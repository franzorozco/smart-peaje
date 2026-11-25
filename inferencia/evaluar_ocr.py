"""Evalúa exactitud de M1 (placa completa) y latencias p50/p95 sobre imágenes etiquetadas como <PLACA>.jpg."""
import argparse
import json
from pathlib import Path
import time

import cv2
import numpy as np

from ocr_adapter import inferir_placa_en, normalizar, precargar_m1

EXTENSIONES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def evaluar(carpeta: Path) -> dict:
    precargar_m1()
    imagenes = sorted(p for p in carpeta.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONES)
    if not imagenes:
        raise SystemExit(f"No se encontraron imágenes en {carpeta}")

    latencias: list[float] = []
    correctas = 0
    sin_lectura = 0
    errores: list[dict] = []

    for img_path in imagenes:
        esperada = normalizar(img_path.stem.split("_")[0])
        bgr = cv2.imread(str(img_path))
        if bgr is None:
            continue
        t0 = time.perf_counter()
        res = inferir_placa_en(bgr)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        latencias.append(dt_ms)

        obtenida = res.get("placa")
        if obtenida is None:
            sin_lectura += 1
        if obtenida == esperada:
            correctas += 1
        else:
            errores.append({
                "archivo": img_path.name,
                "esperada": esperada,
                "obtenida": obtenida,
                "placa_cruda": res.get("placa_cruda"),
                "confianza": res.get("confianza"),
                "latencia_ms": round(dt_ms, 2),
            })

    total = len(latencias)
    exactitud = (correctas / total * 100.0) if total else 0.0
    rechazo = (sin_lectura / total * 100.0) if total else 0.0
    p50 = float(np.percentile(latencias, 50)) if latencias else 0.0
    p95 = float(np.percentile(latencias, 95)) if latencias else 0.0

    return {
        "carpeta": str(carpeta),
        "total_imagenes": total,
        "correctas": correctas,
        "sin_lectura": sin_lectura,
        "exactitud_pct": round(exactitud, 2),
        "tasa_rechazo_pct": round(rechazo, 2),
        "latencia_p50_ms": round(p50, 2),
        "latencia_p95_ms": round(p95, 2),
        "errores": errores,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluar exactitud OCR (M1) sobre imágenes <PLACA>.jpg")
    parser.add_argument("carpeta", type=Path, help="Directorio con imágenes de prueba")
    args = parser.parse_args()
    resultado = evaluar(args.carpeta)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
