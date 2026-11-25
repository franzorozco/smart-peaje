"""Integra /coco-m3/ (COCO Roboflow) y /coco-m3-extra/truck-dataset/ (USP LabelMe v2.0.0)
en un dataset YOLO Pose unificado y libre de fuga de datos: /entrenamiento/datasets/m3_adaptado_v2/.

Fuente complementaria:
  Marcomini, L. A., & Cunha, A. L. (2023). Truck Image Dataset (v2.0.0) [Data set].
  Universidad de São Paulo (USP). Zenodo. https://zenodo.org/records/7695824
  Licencia: Creative Commons Attribution 4.0 International (CC BY 4.0).

Reglas implementadas:
- Conserva intactos /coco-m3/, /coco-m3-extra/ y /entrenamiento/datasets/m3_adaptado/.
- Esquema uniforme: clase única `0: vehiculo`, `kpt_shape: [7, 3]` (`eje_1`..`eje_7`, orden frente -> atrás).
- En LabelMe (USP): usa `Truck` (polígono) para bbox y pertenencia geométrica; `Axle` (`circle` -> points[0] centro,
  `rectangle` -> centroide) para cada eje individual; ignora `Tandem` y `Tridem` como ejes extra (solo se usan
  como pista de orientación frente/atrás).
- Fusiona anotaciones `Axle` duplicadas en la misma rueda (distancia < max(18 px, 1.5% del ancho)) y lo reporta.
- Determina orientación antes de ordenar frente -> atrás; marca casos ambiguos para revisión manual.
- No excluye silenciosamente camiones con >7 ejes: los documenta en `reporte_conversion_v2.json`,
  `metadatos_procedencia.json` y `revision_manual/mas_de_7_ejes/`.
- Separa `train`/`valid`/`test` por video/escena completa (cero fuga de fotogramas relacionados).
- Prioriza camiones de 3, 4, 5, 6 y 7 ejes reduciendo redundancia temporal de frames de solo 2 ejes en `vid_1`/`vid_2`.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import re
import shutil

import cv2
import numpy as np

from convertir_coco_m3 import (
    MAX_EJES,
    NOMBRES_EJES,
    _convertir_anotacion as _convertir_ann_coco,
    _dibujar_muestra,
    _formatear_linea_yolo,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COCO_SRC = ROOT / "coco-m3"
DEFAULT_USP_SRC = ROOT / "coco-m3-extra" / "truck-dataset"
DEFAULT_DST = ROOT / "entrenamiento" / "datasets" / "m3_adaptado_v2"

FUENTE_USP_INFO = {
    "nombre": "Truck Image Dataset v2.0.0",
    "autores": "Leandro Arab Marcomini & André Luiz Cunha (Universidad de São Paulo, Brasil)",
    "url": "https://zenodo.org/records/7695824",
    "publicacion": "Marcomini, L. A., & Cunha, A. L. (2022). Truck Axle Detection with Convolutional Neural Networks. arXiv:2204.01868",
    "licencia": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
    "condiciones_reutilizacion": "Permitido compartir y adaptar con atribución explícita a los autores y a Zenodo 7695824.",
}


def _centro_shape(shape: dict) -> tuple[float, float]:
    """Obtiene el centro exacto de una anotación LabelMe (`circle`, `rectangle` o `polygon`)."""
    pts = np.asarray(shape.get("points") or [], dtype=float)
    if len(pts) == 0:
        return 0.0, 0.0
    stype = (shape.get("shape_type") or "").lower()
    if stype == "circle":
        # En LabelMe, circle guarda [[cx, cy], [borde_x, borde_y]]
        return float(pts[0, 0]), float(pts[0, 1])
    if stype == "rectangle":
        return float((pts[:, 0].min() + pts[:, 0].max()) / 2.0), float((pts[:, 1].min() + pts[:, 1].max()) / 2.0)
    return float(pts[:, 0].mean()), float(pts[:, 1].mean())


def _fusionar_ejes_duplicados(
    puntos: list[tuple[float, float]],
    umbral_px: float,
) -> tuple[list[tuple[float, float]], int]:
    """Fusiona centros `Axle` prácticamente superpuestos sobre la misma rueda."""
    if len(puntos) <= 1:
        return puntos, 0
    clusters: list[list[tuple[float, float]]] = []
    for px, py in sorted(puntos, key=lambda p: p[0]):
        asignado = False
        for cl in clusters:
            mx = sum(p[0] for p in cl) / len(cl)
            my = sum(p[1] for p in cl) / len(cl)
            if ((px - mx) ** 2 + (py - my) ** 2) ** 0.5 <= umbral_px:
                cl.append((px, py))
                asignado = True
                break
        if not asignado:
            clusters.append([(px, py)])

    fusionados = [
        (sum(p[0] for p in cl) / len(cl), sum(p[1] for p in cl) / len(cl))
        for cl in clusters
    ]
    duplicados_rem = len(puntos) - len(fusionados)
    return fusionados, duplicados_rem


def _determinar_orientacion_usp(
    ejes_xy: list[tuple[float, float]],
    agrupaciones_xy: list[tuple[float, float]],
    bbox: tuple[float, float, float, float],
    img_h: int,
) -> tuple[str, bool, str]:
    """Determina si el frente del camión está a la derecha o izquierda.

    Retorna (orientacion, es_ambigua, criterio).
    `frente_derecha` => ordenar ejes X descendente (derecha -> izquierda).
    `frente_izquierda` => ordenar ejes X ascendente (izquierda -> derecha).
    """
    _, ty1, _, ty2 = bbox
    en_carril_cercano = ty2 >= 0.72 * img_h
    xs = sorted(p[0] for p in ejes_xy)

    # Pista 1: si hay agrupaciones Tandem/Tridem, suelen concentrarse hacia la parte trasera
    voto_grupos: str | None = None
    if agrupaciones_xy and len(xs) >= 3:
        media_ejes = sum(xs) / len(xs)
        media_grupos = sum(p[0] for p in agrupaciones_xy) / len(agrupaciones_xy)
        if media_grupos < media_ejes - 15.0:
            voto_grupos = "frente_derecha"
        elif media_grupos > media_ejes + 15.0:
            voto_grupos = "frente_izquierda"

    # Pista 2: espaciado extremo (eje delantero direccional más separado del segundo eje que el tándem trasero)
    voto_espaciado: str | None = None
    if len(xs) >= 3:
        gap_izq = xs[1] - xs[0]
        gap_der = xs[-1] - xs[-2]
        if gap_der > gap_izq * 1.30:
            voto_espaciado = "frente_derecha"
        elif gap_izq > gap_der * 1.30:
            voto_espaciado = "frente_izquierda"

    # En la cámara fija [ROI-1] de São Paulo, el carril cercano viaja izquierda -> derecha (frente_derecha)
    if en_carril_cercano:
        if voto_grupos == "frente_izquierda" and voto_espaciado == "frente_izquierda":
            return "frente_izquierda", True, "contradice_carril_cercano"
        if voto_grupos == "frente_derecha" or voto_espaciado == "frente_derecha":
            return "frente_derecha", False, "consenso_geometria_y_carril"
        if len(xs) == 2:
            # 2 ejes en carril cercano unidireccional verificado por escena
            return "frente_derecha", False, "carril_unidireccional_roi1"
        return "frente_derecha", True, "espaciado_simetrico_en_carril"

    # Carril lejano / fondo (posible sentido contrario)
    if voto_grupos and voto_espaciado and voto_grupos == voto_espaciado:
        return voto_grupos, False, "geometria_carril_fondo"
    if voto_grupos:
        return voto_grupos, True, "solo_agrupaciones_fondo"
    if voto_espaciado:
        return voto_espaciado, True, "solo_espaciado_fondo"
    return "frente_izquierda", True, "orientacion_ambigua_carril_fondo"


def _dibujar_mas_de_7_ejes(
    img_path: Path,
    bbox: tuple[float, float, float, float],
    ejes_ordenados: list[tuple[float, float]],
    destino: Path,
) -> None:
    img = cv2.imread(str(img_path))
    if img is None:
        return
    x1, y1, x2, y2 = [int(round(v)) for v in bbox]
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 140, 255), 3)
    cv2.putText(
        img,
        f"REVISAR: {len(ejes_ordenados)} ejes (>7)",
        (x1, max(28, y1 - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (0, 140, 255),
        2,
        cv2.LINE_AA,
    )
    for idx, (ex, ey) in enumerate(ejes_ordenados, start=1):
        cv2.circle(img, (int(ex), int(ey)), 8, (0, 255, 255), -1, cv2.LINE_AA)
        cv2.putText(
            img, f"e{idx}", (int(ex) + 8, int(ey) - 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2, cv2.LINE_AA,
        )
    h, w = img.shape[:2]
    if max(h, w) > 1280:
        esc = 1280.0 / max(h, w)
        img = cv2.resize(img, (int(w * esc), int(h * esc)), interpolation=cv2.INTER_AREA)
    destino.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(destino), img, [cv2.IMWRITE_JPEG_QUALITY, 88])


def _cargar_items_coco(coco_src: Path, submuestrear_2ejes: bool) -> tuple[list[dict], list[dict], Counter]:
    """Lee las 3 particiones de /coco-m3/ y las agrupa por video/escena sin fuga."""
    items_por_escena: dict[str, list[dict]] = defaultdict(list)
    avisos_globales: list[dict] = []
    cats_excluidas = Counter()

    for split_orig in ("train", "valid", "test"):
        ann_path = coco_src / split_orig / "_annotations.coco.json"
        if not ann_path.is_file():
            continue
        data = json.loads(ann_path.read_text(encoding="utf-8"))
        cats = {c["id"]: c for c in data.get("categories", [])}
        imgs = {im["id"]: im for im in data.get("images", [])}
        anns_por_img: dict[int, list[dict]] = defaultdict(list)
        for ann in data.get("annotations", []):
            anns_por_img[ann["image_id"]].append(ann)

        for img_id, im in imgs.items():
            fname = im["file_name"]
            src_img = coco_src / split_orig / fname
            if not src_img.is_file():
                avisos_globales.append({"fuente": "coco_m3", "tipo": "imagen_faltante", "imagen": fname})
                continue

            base = fname.split(".rf.")[0]
            m = re.match(r"^(vid_\d+)", base)
            grupo_escena = f"coco_{m.group(1)}" if m else f"coco_ind_{base}"

            img_w = int(im["width"])
            img_h = int(im["height"])
            registros: list[dict] = []
            avisos_img: list[dict] = []

            for ann in anns_por_img.get(img_id, []):
                cat = cats.get(ann["category_id"])
                if not cat:
                    continue
                reg, avs = _convertir_ann_coco(ann, cat, img_w, img_h)
                for av in avs:
                    av["fuente"] = "coco_m3"
                    av["imagen"] = fname
                    avisos_globales.append(av)
                    if av["tipo"] == "categoria_excluida":
                        cats_excluidas[av["categoria"]] += 1
                    else:
                        avisos_img.append(av)
                if reg is not None:
                    reg["orientacion"] = "coco_lateral_" + reg["lateral"]
                    reg["requiere_revision"] = any(a["annotation_id"] == ann["id"] for a in avisos_img)
                    reg["motivos_revision"] = [a["tipo"] for a in avisos_img if a["annotation_id"] == ann["id"]]
                    registros.append(reg)

            if not registros:
                continue

            tiene_pesado_o_moto = any(
                r["ejes_teoricos"] >= 3 or r["categoria_origen"] in ("vehicle_2_wheels", "vehicle_3_wheels")
                for r in registros
            )
            items_por_escena[grupo_escena].append({
                "fuente": "coco_m3",
                "grupo_escena": grupo_escena,
                "src_img": src_img,
                "nombre_origen": f"{split_orig}/{fname}",
                "nombre_destino": f"coco_{split_orig}_{fname}",
                "registros": registros,
                "tiene_prioritario": tiene_pesado_o_moto,
                "avisos": avisos_img,
            })

    # Reducir redundancia temporal de frames con SOLO autos de 2 ejes en vid_1 y vid_2
    items_finales: list[dict] = []
    descartados_balanceo = 0
    for grupo, lista in sorted(items_por_escena.items()):
        lista.sort(key=lambda x: x["nombre_origen"])
        if submuestrear_2ejes and grupo in ("coco_vid_1", "coco_vid_2"):
            contador_solo_2 = 0
            for it in lista:
                if it["tiene_prioritario"]:
                    items_finales.append(it)
                else:
                    if contador_solo_2 % 3 == 0:
                        items_finales.append(it)
                    else:
                        descartados_balanceo += 1
                    contador_solo_2 += 1
        else:
            items_finales.extend(lista)

    if descartados_balanceo:
        avisos_globales.append({
            "fuente": "coco_m3",
            "tipo": "submuestreo_balanceo_vid_2_ejes",
            "cantidad_frames_omitidos": descartados_balanceo,
            "motivo": "Se conservó 1 de cada 3 frames exclusivamente de 2 ejes en vid_1/vid_2 para reducir redundancia temporal y priorizar camiones de 3-7 ejes.",
        })
    return items_finales, avisos_globales, cats_excluidas


def _cargar_items_usp(
    usp_src: Path,
    revision_gt7_dir: Path,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Convierte las anotaciones LabelMe del Truck Image Dataset v2.0.0 (USP)."""
    items: list[dict] = []
    avisos_globales: list[dict] = []
    vehiculos_gt7: list[dict] = []
    hashes_vistos: dict[str, str] = {}

    for jp in sorted(usp_src.glob("*.json")):
        img_path = jp.with_suffix(".jpg")
        if not img_path.is_file():
            avisos_globales.append({"fuente": "usp_truck_v2", "tipo": "imagen_faltante", "imagen": jp.name})
            continue

        md5 = hashlib.md5(img_path.read_bytes()).hexdigest()
        if md5 in hashes_vistos:
            avisos_globales.append({
                "fuente": "usp_truck_v2",
                "tipo": "duplicado_exacto_omitido",
                "imagen": img_path.name,
                "duplicado_de": hashes_vistos[md5],
            })
            continue
        hashes_vistos[md5] = img_path.name

        data = json.loads(jp.read_text(encoding="utf-8"))
        img_w = int(data.get("imageWidth") or 0)
        img_h = int(data.get("imageHeight") or 0)
        if img_w <= 0 or img_h <= 0:
            im_cv = cv2.imread(str(img_path))
            if im_cv is None:
                avisos_globales.append({"fuente": "usp_truck_v2", "tipo": "imagen_corrupta", "imagen": img_path.name})
                continue
            img_h, img_w = im_cv.shape[:2]

        stem = jp.stem
        m = re.match(r"^(.*)-(\d+)(?:\(\d+\))?$", stem)
        grupo_escena = f"usp_{m.group(1)}" if m else f"usp_{stem}"

        shapes = data.get("shapes") or []
        trucks_shapes = [s for s in shapes if s.get("label") == "Truck"]
        axles_shapes = [s for s in shapes if s.get("label") == "Axle"]
        group_shapes = [s for s in shapes if s.get("label") in ("Tandem", "Tridem")]

        if not trucks_shapes:
            avisos_globales.append({
                "fuente": "usp_truck_v2",
                "tipo": "sin_anotacion_truck",
                "imagen": img_path.name,
                "axles_en_imagen": len(axles_shapes),
            })
            continue

        # Preparar polígonos y bboxes de cada camión
        camiones = []
        for idx_t, ts in enumerate(trucks_shapes):
            pts = np.asarray(ts.get("points") or [], dtype=np.float32)
            if len(pts) < 3:
                avisos_globales.append({"fuente": "usp_truck_v2", "tipo": "poligono_truck_invalido", "imagen": img_path.name})
                continue
            tx1 = max(0.0, min(float(img_w), float(pts[:, 0].min())))
            ty1 = max(0.0, min(float(img_h), float(pts[:, 1].min())))
            tx2 = max(0.0, min(float(img_w), float(pts[:, 0].max())))
            ty2 = max(0.0, min(float(img_h), float(pts[:, 1].max())))
            if (tx2 - tx1) <= 2 or (ty2 - ty1) <= 2:
                continue
            camiones.append({
                "idx": idx_t,
                "poly": pts.reshape((-1, 1, 2)),
                "bbox": (tx1, ty1, tx2, ty2),
                "axles": [],
                "agrupaciones": [],
            })

        if not camiones:
            continue

        # Asociar cada Axle al camión cuyo polígono lo contiene (tolerancia 25 px al contorno)
        for ax_s in axles_shapes:
            cx, cy = _centro_shape(ax_s)
            mejor_ti = None
            mejor_dist = -1e9
            for ti, cam in enumerate(camiones):
                dist = float(cv2.pointPolygonTest(cam["poly"], (cx, cy), True))
                if dist >= -25.0 and dist > mejor_dist:
                    mejor_dist = dist
                    mejor_ti = ti
            if mejor_ti is None:
                avisos_globales.append({
                    "fuente": "usp_truck_v2",
                    "tipo": "eje_huerfano_fuera_de_poligono",
                    "imagen": img_path.name,
                    "centro": [round(cx, 1), round(cy, 1)],
                })
            else:
                camiones[mejor_ti]["axles"].append((cx, cy))

        # Asociar Tandem/Tridem solo como pista de orientación (NUNCA como ejes extra)
        for gs in group_shapes:
            gx, gy = _centro_shape(gs)
            for cam in camiones:
                if float(cv2.pointPolygonTest(cam["poly"], (gx, gy), True)) >= -25.0:
                    cam["agrupaciones"].append((gx, gy))
                    break

        registros_img: list[dict] = []
        imagen_tiene_gt7 = False

        for cam in camiones:
            tx1, ty1, tx2, ty2 = cam["bbox"]
            tw = tx2 - tx1
            th = ty2 - ty1
            umbral_dup = max(18.0, 0.015 * tw)
            ejes_limpios, dups_fusionados = _fusionar_ejes_duplicados(cam["axles"], umbral_dup)

            motivos_cam: list[str] = []
            if dups_fusionados > 0:
                motivos_cam.append(f"ejes_duplicados_fusionados:{dups_fusionados}")
                avisos_globales.append({
                    "fuente": "usp_truck_v2",
                    "tipo": "ejes_duplicados_fusionados",
                    "imagen": img_path.name,
                    "camion_idx": cam["idx"],
                    "fusionados": dups_fusionados,
                    "ejes_resultantes": len(ejes_limpios),
                })

            n_ejes = len(ejes_limpios)
            if n_ejes == 0:
                avisos_globales.append({
                    "fuente": "usp_truck_v2",
                    "tipo": "truck_sin_ejes_asociados",
                    "imagen": img_path.name,
                    "camion_idx": cam["idx"],
                })
                continue

            # Verificar que los centros caigan en la zona inferior esperada de las ruedas
            ejes_altos = [p for p in ejes_limpios if p[1] < ty1 + 0.45 * th]
            if ejes_altos:
                motivos_cam.append("eje_fuera_zona_inferior")
                avisos_globales.append({
                    "fuente": "usp_truck_v2",
                    "tipo": "eje_fuera_zona_inferior",
                    "imagen": img_path.name,
                    "camion_idx": cam["idx"],
                    "cantidad": len(ejes_altos),
                })

            orientacion, es_ambigua, criterio_ori = _determinar_orientacion_usp(
                ejes_limpios, cam["agrupaciones"], cam["bbox"], img_h
            )
            if es_ambigua:
                motivos_cam.append(f"orientacion_ambigua:{criterio_ori}")
                avisos_globales.append({
                    "fuente": "usp_truck_v2",
                    "tipo": "revision_orientacion_ambigua",
                    "imagen": img_path.name,
                    "camion_idx": cam["idx"],
                    "orientacion_asignada": orientacion,
                    "criterio": criterio_ori,
                })

            # Ordenar estrictamente de frente hacia atrás según orientación
            ejes_ordenados = sorted(
                ejes_limpios,
                key=lambda p: p[0],
                reverse=(orientacion == "frente_derecha"),
            )

            # Manejo explícito de vehículos con >7 ejes (NO excluir silenciosamente)
            if n_ejes > MAX_EJES:
                imagen_tiene_gt7 = True
                vis_gt7 = revision_gt7_dir / f"{Path(img_path.name).stem}_cam{cam['idx']}_{n_ejes}ejes.jpg"
                _dibujar_mas_de_7_ejes(img_path, cam["bbox"], ejes_ordenados, vis_gt7)
                registro_gt7 = {
                    "fuente": "usp_truck_v2",
                    "imagen": img_path.name,
                    "grupo_escena": grupo_escena,
                    "camion_idx": cam["idx"],
                    "ejes_reales": n_ejes,
                    "orientacion": orientacion,
                    "bbox_px": [round(tx1, 1), round(ty1, 1), round(tx2, 1), round(ty2, 1)],
                    "ejes_px": [[round(ex, 1), round(ey, 1)] for ex, ey in ejes_ordenados],
                    "motivo": f"Supera esquema uniforme kpt_shape [{MAX_EJES}, 3]; conservado para auditoría y revisión manual sin truncar.",
                    "muestra_visual": str(vis_gt7.relative_to(revision_gt7_dir.parent.parent)),
                }
                vehiculos_gt7.append(registro_gt7)
                avisos_globales.append({
                    "fuente": "usp_truck_v2",
                    "tipo": "excede_esquema_7_ejes",
                    "imagen": img_path.name,
                    "ejes_reales": n_ejes,
                })
                continue

            if n_ejes == 1:
                motivos_cam.append("revision_eje_unico_visible")
                avisos_globales.append({
                    "fuente": "usp_truck_v2",
                    "tipo": "revision_eje_unico_visible",
                    "imagen": img_path.name,
                    "camion_idx": cam["idx"],
                })

            xc = ((tx1 + tx2) / 2.0) / img_w
            yc = ((ty1 + ty2) / 2.0) / img_h
            nw = tw / img_w
            nh = th / img_h

            kpts_norm: list[tuple[float, float, int]] = []
            for ex, ey in ejes_ordenados:
                ex_c = max(0.0, min(float(img_w), ex))
                ey_c = max(0.0, min(float(img_h), ey))
                kpts_norm.append((ex_c / img_w, ey_c / img_h, 2))
            while len(kpts_norm) < MAX_EJES:
                kpts_norm.append((0.0, 0.0, 0))

            registros_img.append({
                "bbox_norm": (xc, yc, nw, nh),
                "kpts_norm": kpts_norm,
                "categoria_origen": f"usp_truck_{n_ejes}_axles",
                "ejes_teoricos": n_ejes,
                "ejes_visibles": n_ejes,
                "orientacion": orientacion,
                "requiere_revision": bool(motivos_cam),
                "motivos_revision": motivos_cam,
            })

        # Si la imagen contiene un vehículo >7 ejes no etiquetado en [7,3], no incluirla en entrenamiento
        # para evitar entrenar a YOLO a ignorar camiones pesados reales como si fueran fondo.
        if imagen_tiene_gt7 or not registros_img:
            continue

        items.append({
            "fuente": "usp_truck_v2",
            "grupo_escena": grupo_escena,
            "src_img": img_path,
            "nombre_origen": img_path.name,
            "nombre_destino": f"usp_{img_path.name}",
            "registros": registros_img,
            "tiene_prioritario": any(r["ejes_teoricos"] >= 3 for r in registros_img),
            "avisos": [],
        })

    return items, avisos_globales, vehiculos_gt7


def _asignar_splits_por_grupo(items: list[dict], seed: int = 42) -> dict[str, list[dict]]:
    """Asigna grupos de video/escena completos a train (~70%), valid (~20%) y test (~10%)
    estratificando por número de ejes (priorizando 3..7 ejes) sin fuga entre splits.
    """
    rng = random.Random(seed)
    por_grupo: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        por_grupo[it["grupo_escena"]].append(it)

    # Separar por fuente para estratificar cada fuente por grupos completos
    grupos_por_fuente: dict[str, list[tuple[str, list[dict]]]] = defaultdict(list)
    for g, lista in sorted(por_grupo.items()):
        fuente = lista[0]["fuente"]
        grupos_por_fuente[fuente].append((g, lista))

    objetivos_ratio = {"train": 0.70, "valid": 0.20, "test": 0.10}
    asignacion: dict[str, list[dict]] = {"train": [], "valid": [], "test": []}

    for fuente, lista_grupos in sorted(grupos_por_fuente.items()):
        # Conteo global de ejes de la fuente para calcular objetivos por split
        total_ejes_fuente = Counter()
        total_imgs_fuente = 0
        for _, lista in lista_grupos:
            total_imgs_fuente += len(lista)
            for it in lista:
                for r in it["registros"]:
                    total_ejes_fuente[r["ejes_teoricos"]] += 1

        # Ordenar grupos: primero los que tienen ejes más escasos (7, 4, 5, 6, 3), luego por tamaño descendente
        def _clave_prioridad(par: tuple[str, list[dict]]):
            g, lista = par
            cnt = Counter(r["ejes_teoricos"] for it in lista for r in it["registros"])
            rareza = cnt[7] * 100 + cnt[4] * 40 + cnt[5] * 25 + cnt[6] * 20 + cnt[3] * 10
            return (-rareza, -len(lista), rng.random(), g)

        lista_ordenada = sorted(lista_grupos, key=_clave_prioridad)

        conteo_ejes_split = {sp: Counter() for sp in ("train", "valid", "test")}
        conteo_imgs_split = {sp: 0 for sp in ("train", "valid", "test")}

        # Pesos más altos para ejes minoritarios (3..7) al evaluar qué split necesita más este grupo
        pesos_eje = {2: 1.0, 3: 3.0, 4: 6.0, 5: 5.0, 6: 5.0, 7: 8.0}

        for g, lista in lista_ordenada:
            cnt_g = Counter(r["ejes_teoricos"] for it in lista for r in it["registros"])
            n_g = len(lista)

            # Evitar que los videos gigantes coco_vid_1/coco_vid_2 desequilibren test (10%)
            candidatos_sp = ["train", "valid", "test"]
            if g in ("coco_vid_1", "coco_vid_2"):
                candidatos_sp = ["train", "valid"]

            mejor_sp = None
            mejor_score = float("inf")
            for sp in candidatos_sp:
                obj_imgs = max(1.0, total_imgs_fuente * objetivos_ratio[sp])
                llenado_imgs = (conteo_imgs_split[sp] + n_g) / obj_imgs

                # Promedio ponderado del nivel de llenado tras agregar este grupo:
                # elegir el menor llenado empuja todos los splits hacia su cuota exacta 70/20/10.
                suma_w = 2.0
                suma_llenado = llenado_imgs * 2.0
                for eje, cantidad in cnt_g.items():
                    tot_e = total_ejes_fuente[eje]
                    if tot_e == 0:
                        continue
                    obj_e = max(0.5, tot_e * objetivos_ratio[sp])
                    llenado_e = (conteo_ejes_split[sp][eje] + cantidad) / obj_e
                    w_e = pesos_eje.get(eje, 2.0)
                    suma_llenado += llenado_e * w_e
                    suma_w += w_e

                score = suma_llenado / suma_w
                if score < mejor_score:
                    mejor_score = score
                    mejor_sp = sp

            assert mejor_sp is not None
            asignacion[mejor_sp].extend(lista)
            conteo_imgs_split[mejor_sp] += n_g
            conteo_ejes_split[mejor_sp].update(cnt_g)

    return asignacion


def construir_v2(
    coco_src: Path,
    usp_src: Path,
    dst_dir: Path,
    submuestrear_2ejes: bool = True,
    max_muestras_vis: int = 36,
) -> dict:
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    revision_gt7_dir = dst_dir / "revision_manual" / "mas_de_7_ejes"

    items_coco, avisos_coco, cats_excluidas = _cargar_items_coco(coco_src, submuestrear_2ejes=submuestrear_2ejes)
    items_usp, avisos_usp, vehiculos_gt7 = _cargar_items_usp(usp_src, revision_gt7_dir=revision_gt7_dir)

    todos_items = items_coco + items_usp
    asignacion = _asignar_splits_por_grupo(todos_items, seed=42)

    hashes_md5: dict[str, list[tuple[str, str]]] = defaultdict(list)
    escenas_por_split: dict[str, set[str]] = defaultdict(set)
    metadatos_procedencia: list[dict] = []
    muestras_vis_por_clave: dict[tuple[str, int], int] = defaultdict(int)
    total_muestras_vis = 0

    resumen_splits: dict[str, dict] = {}

    for split in ("train", "valid", "test"):
        img_out = dst_dir / split / "images"
        lbl_out = dst_dir / split / "labels"
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        dist_ejes_teoricos = Counter()
        dist_ejes_visibles = Counter()
        dist_fuente_imgs = Counter()
        dist_fuente_inst = Counter()
        instancias_total = 0

        for it in asignacion[split]:
            src_img: Path = it["src_img"]
            dst_name: str = it["nombre_destino"]
            raw_bytes = src_img.read_bytes()
            md5 = hashlib.md5(raw_bytes).hexdigest()

            # Protección adicional contra duplicados exactos entre datasets
            if md5 in hashes_md5:
                avisos_usp.append({
                    "fuente": it["fuente"],
                    "tipo": "duplicado_cruzado_omitido",
                    "imagen": it["nombre_origen"],
                    "duplicado_de": hashes_md5[md5][0],
                })
                continue
            hashes_md5[md5].append((split, dst_name))
            escenas_por_split[it["grupo_escena"]].add(split)

            shutil.copy2(src_img, img_out / dst_name)
            lineas = [_formatear_linea_yolo(r) for r in it["registros"]]
            (lbl_out / f"{Path(dst_name).stem}.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")

            dist_fuente_imgs[it["fuente"]] += 1
            for r in it["registros"]:
                instancias_total += 1
                dist_fuente_inst[it["fuente"]] += 1
                dist_ejes_teoricos[r["ejes_teoricos"]] += 1
                dist_ejes_visibles[r["ejes_visibles"]] += 1

            metadatos_procedencia.append({
                "split": split,
                "archivo_imagen": dst_name,
                "archivo_etiqueta": f"{Path(dst_name).stem}.txt",
                "fuente": it["fuente"],
                "archivo_origen": it["nombre_origen"],
                "grupo_escena": it["grupo_escena"],
                "instancias": [
                    {
                        "categoria_origen": r["categoria_origen"],
                        "ejes_reales": r["ejes_teoricos"],
                        "ejes_visibles": r["ejes_visibles"],
                        "orientacion": r["orientacion"],
                        "requiere_revision": r.get("requiere_revision", False),
                        "motivos_revision": r.get("motivos_revision", []),
                    }
                    for r in it["registros"]
                ],
            })

            # Muestras visuales variadas cubriendo ambas fuentes y ejes 2..7
            if total_muestras_vis < max_muestras_vis:
                max_e = max(r["ejes_teoricos"] for r in it["registros"])
                clave_vis = (it["fuente"], max_e)
                if muestras_vis_por_clave[clave_vis] < 3:
                    vis_name = f"{split}_{it['fuente']}_ejes{max_e}_{Path(dst_name).stem[:28]}.jpg"
                    _dibujar_muestra(src_img, it["registros"], dst_dir / "validacion_visual" / vis_name)
                    muestras_vis_por_clave[clave_vis] += 1
                    total_muestras_vis += 1

        resumen_splits[split] = {
            "imagenes": sum(dist_fuente_imgs.values()),
            "imagenes_por_fuente": dict(dist_fuente_imgs),
            "instancias_vehiculo": instancias_total,
            "instancias_por_fuente": dict(dist_fuente_inst),
            "distribucion_ejes_reales": {str(k): v for k, v in sorted(dist_ejes_teoricos.items())},
            "distribucion_ejes_visibles": {str(k): v for k, v in sorted(dist_ejes_visibles.items())},
        }

    # Auditoría de fugas y duplicados
    escenas_fugadas = {g: sorted(sps) for g, sps in escenas_por_split.items() if len(sps) > 1}
    md5_dup_splits = {h: v for h, v in hashes_md5.items() if len({s for s, _ in v}) > 1}

    todos_avisos = avisos_coco + avisos_usp
    conteo_avisos = Counter(a["tipo"] for a in todos_avisos)

    # Guardar data.yaml
    data_yaml = "\n".join([
        "# Dataset YOLO Pose combinado v2 (Roboflow /coco-m3/ + USP Truck Image Dataset v2.0.0)",
        "path: .",
        "train: train/images",
        "val: valid/images",
        "test: test/images",
        "",
        "names:",
        "  0: vehiculo",
        "",
        f"kpt_shape: [{MAX_EJES}, 3]",
        "# Orden semántico de frente a parte trasera:",
        f"# {', '.join(NOMBRES_EJES)}",
        "# Nota: entrenar con fliplr=0.0 para preservar el orden semántico frente -> atrás.",
        "",
    ])
    (dst_dir / "data.yaml").write_text(data_yaml, encoding="utf-8")

    # Metadatos de procedencia para evaluación MAE posterior por fuente y número real de ejes
    (dst_dir / "metadatos_procedencia.json").write_text(
        json.dumps(
            {
                "esquema": {"clase": "vehiculo", "kpt_shape": [MAX_EJES, 3], "keypoints": NOMBRES_EJES},
                "fuente_complementaria": FUENTE_USP_INFO,
                "imagenes_incluidas": metadatos_procedencia,
                "vehiculos_mas_de_7_ejes_auditados": vehiculos_gt7,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    resumen_final = {
        "destino": str(dst_dir),
        "kpt_shape": [MAX_EJES, 3],
        "nombres_keypoints": NOMBRES_EJES,
        "submuestreo_2ejes_coco_videos": submuestrear_2ejes,
        "fuente_complementaria": FUENTE_USP_INFO,
        "splits": resumen_splits,
        "auditoria": {
            "md5_duplicados_entre_splits": len(md5_dup_splits),
            "escenas_compartidas_entre_splits": len(escenas_fugadas),
            "escenas_totales": len(escenas_por_split),
            "muestras_visuales_generadas": total_muestras_vis,
            "vehiculos_mas_de_7_ejes_auditados": len(vehiculos_gt7),
        },
        "categorias_excluidas_coco": dict(cats_excluidas),
        "resumen_revision_y_avisos": dict(conteo_avisos),
    }

    (dst_dir / "reporte_conversion_v2.json").write_text(
        json.dumps(
            {
                "resumen": resumen_final,
                "vehiculos_mas_de_7_ejes": vehiculos_gt7,
                "total_avisos": len(todos_avisos),
                "avisos": todos_avisos,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Resumen Markdown legible
    tot_ejes_global = Counter()
    for sp_info in resumen_splits.values():
        for k, v in sp_info["distribucion_ejes_reales"].items():
            tot_ejes_global[int(k)] += v
    tot_inst_global = sum(tot_ejes_global.values())
    pesados_global = sum(v for k, v in tot_ejes_global.items() if k >= 3)
    pct_pesados = (pesados_global / tot_inst_global * 100.0) if tot_inst_global else 0.0

    md = [
        "# Resumen de Conversión M3 v2 (Dataset Combinado YOLO Pose)",
        "",
        "## Fuentes y licencias",
        "1. **`coco_m3` (`/coco-m3/`):** Vehicle Wheel Pose (Roboflow, formato COCO), conservado intacto.",
        f"2. **`usp_truck_v2` (`/coco-m3-extra/truck-dataset/`):** **{FUENTE_USP_INFO['nombre']}** — {FUENTE_USP_INFO['autores']}.",
        f"   - URL: {FUENTE_USP_INFO['url']}",
        f"   - Publicación: {FUENTE_USP_INFO['publicacion']}",
        f"   - Licencia: **{FUENTE_USP_INFO['licencia']}** ({FUENTE_USP_INFO['condiciones_reutilizacion']})",
        "",
        "## Esquema YOLO Pose definitivo",
        f"- Clase única: `0: vehiculo`",
        f"- Keypoints: `kpt_shape: [{MAX_EJES}, 3]` (`{', '.join(NOMBRES_EJES)}`, orden frente -> atrás)",
        f"- Total instancias entrenables: **{tot_inst_global}** (vehículos de 3–7 ejes: **{pesados_global}**, **{pct_pesados:.1f}%**)",
        "",
        "## Distribución por conjunto (separación estricta por video/escena)",
        "",
        "| Split | Imágenes (coco / usp) | Instancias | Distribución por número real de ejes |",
        "|---|---:|---:|---|",
    ]
    for sp in ("train", "valid", "test"):
        info = resumen_splits[sp]
        ic = info["imagenes_por_fuente"].get("coco_m3", 0)
        iu = info["imagenes_por_fuente"].get("usp_truck_v2", 0)
        md.append(
            f"| `{sp}` | **{info['imagenes']}** ({ic} / {iu}) | {info['instancias_vehiculo']} | `{info['distribucion_ejes_reales']}` |"
        )
    md.extend([
        "",
        "## Auditoría de calidad y cero fuga de datos",
        f"- Duplicados MD5 entre splits: **{len(md5_dup_splits)}**",
        f"- Escenas/videos compartidos entre splits: **{len(escenas_fugadas)}** (sobre {len(escenas_por_split)} escenas independientes)",
        f"- Vehículos con >7 ejes auditados (NO excluidos silenciosamente): **{len(vehiculos_gt7)}** (ver `revision_manual/mas_de_7_ejes/` y `reporte_conversion_v2.json`)",
        f"- Muestras visuales generadas: **{total_muestras_vis}** en `validacion_visual/`",
        f"- Resumen de avisos y revisión manual: `{dict(conteo_avisos)}`",
        "",
    ])
    (dst_dir / "RESUMEN_CONVERSION_V2.md").write_text("\n".join(md), encoding="utf-8")
    return resumen_final


def main() -> None:
    parser = argparse.ArgumentParser(description="Construir dataset combinado M3 v2 (COCO + USP LabelMe).")
    parser.add_argument("--coco", type=Path, default=DEFAULT_COCO_SRC)
    parser.add_argument("--usp", type=Path, default=DEFAULT_USP_SRC)
    parser.add_argument("--dst", type=Path, default=DEFAULT_DST)
    parser.add_argument("--sin-submuestreo", action="store_true", help="Incluir el 100% de frames de 2 ejes de vid_1/vid_2")
    parser.add_argument("--muestras", type=int, default=36)
    args = parser.parse_args()

    resumen = construir_v2(
        coco_src=args.coco,
        usp_src=args.usp,
        dst_dir=args.dst,
        submuestrear_2ejes=not args.sin_submuestreo,
        max_muestras_vis=args.muestras,
    )
    print(json.dumps(resumen, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
