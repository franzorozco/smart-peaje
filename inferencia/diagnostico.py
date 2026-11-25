"""Script de diagnóstico del entorno de inferencia (evidencia para entornos reproducibles)."""
import json
import platform
import sys

import cv2
import numpy as np
import onnxruntime as ort
import torch
import ultralytics

import config
from ocr_adapter import estado_m1


def main() -> None:
    try:
        import importlib.metadata as meta
        fast_ocr_ver = meta.version("fast-plate-ocr")
    except Exception:
        fast_ocr_ver = "desconocida"

    cuda_ok = bool(torch.cuda.is_available())
    gpu_name = torch.cuda.get_device_name(0) if cuda_ok else None
    archivos_modelos = sorted(
        f.name for f in config.MODELOS_DIR.glob("*") if f.is_file()
    ) if config.MODELOS_DIR.is_dir() else []

    info = {
        "python": sys.version.split()[0],
        "plataforma": platform.platform(),
        "torch": torch.__version__,
        "cuda_disponible": cuda_ok,
        "cuda_version": getattr(torch.version, "cuda", None),
        "gpu_nombre": gpu_name,
        "ultralytics": ultralytics.__version__,
        "onnxruntime": ort.__version__,
        "onnx_providers": ort.get_available_providers(),
        "opencv": cv2.__version__,
        "numpy": np.__version__,
        "fast_plate_ocr": fast_ocr_ver,
        "modelos_dir": str(config.MODELOS_DIR),
        "m2_model_path": str(config.M2_MODEL_PATH),
        "m3_model_path": str(config.M3_MODEL_PATH),
        "m4_model_path": str(config.M4_MODEL_PATH),
        "modelos_presentes": archivos_modelos,
        "m1_estado": estado_m1(),
        "inference_mode": config.INFERENCE_MODE,
        "max_ejes": config.MAX_EJES,
    }
    print(json.dumps(info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
