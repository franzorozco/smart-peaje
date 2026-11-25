"""Lee placas con Tesseract (entorno conda).

Uso: python placas_tesseract.py ruta/imagen.jpg

Configuración para lectura del cuerpo principal de la placa (Requisito 2):
1. Variables de entorno y rutas:
   - SystemRoot / windir: Imprescindibles en Windows para la inicialización correcta de subprocesos.
   - Detección robusta de Tesseract y tessdata en Conda:
     Laravel ejecuta python.exe directamente sin activar el entorno conda ("conda activate").
     Por tanto, configuramos explícitamente pytesseract.tesseract_cmd y TESSDATA_PREFIX
     verificando la existencia de "eng.traineddata" en share/tessdata y Library/share/tessdata.
2. Modo de segmentación de página (--psm 11):
   - PSM 7 asume una sola línea horizontal uniforme; falla cuando las placas tienen leyendas arriba/abajo.
   - PSM 6 asume un bloque de texto uniforme.
   - PSM 11 busca texto disperso sin un orden predefinido ("Sparse text"), lo cual es ideal
     para placas vehiculares de Bolivia donde la palabra "BOLIVIA" o el departamento está en una línea
     secundaria y los números y letras principales están en otra.
   - tessedit_char_whitelist: Limita los caracteres aceptados a A-Z y 0-9.
3. Preprocesamiento de imagen:
   - Canal de brillo (recorte.max(axis=2)): toma el canal de mayor intensidad en cada píxel,
     garantizando alto contraste entre caracteres oscuros y fondos reflectantes o coloreados (blanco, amarillo, azul).
   - Ampliación (fx=3, fy=3 con interpolación cúbica INTER_CUBIC): Tesseract trabaja con mayor precisión
     cuando la altura de los caracteres supera los 30-40 píxeles.
   - Filtro bilateral (bilateralFilter(9, 75, 75)): atenúa ruido e imperfecciones preservando bordes nítidos.
   - Binarización de Otsu (THRESH_BINARY + THRESH_OTSU): calcula automáticamente el umbral óptimo blanco/negro.
4. Umbral de altura del texto (UMBRAL_ALTURA = 0.6):
   - Se obtiene la altura de cada caja de texto detectada por Tesseract.
   - Se descartan aquellas cuya altura sea menor al 60% de la altura máxima (altura * 0.6).
   - Esto filtra leyendas accesorias ("BOLIVIA", "ANTIGUO", nombres de ciudades) dejando solo
     la combinación alfanumérica principal de la placa boliviana.
"""
import os
import sys

# Asegurar variables de entorno críticas en Windows
os.environ.setdefault("SystemRoot", os.environ.get("SystemRoot", r"C:\Windows"))
os.environ.setdefault("windir", os.environ.get("windir", r"C:\Windows"))

import json
import time
from pathlib import Path

import cv2
import pytesseract

from detector import detectar, leer_imagen, resultado

# Configuración de rutas para Conda en Windows y Linux sin activar entorno
PREFIJO = Path(sys.prefix)
if os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = str(PREFIJO / "Library" / "bin" / "tesseract.exe")
    carpetas = [
        PREFIJO / "share" / "tessdata",
        PREFIJO / "Library" / "share" / "tessdata",
    ]
else:
    pytesseract.pytesseract.tesseract_cmd = str(PREFIJO / "bin" / "tesseract")
    carpetas = [
        PREFIJO / "share" / "tessdata",
    ]

for carpeta in carpetas:
    if (carpeta / "eng.traineddata").is_file():
        os.environ["TESSDATA_PREFIX"] = str(carpeta)
        break

# Modo de segmentación: psm 11 (texto disperso para soportar placas multilínea)
# y lista blanca para evitar símbolos indeseados
CONFIGURACION = "--psm 11 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# Umbral de altura relativa para descartar leyendas secundarias (0.6 = 60% de la altura máxima)
UMBRAL_ALTURA = 0.6


def preparar(recorte):
    """Ampliación y binarización para optimizar la lectura de Tesseract.
    
    - Canal de brillo: extrae el valor máximo entre canales BGR para máximo contraste.
    - Interpolación cúbica: escala x3 para dotar a las letras de mayor resolución.
    - Filtro bilateral: suaviza texturas metálicas o reflejos sin difuminar bordes.
    - Otsu: binariza la placa dejando texto negro sobre fondo blanco.
    """
    brillo = recorte.max(axis=2)
    brillo = cv2.resize(brillo, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    brillo = cv2.bilateralFilter(brillo, 9, 75, 75)
    _, binaria = cv2.threshold(brillo, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binaria


def caracteres_principales(datos):
    """Conserva solo el texto más alto: los caracteres principales de la placa.
    
    Descarta textos pequeños secundarios (ej. 'BOLIVIA', departamentos, 'ANTIGUO')
    utilizando el umbral de altura UMBRAL_ALTURA (0.6).
    """
    palabras = [
        (datos["text"][i].strip(), datos["height"][i], float(datos["conf"][i]))
        for i in range(len(datos["text"]))
        if datos["text"][i].strip()
    ]
    if not palabras:
        return "", None

    altura_max = max(alto for _, alto, _ in palabras)
    elegidas = [(texto, conf) for texto, alto, conf in palabras if alto >= altura_max * UMBRAL_ALTURA]
    confianzas = [conf for _, conf in elegidas if conf > 0]

    texto_final = "".join(texto for texto, _ in elegidas)
    confianza_promedio = (sum(confianzas) / len(confianzas) / 100) if confianzas else None

    return texto_final, confianza_promedio


def principal():
    if len(sys.argv) != 2:
        sys.exit("Uso: python placas_tesseract.py ruta/imagen.jpg")

    inicio = time.perf_counter()
    imagen = leer_imagen(sys.argv[1])
    cajas = detectar(imagen)

    textos, confianzas = [], []
    for x1, y1, x2, y2, _ in cajas:
        binaria = preparar(imagen[y1:y2, x1:x2])
        datos = pytesseract.image_to_data(
            binaria,
            lang="eng",
            config=CONFIGURACION,
            output_type=pytesseract.Output.DICT,
        )
        texto, confianza = caracteres_principales(datos)
        textos.append(texto)
        confianzas.append(confianza)

    placas, anotada = resultado(imagen, cajas, textos, confianzas, nombre_motor="Tesseract OCR (PSM 11)")
    print(json.dumps({
        "lector": "Tesseract OCR",
        "placas": placas,
        "imagen": anotada,
        "python": sys.version.split()[0],
        "ejecutable": sys.executable,
        "libreria": f"Tesseract {pytesseract.get_tesseract_version()}",
        "milisegundos": round((time.perf_counter() - inicio) * 1000),
    }))


if __name__ == "__main__":
    principal()
