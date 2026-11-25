"""Detector de placas compartido por los tres entornos (YOLOv9-t en ONNX).

Cada script de lectura importa este archivo, así los tres usan las mismas cajas.
"""
import os
import sys

# Asegurar variables de entorno críticas en Windows para Winsock y OpenMP
os.environ.setdefault("SystemRoot", os.environ.get("SystemRoot", r"C:\Windows"))
os.environ.setdefault("windir", os.environ.get("windir", r"C:\Windows"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import base64
import re
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

CARPETA = Path(__file__).parent / "modelo"
MODELO = CARPETA / "yolo-v9-t-384-license-plates-end2end.onnx"
LADO = 384
FORMATO_BOLIVIA = re.compile(r"^\d{3,4}[A-Z]{3}$")


def leer_imagen(ruta):
    imagen = cv2.imread(str(ruta))
    if imagen is None:
        raise SystemExit("No se pudo leer la imagen.")
    return imagen


def detectar(imagen, umbral=0.25):
    """Devuelve una lista de (x1, y1, x2, y2, confianza) en coordenadas de la imagen original."""
    alto, ancho = imagen.shape[:2]
    escala = min(LADO / alto, LADO / ancho)
    nuevo_ancho, nuevo_alto = round(ancho * escala), round(alto * escala)
    margen_x, margen_y = (LADO - nuevo_ancho) / 2, (LADO - nuevo_alto) / 2
    lienzo = cv2.resize(imagen, (nuevo_ancho, nuevo_alto), interpolation=cv2.INTER_LINEAR)
    lienzo = cv2.copyMakeBorder(
        lienzo, round(margen_y - 0.1), round(margen_y + 0.1), round(margen_x - 0.1), round(margen_x + 0.1),
        cv2.BORDER_CONSTANT, value=(114, 114, 114),
    )
    entrada = (lienzo[:, :, ::-1].transpose(2, 0, 1) / 255.0).astype(np.float32)[None]

    sesion = ort.InferenceSession(str(MODELO), providers=["CPUExecutionProvider"])
    salida = sesion.run(None, {sesion.get_inputs()[0].name: entrada})[0]

    cajas = []
    for _, x1, y1, x2, y2, _, confianza in salida:
        if confianza < umbral:
            continue
        x1, x2 = [(v - margen_x) / escala for v in (x1, x2)]
        y1, y2 = [(v - margen_y) / escala for v in (y1, y2)]
        cajas.append((
            int(max(0, x1)), int(max(0, y1)), int(min(ancho, x2)), int(min(alto, y2)), float(confianza),
        ))
    return cajas


def limpiar(texto):
    return re.sub(r"[^A-Z0-9]", "", texto.upper())


def resultado(imagen, cajas, textos, confianzas_lectura, nombre_motor=""):
    """Dibuja las cajas, inserta banner con el nombre del motor y arma la lista de placas para el JSON."""
    placas = []
    copia_anotada = imagen.copy()
    alto_img, ancho_img = copia_anotada.shape[:2]

    # Nombre corto y color temático por motor
    nombre_lower = (nombre_motor or "").lower()
    if "fast" in nombre_lower:
        motor_corto = "fast-plate-ocr"
        color_motor = (255, 180, 0)
    elif "tesseract" in nombre_lower:
        motor_corto = "Tesseract OCR"
        color_motor = (50, 220, 100)
    elif "easy" in nombre_lower:
        motor_corto = "EasyOCR"
        color_motor = (240, 220, 50)
    else:
        motor_corto = nombre_motor or "Motor de Inferencia"
        color_motor = (0, 255, 255)

    # 1. Dibujar banner superior permanente en la imagen con el nombre del motor
    banner_alto = max(45, int(alto_img * 0.055))
    overlay = copia_anotada.copy()
    cv2.rectangle(overlay, (0, 0), (ancho_img, banner_alto), (15, 20, 25), -1)
    cv2.addWeighted(overlay, 0.88, copia_anotada, 0.12, 0, copia_anotada)
    cv2.line(copia_anotada, (0, banner_alto), (ancho_img, banner_alto), (0, 200, 0), 2)

    font_scale = max(0.55, min(0.95, ancho_img / 1200))

    # Título del motor de inferencia impreso en la imagen
    titulo_motor = f"MOTOR: {motor_corto.upper()}"
    cv2.putText(
        copia_anotada,
        titulo_motor,
        (15, int(banner_alto * 0.68)),
        cv2.FONT_HERSHEY_DUPLEX,
        font_scale,
        color_motor,
        2,
        cv2.LINE_AA,
    )

    # Resumen de placa impresa en la imagen a la derecha del banner
    textos_validos = [limpiar(t) for t in textos if t]
    texto_resumen = ", ".join(textos_validos) if textos_validos else "(SIN LECTURA)"
    etiqueta_resumen = f"PLACA: {texto_resumen}"
    (w_res, _), _ = cv2.getTextSize(etiqueta_resumen, cv2.FONT_HERSHEY_DUPLEX, font_scale, 2)
    pos_x_res = max(ancho_img - w_res - 20, 300)
    cv2.putText(
        copia_anotada,
        etiqueta_resumen,
        (pos_x_res, int(banner_alto * 0.68)),
        cv2.FONT_HERSHEY_DUPLEX,
        font_scale,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    # 2. Dibujar recuadro de la placa con etiqueta del motor y texto
    for (x1, y1, x2, y2, confianza), texto, lectura in zip(cajas, textos, confianzas_lectura):
        texto = limpiar(texto)
        etiqueta = f"{motor_corto}: {texto or '?'}"

        cv2.rectangle(copia_anotada, (x1, y1), (x2, y2), (0, 220, 0), 3)

        (w_txt, h_txt), _ = cv2.getTextSize(etiqueta, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)
        y_label_bottom = max(y1, banner_alto + h_txt + 12)
        y_label_top = y_label_bottom - h_txt - 10
        cv2.rectangle(copia_anotada, (x1, y_label_top), (x1 + w_txt + 12, y_label_bottom), (0, 160, 0), -1)
        cv2.putText(copia_anotada, etiqueta, (x1 + 6, y_label_bottom - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)

        pad_y = max(15, int((y2 - y1) * 0.35))
        pad_x = max(20, int((x2 - x1) * 0.25))
        ry1, ry2 = max(0, y1 - pad_y), min(alto_img, y2 + pad_y)
        rx1, rx2 = max(0, x1 - pad_x), min(ancho_img, x2 + pad_x)
        recorte_placa = copia_anotada[ry1:ry2, rx1:rx2]
        recorte_b64 = base64.b64encode(cv2.imencode(".jpg", recorte_placa, [cv2.IMWRITE_JPEG_QUALITY, 90])[1]).decode()

        placas.append({
            "texto": texto,
            "caracteres": list(texto),
            "total_caracteres": len(texto),
            "formato_bolivia": bool(FORMATO_BOLIVIA.match(texto)),
            "confianza_deteccion": round(confianza * 100, 1),
            "confianza_lectura": None if lectura is None else round(float(lectura) * 100, 1),
            "caja": [x1, y1, x2, y2],
            "recorte": "data:image/jpeg;base64," + recorte_b64,
            "motor": motor_corto,
        })

    anotada = base64.b64encode(cv2.imencode(".jpg", copia_anotada, [cv2.IMWRITE_JPEG_QUALITY, 85])[1]).decode()
    return placas, "data:image/jpeg;base64," + anotada
