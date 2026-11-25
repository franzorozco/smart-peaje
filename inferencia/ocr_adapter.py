"""Adaptador de M1 (detección de placas + OCR) sobre el código existente en /placas/."""
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import cv2
import numpy as np
import onnxruntime as ort
from fast_plate_ocr import LicensePlateRecognizer

import config

ROOT = Path(__file__).resolve().parents[1]
PLACAS_DIR = ROOT / "placas"
if str(PLACAS_DIR) not in sys.path:
    sys.path.insert(0, str(PLACAS_DIR))

import detector  # noqa: E402

PATRON_PLACA = re.compile(r"^\d{3,4}[A-Z]{3}$")


def normalizar(texto: str) -> str:
    """Normaliza la lectura a mayúsculas alfanuméricas sin espacios ni guiones."""
    return re.sub(r"[^A-Z0-9]", "", (texto or "").upper())


def formato_valido(texto: str) -> bool:
    """Valida el formato de placa boliviana esperado (3-4 dígitos + 3 letras)."""
    return bool(PATRON_PLACA.fullmatch(texto or ""))


@lru_cache(maxsize=1)
def _get_detector_session() -> ort.InferenceSession:
    modelo_path = Path(detector.MODELO)
    if not modelo_path.is_file():
        raise FileNotFoundError(f"No existe el detector ONNX en {modelo_path}")
    disponibles = set(ort.get_available_providers())
    providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in disponibles]
    if not providers:
        providers = ["CPUExecutionProvider"]
    return ort.InferenceSession(str(modelo_path), providers=providers)


@lru_cache(maxsize=1)
def _get_recognizer() -> LicensePlateRecognizer:
    onnx_path = Path(detector.CARPETA) / "cct_xs_v2_global.onnx"
    cfg_path = Path(detector.CARPETA) / "cct_xs_v2_global_plate_config.yaml"
    if not onnx_path.is_file() or not cfg_path.is_file():
        raise FileNotFoundError(f"Faltan archivos de fast-plate-ocr en {detector.CARPETA}")
    return LicensePlateRecognizer(
        onnx_model_path=onnx_path,
        plate_config_path=cfg_path,
    )


def precargar_m1() -> dict[str, bool]:
    """Inicializa y verifica que los modelos ONNX de M1 carguen correctamente."""
    det_ok = False
    ocr_ok = False
    try:
        _get_detector_session()
        det_ok = True
    except Exception:
        det_ok = False
    try:
        _get_recognizer()
        ocr_ok = True
    except Exception:
        ocr_ok = False
    return {"m1_detector": det_ok, "m1_ocr": ocr_ok}


def estado_m1() -> dict[str, bool]:
    """Devuelve si el detector y el OCR de M1 están disponibles."""
    det_path = Path(detector.MODELO)
    ocr_path = Path(detector.CARPETA) / "cct_xs_v2_global.onnx"
    cfg_path = Path(detector.CARPETA) / "cct_xs_v2_global_plate_config.yaml"
    return {
        "m1_detector": det_path.is_file(),
        "m1_ocr": ocr_path.is_file() and cfg_path.is_file(),
    }


def localizar_placas(bgr: np.ndarray, umbral: float | None = None) -> list[tuple[int, int, int, int, float]]:
    """Detecta cajas de placas en BGR reutilizando el preproceso YOLOv9-t de /placas/detector.py."""
    if bgr is None or bgr.size == 0:
        return []
    umbral_real = config.PLACA_CONF if umbral is None else umbral
    alto, ancho = bgr.shape[:2]
    lado = int(detector.LADO)
    escala = min(lado / alto, lado / ancho)
    nuevo_ancho, nuevo_alto = round(ancho * escala), round(alto * escala)
    margen_x, margen_y = (lado - nuevo_ancho) / 2, (lado - nuevo_alto) / 2
    lienzo = cv2.resize(bgr, (nuevo_ancho, nuevo_alto), interpolation=cv2.INTER_LINEAR)
    lienzo = cv2.copyMakeBorder(
        lienzo,
        round(margen_y - 0.1),
        round(margen_y + 0.1),
        round(margen_x - 0.1),
        round(margen_x + 0.1),
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )
    entrada = (lienzo[:, :, ::-1].transpose(2, 0, 1) / 255.0).astype(np.float32)[None]
    sesion = _get_detector_session()
    salida = sesion.run(None, {sesion.get_inputs()[0].name: entrada})[0]

    cajas: list[tuple[int, int, int, int, float]] = []
    for fila in salida:
        _, x1, y1, x2, y2, _, confianza = fila
        if float(confianza) < umbral_real:
            continue
        x1, x2 = [(v - margen_x) / escala for v in (x1, x2)]
        y1, y2 = [(v - margen_y) / escala for v in (y1, y2)]
        ix1 = int(max(0, x1))
        iy1 = int(max(0, y1))
        ix2 = int(min(ancho, x2))
        iy2 = int(min(alto, y2))
        if ix2 > ix1 and iy2 > iy1:
            cajas.append((ix1, iy1, ix2, iy2, float(confianza)))

    cajas.sort(key=lambda c: c[4], reverse=True)
    return cajas


def leer_placa(recorte_bgr: np.ndarray) -> dict:
    """Lee texto y confianza de un recorte BGR usando fast-plate-ocr sin inventar métricas."""
    if recorte_bgr is None or recorte_bgr.size == 0:
        return {"placa": None, "confianza": None}
    rgb = cv2.cvtColor(recorte_bgr, cv2.COLOR_BGR2RGB)
    prediccion = _get_recognizer().run_one(rgb, return_confidence=True)
    texto = normalizar(getattr(prediccion, "plate", "") or "")
    char_probs = getattr(prediccion, "char_probs", None)
    confianza = None
    if char_probs is not None and len(char_probs) > 0:
        confianza = round(float(char_probs.mean()), 4)
    return {"placa": texto or None, "confianza": confianza}


def candidatos_placa(bgr: np.ndarray) -> list[tuple[list[int], np.ndarray]]:
    """Respaldo geométrico por contornos cuando el detector ONNX no encuentra cajas."""
    if bgr is None or bgr.size == 0:
        return []
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.bilateralFilter(gray, 9, 75, 75), 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    out: list[tuple[list[int], np.ndarray]] = []
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:40]:
        x, y, w, h = cv2.boundingRect(c)
        if h and 2.0 <= w / h <= 6.0 and w >= 65 and h >= 16:
            out.append(([x, y, x + w, y + h], bgr[y : y + h, x : x + w]))
    return out[:8]


def inferir_placa_en(bgr: np.ndarray) -> dict:
    """Localiza y lee la placa en una imagen BGR, validando el formato y preservando placa_cruda."""
    if bgr is None or bgr.size == 0:
        return {
            "placa": None,
            "placa_cruda": None,
            "confianza": None,
            "caja": None,
            "confianza_deteccion": None,
        }

    cajas = localizar_placas(bgr)
    mejor_cruda: str | None = None
    mejor_conf: float | None = None
    mejor_caja: list[int] | None = None
    mejor_det_conf: float | None = None

    def _actualizar_respaldo(res: dict, caja: list[int] | None, det_conf: float | None) -> None:
        nonlocal mejor_cruda, mejor_conf, mejor_caja, mejor_det_conf
        raw = res.get("placa")
        if not raw:
            return
        conf_val = res.get("confianza") or 0.0
        if mejor_cruda is None or conf_val > (mejor_conf or 0.0):
            mejor_cruda = raw
            mejor_conf = res.get("confianza")
            mejor_caja = caja
            mejor_det_conf = det_conf

    for x1, y1, x2, y2, det_conf in cajas:
        recorte = bgr[y1:y2, x1:x2]
        res = leer_placa(recorte)
        caja = [x1, y1, x2, y2]
        det_round = round(det_conf, 4)
        _actualizar_respaldo(res, caja, det_round)
        if res["placa"] and formato_valido(res["placa"]):
            return {
                "placa": res["placa"],
                "placa_cruda": res["placa"],
                "confianza": res["confianza"],
                "caja": caja,
                "confianza_deteccion": det_round,
            }

    if not cajas:
        alto, ancho = bgr.shape[:2]
        if alto > 0 and 1.8 <= (ancho / alto) <= 6.0:
            res = leer_placa(bgr)
            caja_completa = [0, 0, ancho, alto]
            _actualizar_respaldo(res, caja_completa, None)
            if res["placa"] and formato_valido(res["placa"]):
                return {
                    "placa": res["placa"],
                    "placa_cruda": res["placa"],
                    "confianza": res["confianza"],
                    "caja": caja_completa,
                    "confianza_deteccion": None,
                }
        else:
            for caja_c, crop in candidatos_placa(bgr):
                res = leer_placa(crop)
                _actualizar_respaldo(res, caja_c, None)
                if res["placa"] and formato_valido(res["placa"]):
                    return {
                        "placa": res["placa"],
                        "placa_cruda": res["placa"],
                        "confianza": res["confianza"],
                        "caja": caja_c,
                        "confianza_deteccion": None,
                    }

    return {
        "placa": None,
        "placa_cruda": mejor_cruda,
        "confianza": mejor_conf,
        "caja": mejor_caja,
        "confianza_deteccion": mejor_det_conf,
    }
