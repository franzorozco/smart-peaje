"""Lee placas con EasyOCR (entorno mamba).

Uso: python placas_easyocr.py ruta/imagen.jpg
Los modelos de EasyOCR residen en modelo/easyocr.

Configuración para lectura del cuerpo principal de la placa (Requisito 2):
1. Variables de entorno:
   - SystemRoot / windir: Imprescindibles en Windows para inicializar Winsock sin error WinError 10106.
   - KMP_DUPLICATE_LIB_OK: Permite la convivencia de runtimes OpenMP (PyTorch + OpenCV en Windows).
2. allowlist = PERMITIDOS: Limita la salida exclusivamente a dígitos (0-9) y letras mayúsculas (A-Z),
   evitando caracteres especiales o ruidos de fondo.
3. Umbral de altura relativa (UMBRAL_ALTURA = 0.6):
   Se calcula la altura (y_max - y_min) de cada bloque detectado por EasyOCR.
   Los textos con altura < maxima * 0.6 se descartan automáticamente.
   Esto permite conservar los caracteres grandes del número de placa y eliminar leyendas secundarias
   como "BOLIVIA", departamentos ("LA PAZ", "COCHABAMBA", "SANTA CRUZ") o palabras como "ANTIGUO".
4. Ordenamiento horizontal:
   Se ordenan los caracteres de izquierda a derecha usando la coordenada x inicial (l[0][0][0]).
"""
import os
import sys

# Asegurar variables de entorno críticas en Windows para Winsock y PyTorch/OpenMP
os.environ.setdefault("SystemRoot", os.environ.get("SystemRoot", r"C:\Windows"))
os.environ.setdefault("windir", os.environ.get("windir", r"C:\Windows"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import json
import time
import warnings

warnings.filterwarnings("ignore")

import easyocr  # noqa: E402

from detector import CARPETA, detectar, leer_imagen, resultado

# Solo letras mayúsculas y números (sin espacios ni símbolos)
PERMITIDOS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# Umbral de altura relativa para descartar leyendas secundarias
# 0.6 significa que el texto debe tener al menos el 60% de la altura del texto más alto
UMBRAL_ALTURA = 0.6


def principal():
    if len(sys.argv) != 2:
        sys.exit("Uso: python placas_easyocr.py ruta/imagen.jpg")

    inicio = time.perf_counter()
    imagen = leer_imagen(sys.argv[1])
    cajas = detectar(imagen)
    lector = easyocr.Reader(
        ["en"],
        gpu=False,
        verbose=False,
        model_storage_directory=str(CARPETA / "easyocr"),
    )

    textos, confianzas = [], []
    for x1, y1, x2, y2, _ in cajas:
        recorte = imagen[y1:y2, x1:x2]
        lecturas = lector.readtext(recorte, allowlist=PERMITIDOS)

        # Filtro de leyendas secundarias por altura relativa
        if lecturas:
            altura = lambda l: max(p[1] for p in l[0]) - min(p[1] for p in l[0])
            maxima = max(altura(l) for l in lecturas)
            # Conservamos solo aquellos bloques con al menos el 60% de la altura máxima
            lecturas = [l for l in lecturas if altura(l) >= maxima * UMBRAL_ALTURA]

        # Ordenar de izquierda a derecha por coordenada x de la esquina superior izquierda
        lecturas.sort(key=lambda l: l[0][0][0])
        textos.append("".join(texto for _, texto, _ in lecturas))
        confianzas.append(sum(c for _, _, c in lecturas) / len(lecturas) if lecturas else None)

    placas, anotada = resultado(imagen, cajas, textos, confianzas, nombre_motor="EasyOCR (PyTorch CRNN)")
    print(json.dumps({
        "lector": "EasyOCR (red CRNN en PyTorch)",
        "placas": placas,
        "imagen": anotada,
        "python": sys.version.split()[0],
        "ejecutable": sys.executable,
        "libreria": f"EasyOCR {easyocr.__version__}",
        "milisegundos": round((time.perf_counter() - inicio) * 1000),
    }))


if __name__ == "__main__":
    principal()
