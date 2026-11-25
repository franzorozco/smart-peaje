"""Convierte el dataset COCO de ruedas (/coco-m3/) a formato YOLO Pose por ejes (/entrenamiento/datasets/m3_adaptado/).

Reglas clave:
- Conserva intacto /coco-m3/.
- Esquema uniforme de 7 ejes (eje_1..eje_7, kpt_shape: [7, 3]) determinado por el análisis real del dataset
  (incluyendo vehicle_14_wheels con 7 ejes válidos de frente a atrás).
- Agrupa ruedas izquierda/derecha de un mismo eje seleccionando el lateral dominante visible para evitar
  contar dos veces las ruedas del mismo eje.
- Nunca inventa coordenadas de ruedas ocultas: los ejes ausentes o no visibles quedan en `0 0 0`.
- Marca para revisión anotaciones ambiguas, parciales o fuera de rango y audita duplicados entre splits.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import shutil

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "coco-m3"
DEFAULT_DST = ROOT / "entrenamiento" / "datasets" / "m3_adaptado"

MAX_EJES = 7
NOMBRES_EJES = [f"eje_{i}" for i in range(1, MAX_EJES + 1)]

# Mapeo explícito de categorías vehiculares a pares (izquierda, derecha) en estricto orden frente -> atrás.
# Cuando el eje tiene una sola rueda (moto o eje trasero de triciclo), el segundo elemento es None.
MAPEO_EJES_POR_CATEGORIA: dict[str, list[tuple[str, str | None]]] = {
    "vehicle_2_wheels": [
        ("front_wheel", None),
        ("back_wheel", None),
    ],
    "vehicle_3_wheels": [
        ("front_left_wheel", "front_right_wheel"),
        ("back_wheel", None),
    ],
    "vehicle_4_wheels": [
        ("front_left_wheel", "front_right_wheel"),
        ("back_left_wheel", "back_right_wheel"),
    ],
    "vehicle_6_wheels": [
        ("front_left_wheel", "front_right_wheel"),
        ("middle_left_wheel", "middle_right_wheel"),
        ("back_left_wheel", "back_right_wheel"),
    ],
    "vehicle_8_wheels": [
        ("front_left_wheel", "front_right_wheel"),
        ("middle_front_left_wheel", "middle_front_right_wheel"),
        ("middle_back_left_wheel", "middle_back_right_wheel"),
        ("back_left_wheel", "back_right_wheel"),
    ],
    "vehicle_10_wheels": [
        ("front_left", "front_right"),
        ("front_middle_left", "front_middle_right"),
        ("middle_left", "middle_right"),
        ("middle_back_left", "middle_back_right"),
        ("back_left", "back_right"),
    ],
    "vehicle_14_wheels": [
        ("front_left", "front_right"),
        ("middle_front_left", "middle_front_right"),
        ("back_left", "back_right"),
        ("trailer_front_left_1", "trailer_front_right_1"),
        ("trailer_front_left_2", "trailer_front_right_2"),
        ("trailer_back_left_1", "trailer_back_right_1"),
        ("trailer_back_left_2", "trailer_back_right_2"),
    ],
}

CATEGORIAS_EXCLUIDAS_CONOCIDAS = {
    "cars": "Supercategoría vacía sin instancias",
    "0": "Anotación huérfana sin keypoints",
    "person": "Peatón (keypoints de pies, no vehículo)",
}


def _punto_valido(x: float, y: float, v: float, img_w: int, img_h: int) -> tuple[bool, bool]:
    """Devuelve (visible, fuera_de_imagen)."""
    if v <= 0 or (x == 0 and y == 0):
        return False, False
    fuera = x < -2 or y < -2 or x > img_w + 2 or y > img_h + 2
    return True, fuera


def _convertir_anotacion(
    ann: dict,
    cat: dict,
    img_w: int,
    img_h: int,
) -> tuple[dict | None, list[dict]]:
    """Convierte una anotación COCO a una fila YOLO Pose de 7 ejes y devuelve avisos de revisión."""
    avisos: list[dict] = []
    cat_name = cat["name"]
    if cat_name not in MAPEO_EJES_POR_CATEGORIA:
        return None, [{
            "tipo": "categoria_excluida",
            "annotation_id": ann["id"],
            "categoria": cat_name,
            "motivo": CATEGORIAS_EXCLUIDAS_CONOCIDAS.get(cat_name, "Categoría no vehicular o no mapeada"),
        }]

    bbox = ann.get("bbox") or []
    if len(bbox) != 4:
        return None, [{"tipo": "bbox_invalido", "annotation_id": ann["id"], "categoria": cat_name}]

    bx, by, bw, bh = [float(v) for v in bbox]
    if bw <= 1 or bh <= 1:
        return None, [{"tipo": "bbox_degenerado", "annotation_id": ann["id"], "categoria": cat_name, "bbox": bbox}]

    # Recortar bbox a los límites de la imagen
    x1 = max(0.0, min(float(img_w), bx))
    y1 = max(0.0, min(float(img_h), by))
    x2 = max(0.0, min(float(img_w), bx + bw))
    y2 = max(0.0, min(float(img_h), by + bh))
    nw = (x2 - x1) / img_w
    nh = (y2 - y1) / img_h
    if nw <= 0.001 or nh <= 0.001:
        return None, [{"tipo": "bbox_fuera_imagen", "annotation_id": ann["id"], "categoria": cat_name}]
    xc = ((x1 + x2) / 2.0) / img_w
    yc = ((y1 + y2) / 2.0) / img_h

    kpt_names: list[str] = cat.get("keypoints") or []
    raw_kpts: list[float] = ann.get("keypoints") or []
    if len(raw_kpts) != len(kpt_names) * 3:
        return None, [{
            "tipo": "keypoints_inconsistentes",
            "annotation_id": ann["id"],
            "categoria": cat_name,
            "esperados": len(kpt_names) * 3,
            "encontrados": len(raw_kpts),
        }]

    mapa_kpts: dict[str, tuple[float, float, int]] = {}
    for idx, nombre in enumerate(kpt_names):
        kx = float(raw_kpts[3 * idx])
        ky = float(raw_kpts[3 * idx + 1])
        kv = int(raw_kpts[3 * idx + 2])
        mapa_kpts[nombre] = (kx, ky, kv)

    esquema_ejes = MAPEO_EJES_POR_CATEGORIA[cat_name]

    # Contar visibilidad por lateral para elegir el lado dominante (evita mezclar caras)
    vis_izq = 0
    vis_der = 0
    for izq_n, der_n in esquema_ejes:
        if der_n is None:
            continue
        if izq_n in mapa_kpts:
            ok, _ = _punto_valido(*mapa_kpts[izq_n], img_w, img_h)
            if ok:
                vis_izq += 1
        if der_n in mapa_kpts:
            ok, _ = _punto_valido(*mapa_kpts[der_n], img_w, img_h)
            if ok:
                vis_der += 1

    preferir_izq = vis_izq >= vis_der

    ejes_salida: list[tuple[float, float, int]] = []
    ejes_visibles = 0
    uso_lateral_opuesto = False
    fuera_rango = False

    for izq_n, der_n in esquema_ejes:
        elegido: tuple[float, float, int] | None = None
        if der_n is None:
            pt = mapa_kpts.get(izq_n)
            if pt:
                ok, out_b = _punto_valido(*pt, img_w, img_h)
                if ok:
                    elegido = pt
                    fuera_rango = fuera_rango or out_b
        else:
            primario = izq_n if preferir_izq else der_n
            secundario = der_n if preferir_izq else izq_n
            pt_p = mapa_kpts.get(primario)
            pt_s = mapa_kpts.get(secundario)
            ok_p, out_p = _punto_valido(*pt_p, img_w, img_h) if pt_p else (False, False)
            ok_s, out_s = _punto_valido(*pt_s, img_w, img_h) if pt_s else (False, False)
            if ok_p and pt_p is not None:
                elegido = pt_p
                fuera_rango = fuera_rango or out_p
            elif ok_s and pt_s is not None:
                elegido = pt_s
                uso_lateral_opuesto = True
                fuera_rango = fuera_rango or out_s

        if elegido is not None:
            kx, ky, kv = elegido
            kx_clamped = max(0.0, min(float(img_w), kx))
            ky_clamped = max(0.0, min(float(img_h), ky))
            ejes_salida.append((kx_clamped / img_w, ky_clamped / img_h, 2 if kv >= 2 else 1))
            ejes_visibles += 1
        else:
            ejes_salida.append((0.0, 0.0, 0))

    # Rellenar hasta MAX_EJES con (0, 0, 0) para ejes inexistentes
    while len(ejes_salida) < MAX_EJES:
        ejes_salida.append((0.0, 0.0, 0))

    if ejes_visibles == 0:
        return None, [{
            "tipo": "sin_ejes_visibles",
            "annotation_id": ann["id"],
            "categoria": cat_name,
            "motivo": "Ninguna rueda visible; excluida para no degradar YOLO Pose",
        }]

    if ejes_visibles == 1:
        avisos.append({
            "tipo": "revision_eje_unico_visible",
            "annotation_id": ann["id"],
            "categoria": cat_name,
            "ejes_teoricos": len(esquema_ejes),
            "ejes_visibles": ejes_visibles,
        })
    if uso_lateral_opuesto:
        avisos.append({
            "tipo": "revision_lateral_mixto",
            "annotation_id": ann["id"],
            "categoria": cat_name,
            "ejes_visibles": ejes_visibles,
        })
    if fuera_rango:
        avisos.append({
            "tipo": "revision_keypoint_fuera_imagen",
            "annotation_id": ann["id"],
            "categoria": cat_name,
        })

    return {
        "bbox_norm": (xc, yc, nw, nh),
        "kpts_norm": ejes_salida,
        "categoria_origen": cat_name,
        "ejes_teoricos": len(esquema_ejes),
        "ejes_visibles": ejes_visibles,
        "lateral": "izq" if preferir_izq else "der",
    }, avisos


def _formatear_linea_yolo(registro: dict) -> str:
    xc, yc, nw, nh = registro["bbox_norm"]
    partes = [f"0 {xc:.6f} {yc:.6f} {nw:.6f} {nh:.6f}"]
    for kx, ky, kv in registro["kpts_norm"]:
        if kv == 0:
            partes.append("0 0 0")
        else:
            partes.append(f"{kx:.6f} {ky:.6f} {kv}")
    return " ".join(partes)


def _dibujar_muestra(img_path: Path, registros: list[dict], destino: Path) -> None:
    img = cv2.imread(str(img_path))
    if img is None:
        return
    h, w = img.shape[:2]
    colores_eje = [
        (0, 255, 255),
        (0, 200, 100),
        (255, 180, 0),
        (255, 100, 180),
        (100, 140, 255),
        (180, 255, 100),
        (0, 100, 255),
    ]
    for reg in registros:
        xc, yc, nw, nh = reg["bbox_norm"]
        x1 = int((xc - nw / 2) * w)
        y1 = int((yc - nh / 2) * h)
        x2 = int((xc + nw / 2) * w)
        y2 = int((yc + nh / 2) * h)
        cv2.rectangle(img, (x1, y1), (x2, y2), (34, 197, 94), 2)
        etiqueta = f"{reg['categoria_origen']} ({reg['ejes_visibles']}/{reg['ejes_teoricos']} ejes)"
        cv2.putText(
            img, etiqueta, (x1, max(20, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (34, 197, 94), 2, cv2.LINE_AA,
        )
        for idx, (kx, ky, kv) in enumerate(reg["kpts_norm"]):
            if kv > 0:
                px, py = int(kx * w), int(ky * h)
                color = colores_eje[idx % len(colores_eje)]
                cv2.circle(img, (px, py), 6, color, -1, cv2.LINE_AA)
                cv2.circle(img, (px, py), 7, (15, 23, 42), 2, cv2.LINE_AA)
                cv2.putText(
                    img, f"e{idx + 1}", (px + 7, py - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 2, cv2.LINE_AA,
                )

    max_lado = max(h, w)
    if max_lado > 1280:
        esc = 1280.0 / max_lado
        img = cv2.resize(img, (int(w * esc), int(h * esc)), interpolation=cv2.INTER_AREA)
    destino.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(destino), img, [cv2.IMWRITE_JPEG_QUALITY, 88])


def convertir(src_dir: Path, dst_dir: Path, max_muestras_vis: int = 24) -> dict:
    if not src_dir.is_dir():
        raise FileNotFoundError(f"No existe el directorio origen {src_dir}")

    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    resumen = {
        "origen": str(src_dir),
        "destino": str(dst_dir),
        "kpt_shape": [MAX_EJES, 3],
        "nombres_keypoints": NOMBRES_EJES,
        "splits": {},
        "duplicados": {},
        "categorias_excluidas": Counter(),
        "motivos_revision": Counter(),
    }

    hashes_md5: dict[str, list[tuple[str, str]]] = defaultdict(list)
    bases_rf: dict[str, list[tuple[str, str]]] = defaultdict(list)
    errores_y_revision: list[dict] = []
    muestras_por_eje: dict[int, int] = defaultdict(int)
    total_muestras_vis = 0

    for split in ("train", "valid", "test"):
        ann_path = src_dir / split / "_annotations.coco.json"
        if not ann_path.is_file():
            continue

        data = json.loads(ann_path.read_text(encoding="utf-8"))
        cats = {c["id"]: c for c in data.get("categories", [])}
        imgs = {im["id"]: im for im in data.get("images", [])}
        anns_por_img: dict[int, list[dict]] = defaultdict(list)
        for ann in data.get("annotations", []):
            anns_por_img[ann["image_id"]].append(ann)

        img_out_dir = dst_dir / split / "images"
        lbl_out_dir = dst_dir / split / "labels"
        img_out_dir.mkdir(parents=True, exist_ok=True)
        lbl_out_dir.mkdir(parents=True, exist_ok=True)

        dist_ejes_teoricos = Counter()
        dist_ejes_visibles = Counter()
        dist_categorias = Counter()
        imgs_copiadas = 0
        imgs_sin_vehiculos = 0
        instancias_convertidas = 0

        for img_id, im in imgs.items():
            fname = im["file_name"]
            src_img = src_dir / split / fname
            if not src_img.is_file():
                errores_y_revision.append({"split": split, "tipo": "imagen_faltante", "file_name": fname})
                continue

            raw_bytes = src_img.read_bytes()
            hashes_md5[hashlib.md5(raw_bytes).hexdigest()].append((split, fname))
            bases_rf[fname.split(".rf.")[0]].append((split, fname))

            img_w = int(im["width"])
            img_h = int(im["height"])

            registros_img: list[dict] = []
            for ann in anns_por_img.get(img_id, []):
                cat = cats.get(ann["category_id"])
                if not cat:
                    continue
                reg, avisos = _convertir_anotacion(ann, cat, img_w, img_h)
                for av in avisos:
                    av["split"] = split
                    av["imagen"] = fname
                    errores_y_revision.append(av)
                    if av["tipo"] == "categoria_excluida":
                        resumen["categorias_excluidas"][av["categoria"]] += 1
                    else:
                        resumen["motivos_revision"][av["tipo"]] += 1
                if reg is not None:
                    registros_img.append(reg)
                    instancias_convertidas += 1
                    dist_ejes_teoricos[reg["ejes_teoricos"]] += 1
                    dist_ejes_visibles[reg["ejes_visibles"]] += 1
                    dist_categorias[reg["categoria_origen"]] += 1

            # Copiar imagen y escribir etiqueta YOLO Pose (.txt)
            shutil.copy2(src_img, img_out_dir / fname)
            imgs_copiadas += 1
            lbl_path = lbl_out_dir / f"{Path(fname).stem}.txt"
            lineas = [_formatear_linea_yolo(r) for r in registros_img]
            lbl_path.write_text("\n".join(lineas) + ("\n" if lineas else ""), encoding="utf-8")
            if not lineas:
                imgs_sin_vehiculos += 1

            # Guardar muestras visuales variadas (priorizando vehículos de más ejes)
            if registros_img and total_muestras_vis < max_muestras_vis:
                max_e_img = max(r["ejes_teoricos"] for r in registros_img)
                limite_por_eje = 6 if max_e_img >= 3 else 4
                if muestras_por_eje[max_e_img] < limite_por_eje:
                    vis_name = f"{split}_ejes{max_e_img}_{Path(fname).stem[:32]}.jpg"
                    _dibujar_muestra(src_img, registros_img, dst_dir / "validacion_visual" / vis_name)
                    muestras_por_eje[max_e_img] += 1
                    total_muestras_vis += 1

        resumen["splits"][split] = {
            "imagenes": imgs_copiadas,
            "imagenes_sin_etiquetas": imgs_sin_vehiculos,
            "instancias_vehiculo": instancias_convertidas,
            "distribucion_ejes_teoricos": {str(k): v for k, v in sorted(dist_ejes_teoricos.items())},
            "distribucion_ejes_visibles": {str(k): v for k, v in sorted(dist_ejes_visibles.items())},
            "categorias_origen": dict(sorted(dist_categorias.items())),
        }

    # Auditoría de duplicados
    dup_md5_cruzados = {h: v for h, v in hashes_md5.items() if len({s for s, _ in v}) > 1}
    dup_md5_total = {h: v for h, v in hashes_md5.items() if len(v) > 1}
    dup_base_cruzados = {b: v for b, v in bases_rf.items() if len({s for s, _ in v}) > 1}
    resumen["duplicados"] = {
        "md5_duplicados_totales": len(dup_md5_total),
        "md5_duplicados_entre_splits": len(dup_md5_cruzados),
        "nombre_base_duplicado_entre_splits": len(dup_base_cruzados),
    }
    resumen["categorias_excluidas"] = dict(resumen["categorias_excluidas"])
    resumen["motivos_revision"] = dict(resumen["motivos_revision"])
    resumen["muestras_visuales_generadas"] = total_muestras_vis

    # Generar data.yaml compatible con Ultralytics YOLOv8 Pose
    data_yaml = "\n".join([
        "# Dataset YOLO Pose adaptado desde /coco-m3/ para conteo de ejes",
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
        "# Nota: fliplr=0.0 recomendado al entrenar para preservar el orden semántico frente -> atrás.",
        "",
    ])
    (dst_dir / "data.yaml").write_text(data_yaml, encoding="utf-8")

    # Guardar reporte JSON detallado y resumen Markdown legible
    (dst_dir / "reporte_conversion.json").write_text(
        json.dumps(
            {
                "resumen": resumen,
                "total_registros_revision": len(errores_y_revision),
                "registros_revision": errores_y_revision,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    lineas_md = [
        "# Resumen de Conversión M3 (COCO -> YOLO Pose)",
        "",
        f"- **Origen intacto:** `{src_dir}`",
        f"- **Destino:** `{dst_dir}`",
        f"- **Clase única:** `0: vehiculo`",
        f"- **Esquema de keypoints:** `kpt_shape: [{MAX_EJES}, 3]` (`{', '.join(NOMBRES_EJES)}`)",
        "- **Justificación de 7 ejes:** el análisis de `_annotations.coco.json` confirmó anotaciones válidas de `vehicle_14_wheels` con 7 ejes secuenciales visibles de frente a atrás.",
        f"- **Muestras visuales generadas:** {total_muestras_vis} en `validacion_visual/`",
        "",
        "## Distribución por conjunto",
        "",
        "| Split | Imágenes | Instancias vehículo | Distribución ejes teóricos | Distribución ejes visibles |",
        "|---|---:|---:|---|---|",
    ]
    for split, info in resumen["splits"].items():
        lineas_md.append(
            f"| `{split}` | {info['imagenes']} | {info['instancias_vehiculo']} | "
            f"`{info['distribucion_ejes_teoricos']}` | `{info['distribucion_ejes_visibles']}` |"
        )
    lineas_md.extend([
        "",
        "## Categorías excluidas",
        f"- `{resumen['categorias_excluidas']}`",
        "",
        "## Anotaciones marcadas para revisión",
        f"- `{resumen['motivos_revision']}` (detalle completo en `reporte_conversion.json`)",
        "",
        "## Auditoría de duplicados entre splits",
        f"- Duplicados MD5 totales: **{resumen['duplicados']['md5_duplicados_totales']}**",
        f"- Duplicados MD5 entre splits: **{resumen['duplicados']['md5_duplicados_entre_splits']}**",
        f"- Nombres base (`.rf.`) repetidos entre splits: **{resumen['duplicados']['nombre_base_duplicado_entre_splits']}**",
        "",
    ])
    (dst_dir / "RESUMEN_CONVERSION.md").write_text("\n".join(lineas_md), encoding="utf-8")
    return resumen


def main() -> None:
    parser = argparse.ArgumentParser(description="Convertir dataset COCO /coco-m3/ a YOLO Pose por ejes.")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC, help="Ruta de /coco-m3/")
    parser.add_argument("--dst", type=Path, default=DEFAULT_DST, help="Ruta destino YOLO Pose")
    parser.add_argument("--muestras", type=int, default=24, help="Cantidad máxima de imágenes de validación visual")
    args = parser.parse_args()

    resumen = convertir(args.src, args.dst, max_muestras_vis=args.muestras)
    print(json.dumps(resumen, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
