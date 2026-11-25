"""Extracción de frames desde clips MP4/MOV de 5 a 10 segundos enviados desde la app móvil."""
import os
from pathlib import Path
import tempfile

import cv2

EXTENSIONES_VIDEO = {".mp4", ".mov", ".3gp", ".webm", ".mkv", ".avi"}
MAX_CLIP_BYTES = 30 * 1024 * 1024


def es_video(upload) -> bool:
    ctype = (getattr(upload, "content_type", "") or "").lower()
    nombre = getattr(upload, "name", "") or ""
    ext = Path(nombre).suffix.lower()
    return ctype.startswith("video/") or ext in EXTENSIONES_VIDEO


def frames_de_clip(upload) -> list[bytes]:
    if upload.size > MAX_CLIP_BYTES:
        raise ValueError("Clip demasiado grande (máximo 30 MB).")

    ext = Path(getattr(upload, "name", "") or "clip.mp4").suffix.lower() or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        for chunk in upload.chunks():
            tmp.write(chunk)
        path = tmp.name

    try:
        cap = cv2.VideoCapture(path)
        try:
            if not cap.isOpened():
                raise ValueError("No se pudo abrir el clip de video.")
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = 0
            while cap.grab():
                total_frames += 1
        finally:
            cap.release()

        if fps <= 0 or total_frames <= 0:
            raise ValueError("Clip inválido; no se pudo determinar su duración.")

        duracion = total_frames / fps
        if not (4.5 <= duracion <= 10.5):
            raise ValueError("Clip inválido; usar una duración de 5 a 10 segundos.")

        objetivos = sorted({
            min(total_frames - 1, max(0, int((i + 0.5) * total_frames / 5)))
            for i in range(5)
        })
        objetivos_set = set(objetivos)

        frames_jpg: list[bytes] = []
        cap2 = cv2.VideoCapture(path)
        try:
            idx = 0
            while cap2.grab():
                if idx in objetivos_set:
                    ok, img = cap2.retrieve()
                    if ok and img is not None:
                        ok_enc, buf = cv2.imencode(".jpg", img)
                        if ok_enc:
                            frames_jpg.append(buf.tobytes())
                idx += 1
                if idx > max(objetivos):
                    break
        finally:
            cap2.release()

        if not frames_jpg:
            raise ValueError("No se pudieron extraer frames válidos del clip.")
        return frames_jpg
    finally:
        if os.path.exists(path):
            os.unlink(path)
