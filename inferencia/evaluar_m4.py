"""Evaluación reproducible del componente M4 (YOLOv8n-seg COCO person=0) sobre imágenes autorizadas con referencia manual."""
from __future__ import annotations

import base64
import json
import statistics
import time
from pathlib import Path

import cv2

import config
import vision

ROOT = Path(__file__).resolve().parent.parent
EVIDENCIAS_DIR = ROOT / "docs" / "evidencias" / "M4"
UPLOADS_DIR = Path(
    r"C:/Users/Franz Orozco/.gemini/antigravity/brain/5ab0b6c9-d415-450b-aae9-832305800388/.user_uploaded"
)

# Referencias anotadas manualmente mediante inspección visual directa de cada imagen autorizada.
# ref_ocupantes: int (ocupantes visibles confirmables) o None (cabina no determinable por polarizado/reflejo/oclusión).
CASOS_REFERENCIA: list[dict] = [
    {
        "id": "m4_01_conductor_visible",
        "ruta": ROOT / "imagenes" / "PARA SUBIR" / "imag-471-_png.rf.bc8357b5ed97b170088316641ef8eb51.jpg",
        "escenario": "conductor_visible_ventana_abierta",
        "ref_ocupantes": 1,
        "peatones_en_escena": 0,
        "nota": "Toyota Caldina negro con conductor claramente visible por la ventana abierta.",
    },
    {
        "id": "m4_02_ocupante_y_peatones",
        "ruta": ROOT / "imagenes" / "PARA SUBIR" / "imag-622-_png.rf.9a80c1347d6414d1122c246bc7eb83db.jpg",
        "escenario": "ocupante_puerta_abierta_y_peatones_cercanos",
        "ref_ocupantes": 1,
        "peatones_en_escena": 3,
        "nota": "Camioneta roja con 1 ocupante en cabina (puerta abierta) y 3 peatones en la acera derecha.",
    },
    {
        "id": "m4_03_vacio_claro",
        "ruta": UPLOADS_DIR / "media_1795554611711_7b3cc698.webp",
        "escenario": "vehiculo_vacio_cabina_clara",
        "ref_ocupantes": 0,
        "peatones_en_escena": 0,
        "nota": "Hyundai Ioniq blanco estacionado en 3/4 con vidrios claros y 0 ocupantes visibles.",
    },
    {
        "id": "m4_04_peatones_acera",
        "ruta": ROOT / "imagenes" / "PARA SUBIR" / "imag-406-_png.rf.5aef01d6d826d0521998c768ae00d996.jpg",
        "escenario": "peatones_cercanos_sin_ocupantes",
        "ref_ocupantes": 0,
        "peatones_en_escena": 3,
        "nota": "Minibús plateado con 3 peatones caminando en la acera contigua; sin ocupantes visibles.",
    },
    {
        "id": "m4_05_peaton_pegado_vehiculo",
        "ruta": ROOT / "imagenes" / "PARA SUBIR" / "imag-644-_png.rf.8b1e527c14ab52950508ddb6ba7593e8.jpg",
        "escenario": "peaton_junto_a_vehiculo",
        "ref_ocupantes": 0,
        "peatones_en_escena": 2,
        "nota": "Vagoneta gris estacionada con un peatón parado junto a la puerta trasera.",
    },
    {
        "id": "m4_06_vidrio_polarizado_sombra",
        "ruta": ROOT / "imagenes" / "PARA SUBIR" / "imag-1241-_png.rf.8adbb34b92d3289c0cfe638dd9f58462.jpg",
        "escenario": "vidrios_polarizados_u_oscuros",
        "ref_ocupantes": None,
        "peatones_en_escena": 0,
        "nota": "Vagoneta oscura en sombra con vidrios polarizados donde no es posible confirmar el interior.",
    },
    {
        "id": "m4_07_polarizado_y_peatones",
        "ruta": ROOT / "entrenamiento" / "datasets" / "m3_adaptado_v2" / "test" / "images" / "coco_train_images_3423_jpg.rf.305a1351f440220e99c7b103da23c547.jpg",
        "escenario": "vidrios_oscuros_y_peatones_cercanos",
        "ref_ocupantes": None,
        "peatones_en_escena": 4,
        "nota": "SUV gris con vidrios oscuros/reflejo y 4 peatones caminando en la acera izquierda.",
    },
    {
        "id": "m4_08_reflejo_parabrisas",
        "ruta": ROOT / "entrenamiento" / "datasets" / "m3_adaptado_v2" / "test" / "images" / "coco_test_images_1129_jpg.rf.d4ac79116a2822fd0a81a1acfdcc1d4f.jpg",
        "escenario": "reflejo_intenso_parabrisas",
        "ref_ocupantes": None,
        "peatones_en_escena": 0,
        "nota": "Furgoneta blanca con reflejo brillante del cielo sobre el parabrisas.",
    },
    {
        "id": "m4_09_oclusion_letreros_y_peaton",
        "ruta": UPLOADS_DIR / "media_1795555604979_d6474d3f.jpg",
        "escenario": "oclusion_letreros_parabrisas_y_peaton",
        "ref_ocupantes": None,
        "peatones_en_escena": 1,
        "nota": "Minibús rojo 4257XCR con letreros de ruta cubriendo el parabrisas y 1 peatón a la derecha.",
    },
    {
        "id": "m4_10_oclusion_trafico_y_peatones",
        "ruta": UPLOADS_DIR / "media_1795554918902_0898dd50.jpg",
        "escenario": "oclusion_multiple_y_peatones",
        "ref_ocupantes": None,
        "peatones_en_escena": 4,
        "nota": "Minibús rojo en congestión con múltiples peatones próximos y reflejos en parabrisas.",
    },
    {
        "id": "m4_11_reflejos_calle_y_peatones",
        "ruta": ROOT / "imagenes" / "PARA SUBIR" / "imag-558-_png.rf.2230d8ea44c4c709099bc9eb0353a2de.jpg",
        "escenario": "reflejos_y_peatones_cercanos",
        "ref_ocupantes": 0,
        "peatones_en_escena": 4,
        "nota": "Minibuses en avenida urbana con reflejos en parabrisas y peatones en acera.",
    },
    {
        "id": "m4_12_vehiculo_en_movimiento",
        "ruta": ROOT / "imagenes" / "PARA SUBIR" / "20251119_103723_frame_003_jpg.rf.8ea59a28b44ff1f162d6a6aef97ff356.jpg",
        "escenario": "ocupante_visible_en_circulacion",
        "ref_ocupantes": 1,
        "peatones_en_escena": 0,
        "nota": "Vehículo en circulación con ocupante visible en cabina.",
    },
]


def _guardar_evidencia(evidencia_b64: str, destino: Path) -> None:
    if not evidencia_b64:
        return
    raw = evidencia_b64.split(",", 1)[1] if "," in evidencia_b64 else evidencia_b64
    destino.write_bytes(base64.b64decode(raw))


def main() -> None:
    EVIDENCIAS_DIR.mkdir(parents=True, exist_ok=True)
    vision.cargar_modelos(forzar=True)
    pax_model = vision._MODELS["pasajeros"]
    device = vision.resolver_dispositivo()

    # Warmup de 1 pasada para estabilizar mediciones de latencia
    for c in CASOS_REFERENCIA:
        if c["ruta"].is_file():
            img0 = cv2.imread(str(c["ruta"]))
            if img0 is not None:
                pax_model.predict(img0, conf=config.CONF_M4, iou=config.IOU_M4, classes=[0], device=device, verbose=False)
                break

    resultados: list[dict] = []
    lat_m4_ms: list[float] = []
    lat_total_ms: list[float] = []

    exactos_total = 0
    evaluados = 0
    errores_abs: list[float] = []
    exactos_determinables = 0
    total_determinables = 0
    abstenciones_correctas = 0
    total_no_determinables = 0
    peatones_descartados_total = 0

    for caso in CASOS_REFERENCIA:
        ruta: Path = caso["ruta"]
        if not ruta.is_file():
            print(f"[OMITIDO] No existe {ruta}")
            continue
        img = cv2.imread(str(ruta))
        if img is None:
            print(f"[OMITIDO] No se pudo leer {ruta}")
            continue

        # 1. Medición aislada de M4 (YOLOv8n-seg COCO person=0)
        t0 = time.perf_counter()
        _ = pax_model.predict(
            img,
            conf=config.CONF_M4,
            iou=config.IOU_M4,
            classes=[0],
            device=device,
            verbose=False,
        )
        m4_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        lat_m4_ms.append(m4_ms)

        # 2. Medición del pipeline unificado M1+M2+M3+M4
        t1 = time.perf_counter()
        try:
            res = vision.inferir(img)
        except Exception as exc:
            resultados.append({
                "id": caso["id"],
                "escenario": caso["escenario"],
                "ref_ocupantes": caso["ref_ocupantes"],
                "error": str(exc),
                "m4_ms": m4_ms,
            })
            continue
        total_ms = round((time.perf_counter() - t1) * 1000.0, 2)
        lat_total_ms.append(total_ms)

        pred = res.get("pasajeros")
        ref = caso["ref_ocupantes"]
        m4_det = res.get("m4_detalle") or {}
        peatones_desc = int(m4_det.get("peatones_descartados") or 0)
        peatones_descartados_total += peatones_desc

        evaluados += 1
        acierto_exacto = pred == ref
        if acierto_exacto:
            exactos_total += 1

        if ref is None:
            total_no_determinables += 1
            if pred is None:
                abstenciones_correctas += 1
        else:
            total_determinables += 1
            if pred is not None:
                errores_abs.append(abs(int(pred) - int(ref)))
                if int(pred) == int(ref):
                    exactos_determinables += 1

        ev_path = EVIDENCIAS_DIR / f"{caso['id']}.jpg"
        _guardar_evidencia(res.get("evidencia") or "", ev_path)

        resultados.append({
            "id": caso["id"],
            "archivo": ruta.name,
            "escenario": caso["escenario"],
            "categoria_m2": res.get("categoria"),
            "ref_ocupantes": ref,
            "pred_ocupantes": pred,
            "conductor_detectado": res.get("conductor_detectado"),
            "pasajeros_adicionales": res.get("pasajeros_adicionales"),
            "estado_conteo": m4_det.get("estado_conteo"),
            "criterio_rol": m4_det.get("criterio_rol"),
            "peatones_en_escena": caso["peatones_en_escena"],
            "peatones_descartados_m4": peatones_desc,
            "visibilidad_cabina": m4_det.get("visibilidad_cabina"),
            "acierto_exacto": acierto_exacto,
            "m4_ms": m4_ms,
            "pipeline_total_ms": total_ms,
            "evidencia": ev_path.name,
        })

    def _p95(vals: list[float]) -> float | None:
        if not vals:
            return None
        s = sorted(vals)
        idx = min(len(s) - 1, int(round(0.95 * (len(s) - 1))))
        return round(s[idx], 2)

    resumen = {
        "modelo_m4": "YOLOv8n-seg (COCO 2017 Segmentation, clase 0 = person)",
        "dispositivo": str(device),
        "umbrales": {
            "CONF_M4": config.CONF_M4,
            "IOU_M4": config.IOU_M4,
            "M4_MIN_OVERLAP_VEH": config.M4_MIN_OVERLAP_VEH,
            "M4_MIN_OVERLAP_CABINA": config.M4_MIN_OVERLAP_CABINA,
            "M4_MIN_BRILLO_CABINA": config.M4_MIN_BRILLO_CABINA,
            "M4_MIN_CONTRASTE_CABINA": config.M4_MIN_CONTRASTE_CABINA,
            "M4_MAX_REFLEJO_RATIO": config.M4_MAX_REFLEJO_RATIO,
        },
        "total_casos_evaluados": evaluados,
        "exactitud_global_incluye_null": round(exactos_total / evaluados, 4) if evaluados else None,
        "casos_determinables": total_determinables,
        "exactitud_determinables": round(exactos_determinables / total_determinables, 4) if total_determinables else None,
        "mae_determinables_con_prediccion": round(sum(errores_abs) / len(errores_abs), 4) if errores_abs else None,
        "casos_no_determinables_ref_null": total_no_determinables,
        "abstenciones_null_correctas": abstenciones_correctas,
        "peatones_descartados_total": peatones_descartados_total,
        "latencia_m4_ms": {
            "media": round(statistics.mean(lat_m4_ms), 2) if lat_m4_ms else None,
            "p50": round(statistics.median(lat_m4_ms), 2) if lat_m4_ms else None,
            "p95": _p95(lat_m4_ms),
        },
        "latencia_pipeline_total_ms": {
            "media": round(statistics.mean(lat_total_ms), 2) if lat_total_ms else None,
            "p50": round(statistics.median(lat_total_ms), 2) if lat_total_ms else None,
            "p95": _p95(lat_total_ms),
        },
        "resultados": resultados,
    }

    out_json = EVIDENCIAS_DIR / "reporte_m4.json"
    out_json.write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumen, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
