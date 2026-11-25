"""Descarga los pesos privados vehiculos.pt y ejes.pt si no existen en modelos/."""
from pathlib import Path
import os
import sys

import gdown
import requests

import config


def _es_gdrive(url: str) -> bool:
    return "drive.google.com" in url or "docs.google.com" in url


def _descargar(url: str, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    print(f"Descargando {destino.name} desde {url} ...")
    if _es_gdrive(url):
        resultado = gdown.download(url=url, output=str(destino), quiet=False, fuzzy=True)
        if not resultado or not destino.is_file():
            raise RuntimeError(f"No se pudo descargar desde Google Drive: {url}")
        return

    with requests.get(url, stream=True, timeout=(10, 120)) as resp:
        resp.raise_for_status()
        with destino.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)


def main() -> int:
    objetivos = [
        ("M2_URL", config.M2_MODEL_PATH),
        ("M3_URL", config.M3_MODEL_PATH),
        ("M4_URL", config.M4_MODEL_PATH),
    ]
    for env_var, destino in objetivos:
        url = os.environ.get(env_var, "").strip()
        if destino.is_file():
            print(f"[OK] {destino.name} ya existe en {destino}")
            continue
        if env_var == "M4_URL" and not url:
            # Descarga oficial de YOLOv8n-seg (COCO 2017 Segmentation) si no se define espejo privado
            url = "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n-seg.pt"
        if not url:
            print(f"[AVISO] {destino.name} no existe y {env_var} no está definida.")
            continue
        _descargar(url, destino)
        print(f"[OK] Guardado {destino} ({destino.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
