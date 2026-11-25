"""Diagnóstico del entorno del backend Django (evidencia de entorno reproducible)."""
import json
import os
import platform
import sys

import cv2
import django


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    info = {
        "python": sys.version.split()[0],
        "plataforma": platform.platform(),
        "django": django.get_version(),
        "opencv": cv2.__version__,
    }
    print(json.dumps(info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
