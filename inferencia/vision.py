"""Motor unificado de visión por computadora: M1 (placas/OCR), M2 (segmentación), M3 (keypoints/ejes) y pasajeros."""
import base64
import json
import logging
import threading
import unicodedata
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

import config
from ocr_adapter import estado_m1, inferir_placa_en, precargar_m1

logger = logging.getLogger("inferencia.vision")


class ModeloNoDisponible(RuntimeError):
    """Excepción lanzada en modo real cuando falta un modelo obligatorio."""


_LOAD_LOCK = threading.Lock()
_PREDICT_LOCK = threading.Lock()
_MODELS: dict[str, YOLO | None] = {
    "seg": None,
    "pose": None,
    "pasajeros": None,
}
_MANIFESTS: dict[str, dict | None] = {
    "m2": None,
    "m3": None,
    "m4": None,
}
_LOAD_ERRORS: dict[str, str | None] = {
    "m2": None,
    "m3": None,
    "m4": None,
}
_LOADED = False

# Paleta BGR por categoría vehicular para visualizar máscaras y cajas
COLORES_CATEGORIA: dict[str, tuple[int, int, int]] = {
    "auto": (34, 197, 94),       # verde
    "bus": (235, 130, 50),       # azul claro
    "camion": (0, 165, 255),     # naranja
    "minibus": (210, 180, 0),    # cian/turquesa
    "moto": (220, 90, 230),      # violeta/magenta
}

# Categorías livianas donde >2 ejes es físicamente inconsistente y dispara revisión
CATEGORIAS_DOS_EJES = {"moto", "auto", "minibus"}


def resolver_dispositivo() -> int | str:
    """Selecciona GPU 0 si CUDA está disponible (en modo auto) o el dispositivo configurado."""
    if config.INFERENCE_DEVICE == "auto":
        return 0 if torch.cuda.is_available() else "cpu"
    if config.INFERENCE_DEVICE.isdigit():
        return int(config.INFERENCE_DEVICE)
    return config.INFERENCE_DEVICE


def normalizar_categoria(nombre: str) -> str:
    """Normaliza la etiqueta de clase entregada por M2 a moto|auto|minibus|camion|bus."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", (nombre or "").strip().lower())
        if unicodedata.category(c) != "Mn"
    )
    limpio = sin_acentos.replace("-", " ").replace("_", " ").strip()
    if limpio in ("minibus", "mini bus"):
        return "minibus"
    if limpio in ("camion", "truck"):
        return "camion"
    if limpio in ("auto", "car", "sedan", "suv", "hatchback"):
        return "auto"
    if limpio in ("moto", "motocicleta", "motorcycle"):
        return "moto"
    if limpio in ("bus", "autobus"):
        return "bus"
    return limpio or "auto"


def _leer_manifiesto(ruta: Path) -> dict | None:
    if not ruta.is_file():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("No se pudo leer manifiesto %s: %s", ruta, exc)
        return None


def _cargar_yolo_validado(
    ruta: Path,
    manifest_path: Path,
    clave: str,
    tarea_esperada: str,
    kpt_shape_esperado: list[int] | None = None,
) -> YOLO | None:
    _MANIFESTS[clave] = _leer_manifiesto(manifest_path)
    if not ruta.is_file():
        _LOAD_ERRORS[clave] = f"Archivo de pesos no encontrado: {ruta}"
        logger.warning("%s", _LOAD_ERRORS[clave])
        return None
    try:
        modelo = YOLO(str(ruta))
    except Exception as exc:
        _LOAD_ERRORS[clave] = f"Error al cargar {ruta.name}: {exc}"
        logger.exception("Error cargando modelo %s: %s", ruta, exc)
        return None

    if getattr(modelo, "task", None) != tarea_esperada:
        _LOAD_ERRORS[clave] = (
            f"Tarea incompatible en {ruta.name}: esperada '{tarea_esperada}', "
            f"encontrada '{getattr(modelo, 'task', None)}'"
        )
        logger.error("%s", _LOAD_ERRORS[clave])
        return None

    if kpt_shape_esperado is not None:
        kshape = list(getattr(modelo.model, "kpt_shape", []) or [])
        if kshape != kpt_shape_esperado:
            _LOAD_ERRORS[clave] = (
                f"kpt_shape incompatible en {ruta.name}: esperado {kpt_shape_esperado}, encontrado {kshape}"
            )
            logger.error("%s", _LOAD_ERRORS[clave])
            return None

    manifest = _MANIFESTS[clave]
    if manifest:
        clases_man_raw = manifest.get("classes") or manifest.get("names")
        if isinstance(clases_man_raw, dict):
            clases_peso = {str(k): str(v) for k, v in (modelo.names or {}).items()}
            clases_man = {str(k): str(v) for k, v in clases_man_raw.items()}
            if clases_peso != clases_man:
                logger.warning(
                    "Discrepancia de clases entre %s (%s) y manifiesto (%s)",
                    ruta.name, clases_peso, clases_man,
                )

    _LOAD_ERRORS[clave] = None
    return modelo


def _cargar_pasajeros() -> YOLO | None:
    """Carga M4 (YOLOv8n-seg COCO, exclusivamente clase person ID 0) una sola vez al iniciar."""
    if not config.PASAJEROS:
        _LOAD_ERRORS["m4"] = "M4 deshabilitado por configuración (M4_HABILITADO=0)"
        return None
    modelo = _cargar_yolo_validado(
        config.M4_MODEL_PATH,
        config.M4_MANIFEST_PATH,
        "m4",
        "segment",
    )
    if modelo is None:
        return None
    nombres = getattr(modelo, "names", {}) or {}
    clase_0 = str(nombres.get(0, "")).strip().lower()
    if clase_0 != "person":
        _LOAD_ERRORS["m4"] = f"Clase ID 0 incompatible en {config.M4_MODEL_PATH.name}: esperada 'person', encontrada '{clase_0}'"
        logger.error("%s", _LOAD_ERRORS["m4"])
        return None
    return modelo


def _es_modelo_llantas(pose_model: YOLO | None) -> bool:
    """Detecta automáticamente si M3 detecta llantas individuales (p. ej. class 'llanta', kpt_shape [5,3])."""
    if pose_model is None:
        return False
    nombres = [str(v).strip().lower() for v in (getattr(pose_model, "names", {}) or {}).values()]
    return any(n in ("llanta", "llantas", "rueda", "ruedas", "wheel", "wheels", "tire", "tires") for n in nombres)


def cargar_modelos(forzar: bool = False) -> None:
    """Carga una sola vez (thread-safe) M1, M2, M3 y el modelo de pasajeros."""
    global _LOADED
    with _LOAD_LOCK:
        if _LOADED and not forzar:
            return
        precargar_m1()
        _MODELS["seg"] = _cargar_yolo_validado(
            config.M2_MODEL_PATH, config.M2_MANIFEST_PATH, "m2", "segment"
        )
        _MODELS["pose"] = _cargar_yolo_validado(
            config.M3_MODEL_PATH,
            config.M3_MANIFEST_PATH,
            "m3",
            "pose",
            kpt_shape_esperado=None,
        )
        _MODELS["pasajeros"] = _cargar_pasajeros()
        _LOADED = True


def estado_modelos() -> dict:
    """Devuelve el estado de disponibilidad de todos los modelos, manifiestos, umbrales y GPU."""
    m1 = precargar_m1() if _LOADED else estado_m1()
    seg = _MODELS["seg"]
    pose = _MODELS["pose"]
    seg_names = {str(k): str(v) for k, v in seg.names.items()} if seg is not None else {}
    pose_names = {str(k): str(v) for k, v in pose.names.items()} if pose is not None else {}
    pose_kpt_shape = list(getattr(pose.model, "kpt_shape", []) or []) if pose is not None else None
    man_m2 = _MANIFESTS.get("m2")
    man_m3 = _MANIFESTS.get("m3")
    man_m4 = _MANIFESTS.get("m4")
    pax = _MODELS["pasajeros"]

    return {
        "modo_ejecucion": config.INFERENCE_MODE,
        "modelos": {
            "m1_detector": m1["m1_detector"],
            "m1_ocr": m1["m1_ocr"],
            "m2_segmentacion": seg is not None,
            "m3_keypoints": pose is not None,
            "m4_pasajeros": pax is not None,
            "pasajeros": pax is not None,
        },
        "m2": {
            "cargado": seg is not None,
            "ruta": str(config.M2_MODEL_PATH),
            "clases": seg_names,
            "conf_umbral": config.CONF_M2,
            "iou_umbral": config.IOU_M2,
            "conf_cobro": config.CONF_M2_COBRO,
            "manifiesto": (
                {
                    "base_model": man_m2.get("base_model"),
                    "input_size": man_m2.get("input_size"),
                    "sha256": (man_m2.get("sha256") or "")[:16],
                    "box_mAP50": (man_m2.get("metrics_test") or {}).get("box_mAP50"),
                    "mask_mAP50": (man_m2.get("metrics_test") or {}).get("mask_mAP50"),
                }
                if man_m2
                else None
            ),
            "error": _LOAD_ERRORS.get("m2"),
        },
        "m3": {
            "cargado": pose is not None,
            "estado": "activo" if pose is not None else "pendiente_entrenamiento",
            "modo_m3": ("llantas" if _es_modelo_llantas(pose) else "vehiculo_ejes") if pose is not None else None,
            "ruta": str(config.M3_MODEL_PATH),
            "clases": pose_names,
            "kpt_shape": pose_kpt_shape,
            "kpt_shape_esperado": pose_kpt_shape or [config.MAX_EJES, 3],
            "conf_umbral": config.CONF_M3,
            "conf_keypoint": config.CONF_KEYPOINT,
            "iou_asociacion": config.IOU_ASOCIACION,
            "manifiesto": (
                {
                    "arquitectura": man_m3.get("arquitectura"),
                    "sha256": (man_m3.get("sha256") or "")[:16],
                    "mAP50_pose_test": (
                        (man_m3.get("metricas_pose_test") or man_m3.get("metricas_pose_val") or {}).get("metrics/mAP50(P)")
                    ),
                    "mAP50_95_pose_test": (
                        (man_m3.get("metricas_pose_test") or man_m3.get("metricas_pose_val") or {}).get("metrics/mAP50-95(P)")
                    ),
                    "exactitud_entre_detectados": ((man_m3.get("metricas_conteo_ejes") or {}).get("todas") or {}).get("exactitud_entre_detectados"),
                    "mae_detectados": ((man_m3.get("metricas_conteo_ejes") or {}).get("todas") or {}).get("mae_detectados"),
                }
                if man_m3
                else None
            ),
            "error": _LOAD_ERRORS.get("m3"),
        },
        "m4": {
            "cargado": pax is not None,
            "habilitado": config.PASAJEROS,
            "estado": "activo" if pax is not None else ("deshabilitado" if not config.PASAJEROS else "no_disponible"),
            "ruta": str(config.M4_MODEL_PATH),
            "clase_activa": {"0": "person"},
            "conf_umbral": config.CONF_M4,
            "iou_umbral": config.IOU_M4,
            "min_overlap_vehiculo": config.M4_MIN_OVERLAP_VEH,
            "min_overlap_cabina": config.M4_MIN_OVERLAP_CABINA,
            "manifiesto": (
                {
                    "arquitectura": man_m4.get("arquitectura"),
                    "pesos_origen": man_m4.get("pesos_origen"),
                    "fuente_oficial": man_m4.get("fuente_oficial"),
                    "sha256": (man_m4.get("sha256") or "")[:16],
                }
                if man_m4
                else None
            ),
            "error": _LOAD_ERRORS.get("m4"),
        },
        "clases_m2": list(seg_names.values()),
        "kpt_shape_esperado": [config.MAX_EJES, 3],
        "gpu": bool(torch.cuda.is_available()),
        "dispositivo": str(resolver_dispositivo()),
        "demo": config.INFERENCE_MODE == "mock",
    }


def calcular_iou(box_a: list[int] | tuple[int, int, int, int], box_b: list[int] | tuple[int, int, int, int]) -> float:
    """Calcula Intersection-over-Union (IoU) entre dos cajas [x1, y1, x2, y2]."""
    ix1 = max(box_a[0], box_b[0])
    iy1 = max(box_a[1], box_b[1])
    ix2 = min(box_a[2], box_b[2])
    iy2 = min(box_a[3], box_b[3])
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1, (box_a[2] - box_a[0]) * (box_a[3] - box_a[1]))
    area_b = max(1, (box_b[2] - box_b[0]) * (box_b[3] - box_b[1]))
    return float(inter / (area_a + area_b - inter))


def _simplificar_poligono(poly: np.ndarray | None, max_puntos: int = 36) -> list[list[float]]:
    """Simplifica un polígono de máscara para devolverlo compacto en JSON."""
    if poly is None or len(poly) < 3:
        return []
    pts = np.asarray(poly, dtype=np.float32)
    if len(pts) > max_puntos:
        eps = 0.005 * cv2.arcLength(pts.reshape((-1, 1, 2)), True)
        aprox = cv2.approxPolyDP(pts.reshape((-1, 1, 2)), eps, True).reshape((-1, 2))
        if len(aprox) >= 3:
            pts = aprox
    if len(pts) > max_puntos:
        indices = np.linspace(0, len(pts) - 1, max_puntos, dtype=int)
        pts = pts[indices]
    return [[round(float(x), 1), round(float(y), 1)] for x, y in pts]


def _codificar_evidencia(img_bgr: np.ndarray) -> str:
    h, w = img_bgr.shape[:2]
    max_lado = max(h, w)
    if max_lado > 1280:
        escala = 1280.0 / max_lado
        img_bgr = cv2.resize(
            img_bgr,
            (max(1, int(w * escala)), max(1, int(h * escala))),
            interpolation=cv2.INTER_AREA,
        )
    ok, buf = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def _dibujar_evidencia_multi(
    bgr: np.ndarray,
    detalles_vehiculos: list[dict],
    principal: dict,
    modo_mock: bool,
) -> str:
    canvas = bgr.copy()
    h, w = canvas.shape[:2]
    banner_h = max(40, int(h * 0.06))

    for det in detalles_vehiculos:
        es_principal = det is principal
        color_veh = COLORES_CATEGORIA.get(det["categoria"], (34, 197, 94))

        # 1. Máscara semi-transparente de segmentación M2
        veh_poly = det.get("_veh_poly")
        if veh_poly is not None and len(veh_poly) >= 3:
            overlay = canvas.copy()
            pts = veh_poly.astype(np.int32).reshape((-1, 1, 2))
            cv2.fillPoly(overlay, [pts], color_veh)
            cv2.addWeighted(overlay, 0.28, canvas, 0.72, 0, canvas)
            cv2.polylines(canvas, [pts], True, color_veh, 2, cv2.LINE_AA)

        # 2. Privacidad de pasajeros (M4): máscaras opacas sólidas (sin rostros ni biometría)
        for occ in det.get("_pax_render", []):
            poly = occ.get("poly")
            pbox = occ.get("bbox")
            rol = occ.get("rol")
            color_fill = (200, 180, 0) if rol == "conductor_probable" else (11, 158, 245)
            color_borde = (120, 110, 0) if rol == "conductor_probable" else (0, 100, 180)
            tag_rol = "COND" if rol == "conductor_probable" else "PAX"
            if poly is not None and len(poly) >= 3:
                pts = poly.astype(np.int32).reshape((-1, 1, 2))
                cv2.fillPoly(canvas, [pts], color_fill)
                cv2.polylines(canvas, [pts], True, color_borde, 2, cv2.LINE_AA)
            elif pbox is not None:
                px1, py1, px2, py2 = pbox
                cv2.rectangle(canvas, (px1, py1), (px2, py2), color_fill, -1)
            if pbox is not None:
                px1, py1, px2, py2 = pbox
                cx_t = max(4, min(w - 48, px1))
                cy_t = max(banner_h + 18, py1 - 4)
                cv2.putText(
                    canvas, tag_rol, (cx_t, cy_t),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, color_fill, 2, cv2.LINE_AA,
                )

        # 3. Bounding box M2 + etiqueta categoría, confianza y ejes
        vx1, vy1, vx2, vy2 = det["bbox"]
        grosor = 3 if es_principal else 2
        cv2.rectangle(canvas, (vx1, vy1), (vx2, vy2), color_veh, grosor)
        conf_cat = det.get("confianza_categoria")
        conf_txt = f" {conf_cat * 100:.0f}%" if conf_cat is not None else ""
        ejes_obs = det.get("ejes_observados")
        ejes_badge = f" | {ejes_obs}E" if ejes_obs else ""
        etiqueta_veh = f"{det['id_deteccion']} {det['categoria'].upper()}{conf_txt}{ejes_badge}"
        (tw_l, th_l), _ = cv2.getTextSize(etiqueta_veh, cv2.FONT_HERSHEY_SIMPLEX, 0.56, 2)
        ly = max(banner_h + th_l + 10, vy1)
        cv2.rectangle(canvas, (vx1, ly - th_l - 8), (vx1 + tw_l + 10, ly), color_veh, -1)
        cv2.putText(
            canvas, etiqueta_veh, (vx1 + 5, ly - 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.56, (15, 23, 42), 2, cv2.LINE_AA,
        )

        # 4. Keypoints de ejes M3 numerados (1..7) conectados en orden frente -> atrás
        for ll in det.get("_llantas_vis", []):
            lx1, ly1, lx2, ly2 = [int(v) for v in ll["bbox"]]
            cv2.rectangle(canvas, (lx1, ly1), (lx2, ly2), (0, 215, 255), 1, cv2.LINE_AA)
            for rx, ry, rc in ll.get("rim_kpts", []):
                if rc >= 0.35 and (rx > 0 or ry > 0):
                    cv2.circle(canvas, (int(round(rx)), int(round(ry))), 3, (255, 255, 255), -1, cv2.LINE_AA)

        kpts_vis = det.get("_kpts_vis", [])
        if len(kpts_vis) >= 2:
            for p_a, p_b in zip(kpts_vis, kpts_vis[1:]):
                cv2.line(
                    canvas,
                    (int(round(p_a[1])), int(round(p_a[2]))),
                    (int(round(p_b[1])), int(round(p_b[2]))),
                    (0, 215, 255),
                    2,
                    cv2.LINE_AA,
                )
        for slot_idx, kx, ky, _kc in kpts_vis:
            cx, cy = int(round(kx)), int(round(ky))
            cv2.circle(canvas, (cx, cy), 8, (0, 215, 255), -1, cv2.LINE_AA)
            cv2.circle(canvas, (cx, cy), 10, (15, 23, 42), 2, cv2.LINE_AA)
            cv2.putText(
                canvas, f"e{slot_idx}", (cx + 10, cy - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 215, 255), 2, cv2.LINE_AA,
            )

        # 5. Caja y texto de placa asociada (M1)
        caja_p = det.get("_placa_caja")
        placa_txt = det.get("placa") or det.get("placa_cruda")
        if caja_p:
            px1, py1, px2, py2 = [int(v) for v in caja_p]
            cv2.rectangle(canvas, (px1, py1), (px2, py2), (255, 180, 0), 3)
            if placa_txt:
                cv2.putText(
                    canvas, placa_txt, (px1, max(24, py1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.68, (255, 180, 0), 2, cv2.LINE_AA,
                )

    # 6. Banner superior informativo
    cv2.rectangle(canvas, (0, 0), (w, banner_h), (15, 23, 42), -1)
    cv2.line(canvas, (0, banner_h), (w, banner_h), (34, 197, 94), 2)
    placa_label = principal.get("placa") or "SIN PLACA"
    est_e = principal.get("ejes_estado")
    if est_e == "pendiente_m3":
        ejes_label = "PENDIENTE(M3)"
    elif est_e == "confirmado":
        ejes_label = f"{principal['ejes']} (OK)"
    elif est_e == "pendiente_confirmacion":
        ejes_label = f"{principal['ejes_observados']} (REV)"
    else:
        ejes_label = "INCIERTO"
    pax_label = str(principal["pasajeros"]) if principal.get("pasajeros") is not None else "N/A"
    mock_tag = " [MOCK]" if modo_mock else ""
    multi_tag = f" | VEH {len(detalles_vehiculos)}" if len(detalles_vehiculos) > 1 else ""
    banner_txt = (
        f"PLACA {placa_label} | {principal['categoria'].upper()} | "
        f"EJES {ejes_label} | PASAJEROS {pax_label}{multi_tag}{mock_tag}"
    )
    font_scale = max(0.44, min(0.80, w / 1200.0))
    cv2.putText(
        canvas,
        banner_txt,
        (12, int(banner_h * 0.68)),
        cv2.FONT_HERSHEY_DUPLEX,
        font_scale,
        (248, 250, 252),
        2,
        cv2.LINE_AA,
    )
    return _codificar_evidencia(canvas)


def _persona_class_ids(model: YOLO) -> list[int]:
    """Devuelve exclusivamente la clase 'person' (ID 0 en COCO 2017 Segmentation)."""
    names = getattr(model, "names", {}) or {}
    if isinstance(names, dict) and str(names.get(0, "")).strip().lower() == "person":
        return [0]
    if isinstance(names, dict):
        ids = [int(k) for k, v in names.items() if str(v).lower() == "person"]
        if ids:
            return ids
    return [0]


def _region_cabina_vehiculo(
    bbox: list[int],
    categoria: str,
    h_img: int,
    w_img: int,
) -> tuple[int, int, int, int]:
    """Define la región interior visible (cabina / parabrisas / zona de jinete) del vehículo M2."""
    vx1, vy1, vx2, vy2 = bbox
    vw = max(1, vx2 - vx1)
    vh = max(1, vy2 - vy1)
    if categoria == "moto":
        cx1 = max(0, int(round(vx1 + 0.04 * vw)))
        cx2 = min(w_img, int(round(vx2 - 0.04 * vw)))
        cy1 = max(0, int(round(vy1 - 0.15 * vh)))
        cy2 = min(h_img, int(round(vy1 + 0.75 * vh)))
    elif categoria in ("bus", "minibus"):
        cx1 = max(0, int(round(vx1 + 0.05 * vw)))
        cx2 = min(w_img, int(round(vx2 - 0.05 * vw)))
        cy1 = max(0, int(round(vy1 + 0.10 * vh)))
        cy2 = min(h_img, int(round(vy1 + 0.62 * vh)))
    elif categoria == "camion":
        cx1 = max(0, int(round(vx1 + 0.05 * vw)))
        cx2 = min(w_img, int(round(vx2 - 0.05 * vw)))
        cy1 = max(0, int(round(vy1 + 0.10 * vh)))
        cy2 = min(h_img, int(round(vy1 + 0.58 * vh)))
    else:  # auto
        cx1 = max(0, int(round(vx1 + 0.06 * vw)))
        cx2 = min(w_img, int(round(vx2 - 0.06 * vw)))
        cy1 = max(0, int(round(vy1 + 0.08 * vh)))
        cy2 = min(h_img, int(round(vy1 + 0.62 * vh)))
    if cx2 <= cx1:
        cx1, cx2 = vx1, max(vx1 + 1, vx2)
    if cy2 <= cy1:
        cy1, cy2 = vy1, max(vy1 + 1, vy2)
    return cx1, cy1, cx2, cy2


def _evaluar_visibilidad_cabina(
    bgr: np.ndarray,
    veh_bbox: list[int],
    veh_poly: np.ndarray | None,
    categoria: str,
) -> tuple[bool, str, dict]:
    """Evalúa objetivamente si el interior de la cabina es visible para diferenciar 0 de null."""
    h_img, w_img = bgr.shape[:2]
    cx1, cy1, cx2, cy2 = _region_cabina_vehiculo(veh_bbox, categoria, h_img, w_img)
    cw, ch = max(1, cx2 - cx1), max(1, cy2 - cy1)

    if categoria == "moto":
        vw = max(1, veh_bbox[2] - veh_bbox[0])
        vh = max(1, veh_bbox[3] - veh_bbox[1])
        ok = vw >= 36 and vh >= 36
        return ok, ("cabina_abierta_moto" if ok else "cabina_pequena"), {
            "cabina_bbox": [cx1, cy1, cx2, cy2],
            "ancho_px": cw,
            "alto_px": ch,
            "brillo_medio": None,
            "contraste": None,
            "ratio_reflejo": None,
            "ratio_oscuro": None,
        }

    roi = bgr[cy1:cy2, cx1:cx2]
    if roi.size == 0 or cw < config.M4_MIN_CABIN_PX or ch < config.M4_MIN_CABIN_PX:
        return False, "cabina_pequena", {
            "cabina_bbox": [cx1, cy1, cx2, cy2],
            "ancho_px": cw,
            "alto_px": ch,
            "brillo_medio": None,
            "contraste": None,
            "ratio_reflejo": None,
            "ratio_oscuro": None,
        }

    # Máscara opcional dentro del polígono M2 para evitar fondo/cielo sobre el techo
    mask_local = np.ones((ch, cw), dtype=np.uint8)
    if veh_poly is not None and len(veh_poly) >= 3:
        m_poly = np.zeros((ch, cw), dtype=np.uint8)
        pts_rel = np.round(veh_poly - np.array([[cx1, cy1]], dtype=np.float32)).astype(np.int32)
        cv2.fillPoly(m_poly, [pts_rel.reshape((-1, 1, 2))], 1)
        if int(m_poly.sum()) >= max(100, int(0.15 * cw * ch)):
            mask_local = m_poly

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    s_ch = hsv[:, :, 1][mask_local > 0]
    v_ch = hsv[:, :, 2][mask_local > 0]
    if v_ch.size == 0:
        return False, "cabina_pequena", {
            "cabina_bbox": [cx1, cy1, cx2, cy2],
            "ancho_px": cw,
            "alto_px": ch,
            "brillo_medio": None,
            "contraste": None,
            "ratio_reflejo": None,
            "ratio_oscuro": None,
        }

    brillo = float(np.mean(v_ch))
    contraste = float(np.std(v_ch))
    ratio_reflejo = float(np.mean((v_ch > 235) & (s_ch < 35)))
    ratio_oscuro = float(np.mean(v_ch < 45))

    metricas = {
        "cabina_bbox": [cx1, cy1, cx2, cy2],
        "ancho_px": cw,
        "alto_px": ch,
        "brillo_medio": round(brillo, 1),
        "contraste": round(contraste, 1),
        "ratio_reflejo": round(ratio_reflejo, 4),
        "ratio_oscuro": round(ratio_oscuro, 4),
    }

    if ratio_oscuro > 0.65 or brillo < config.M4_MIN_BRILLO_CABINA or contraste < config.M4_MIN_CONTRASTE_CABINA:
        return False, "vidrio_polarizado_u_oscuro", metricas
    if ratio_reflejo > config.M4_MAX_REFLEJO_RATIO:
        return False, "reflejo_intenso", metricas
    return True, "cabina_visible", metricas


def _evaluar_ocupantes_m4(
    bgr: np.ndarray,
    cand: dict,
    pax_detecciones: list[tuple[tuple[int, int, int, int], np.ndarray | None, float]],
    placa_caja: list[int] | None,
) -> dict:
    """Asocia personas segmentadas (M4) con el interior del vehículo M2, excluye peatones y diferencia conductor/pasajeros."""
    h_img, w_img = bgr.shape[:2]
    vx1, vy1, vx2, vy2 = cand["bbox"]
    vw = max(1, vx2 - vx1)
    vh = max(1, vy2 - vy1)
    categoria = cand["categoria"]
    veh_poly = cand.get("veh_poly")

    cx1, cy1, cx2, cy2 = _region_cabina_vehiculo(cand["bbox"], categoria, h_img, w_img)
    cw, ch = max(1, cx2 - cx1), max(1, cy2 - cy1)

    # Lienzo local acotado al vehículo + margen superior (para motos) para medir solapamiento exacto de máscaras
    rx1 = max(0, min(vx1, cx1))
    ry1 = max(0, min(vy1, cy1))
    rx2 = min(w_img, max(vx2, cx2))
    ry2 = min(h_img, max(vy2, cy2))
    rw = max(1, rx2 - rx1)
    rh = max(1, ry2 - ry1)

    veh_mask = np.zeros((rh, rw), dtype=np.uint8)
    if veh_poly is not None and len(veh_poly) >= 3:
        pts_v = np.round(veh_poly - np.array([[rx1, ry1]], dtype=np.float32)).astype(np.int32)
        cv2.fillPoly(veh_mask, [pts_v.reshape((-1, 1, 2))], 1)
    else:
        veh_mask[vy1 - ry1 : vy2 - ry1, vx1 - rx1 : vx2 - rx1] = 1

    cab_mask = np.zeros((rh, rw), dtype=np.uint8)
    cab_mask[cy1 - ry1 : cy2 - ry1, cx1 - rx1 : cx2 - rx1] = 1

    ocupantes_raw: list[dict] = []
    peatones_descartados: list[dict] = []

    for pbox, p_poly, p_conf in pax_detecciones:
        px1, py1, px2, py2 = pbox
        # Filtro rápido de no intersección con la región ampliada del vehículo
        if px2 < rx1 or px1 > rx2 or py2 < ry1 or py1 > ry2:
            continue

        # Construir máscara de la persona en coordenadas locales
        p_mask = np.zeros((rh, rw), dtype=np.uint8)
        if p_poly is not None and len(p_poly) >= 3:
            pts_p = np.round(p_poly - np.array([[rx1, ry1]], dtype=np.float32)).astype(np.int32)
            cv2.fillPoly(p_mask, [pts_p.reshape((-1, 1, 2))], 1)
        else:
            ix1, iy1 = max(rx1, px1) - rx1, max(ry1, py1) - ry1
            ix2, iy2 = min(rx2, px2) - rx1, min(ry2, py2) - ry1
            if ix2 > ix1 and iy2 > iy1:
                p_mask[iy1:iy2, ix1:ix2] = 1

        # Área total estimada de la persona (en coordenadas globales para no inflar ratios si sobresale fuera del ROI)
        area_global = float(max(1, (px2 - px1) * (py2 - py1)))
        if p_poly is not None and len(p_poly) >= 3:
            area_poly = float(cv2.contourArea(p_poly.astype(np.float32)))
            if area_poly > 1.0:
                area_global = area_poly

        en_veh_px = float(np.count_nonzero(p_mask & veh_mask))
        en_cab_px = float(np.count_nonzero(p_mask & cab_mask))
        ratio_veh = min(1.0, en_veh_px / area_global)
        ratio_cab = min(1.0, en_cab_px / area_global)

        # Exclusión de peatones externos
        motivo_descarte: str | None = None
        if categoria == "moto":
            if ratio_cab < 0.22 and ratio_veh < 0.25:
                motivo_descarte = "fuera_zona_moto"
        else:
            if ratio_veh < config.M4_MIN_OVERLAP_VEH:
                motivo_descarte = "fuera_mascara_vehiculo"
            elif ratio_cab < config.M4_MIN_OVERLAP_CABINA:
                motivo_descarte = "fuera_zona_cabina"
            elif py2 >= (vy2 - 0.12 * vh) and (py2 - py1) >= (0.55 * vh) and ratio_cab < 0.60:
                motivo_descarte = "peaton_nivel_suelo"

        if motivo_descarte is not None:
            peatones_descartados.append({
                "conf": round(float(p_conf), 4),
                "ratio_en_vehiculo": round(ratio_veh, 4),
                "ratio_en_cabina": round(ratio_cab, 4),
                "motivo": motivo_descarte,
            })
            continue

        mx_p = (px1 + px2) / 2.0
        my_p = (py1 + py2) / 2.0
        rel_x = (mx_p - cx1) / cw
        rel_y = (my_p - cy1) / ch

        ocupantes_raw.append({
            "bbox": pbox,
            "poly": p_poly,
            "conf": round(float(p_conf), 4),
            "ratio_en_vehiculo": round(ratio_veh, 4),
            "ratio_en_cabina": round(ratio_cab, 4),
            "rel_x_cabina": round(rel_x, 3),
            "rel_y_cabina": round(rel_y, 3),
        })

    # Diferenciación conductor vs pasajeros (criterio geométrico Bolivia LHD: volante a la izquierda del vehículo)
    # En toma frontal (placa visible en el frente o vehículo orientado hacia cámara), el conductor queda en la mitad derecha de la imagen (rel_x >= 0.48).
    vista_frontal = bool(placa_caja is not None) or (vw / vh <= 1.65)
    criterio_rol = "sin_ocupantes_detectados"
    conductor_idx: int | None = None

    if ocupantes_raw:
        if categoria == "moto":
            # En motocicleta el conductor es el ocupante más alto/adelantado
            conductor_idx = min(range(len(ocupantes_raw)), key=lambda i: (ocupantes_raw[i]["rel_y_cabina"], -ocupantes_raw[i]["conf"]))
            criterio_rol = "moto_jinete_principal"
        elif vista_frontal:
            candidatos_cond = [
                i for i, o in enumerate(ocupantes_raw)
                if o["rel_x_cabina"] >= 0.48 and o["rel_y_cabina"] <= 0.85
            ]
            if candidatos_cond:
                conductor_idx = min(candidatos_cond, key=lambda i: abs(ocupantes_raw[i]["rel_x_cabina"] - 0.65))
                criterio_rol = "frontal_bolivia_volante_izquierdo_imagen_derecha"
            else:
                criterio_rol = "frontal_sin_ocupante_en_asiento_conductor"
        else:
            if len(ocupantes_raw) == 1:
                conductor_idx = 0
                criterio_rol = "lateral_ocupante_unico_probable_conductor"
            else:
                criterio_rol = "lateral_multiple_rol_no_diferenciable"

    ocupantes_publicos: list[dict] = []
    pax_render: list[dict] = []
    for i, occ in enumerate(ocupantes_raw):
        if conductor_idx is not None:
            rol = "conductor_probable" if i == conductor_idx else "pasajero"
        else:
            rol = "ocupante_sin_rol_confirmado"
        ocupantes_publicos.append({
            "indice": i + 1,
            "rol": rol,
            "conf": occ["conf"],
            "ratio_en_vehiculo": occ["ratio_en_vehiculo"],
            "ratio_en_cabina": occ["ratio_en_cabina"],
            "mascara_poligono": _simplificar_poligono(occ["poly"]),
        })
        pax_render.append({
            "bbox": occ["bbox"],
            "poly": occ["poly"],
            "rol": rol,
        })

    vis_ok, estado_vis, metricas_vis = _evaluar_visibilidad_cabina(bgr, cand["bbox"], veh_poly, categoria)

    n_ocupantes = len(ocupantes_publicos)
    if n_ocupantes > 0:
        pasajeros_final: int | None = n_ocupantes
        conductor_det: int | None = 1 if conductor_idx is not None else 0
        pasajeros_adic: int | None = n_ocupantes - (1 if conductor_idx is not None else 0)
        estado_conteo = "confiable"
    elif vis_ok:
        pasajeros_final = 0
        conductor_det = 0
        pasajeros_adic = 0
        estado_conteo = "confiable_cero_observados"
    else:
        pasajeros_final = None
        conductor_det = None
        pasajeros_adic = None
        estado_conteo = estado_vis

    return {
        "pasajeros": pasajeros_final,
        "conductor_detectado": conductor_det,
        "pasajeros_adicionales": pasajeros_adic,
        "m4_detalle": {
            "ocupantes_visibles": pasajeros_final,
            "conductor_detectado": conductor_det,
            "pasajeros_adicionales": pasajeros_adic,
            "estado_conteo": estado_conteo,
            "criterio_rol": criterio_rol,
            "visibilidad_cabina": metricas_vis,
            "peatones_descartados": len(peatones_descartados),
            "detalle_peatones_descartados": peatones_descartados,
            "ocupantes": ocupantes_publicos,
        },
        "_pax_render": pax_render,
    }


def _filtrar_keypoints_geometrico(
    kpts_visibles: list[tuple[int, float, float, float]],
    kpts_detalle: list[dict],
    bbox: list[int],
) -> list[tuple[int, float, float, float]]:
    """Filtra keypoints imposibles (fuera de la franja inferior de ruedas) y aplica NMS por distancia mínima."""
    if not kpts_visibles:
        return []
    bx1, by1, bx2, by2 = bbox
    box_w = max(1.0, float(bx2 - bx1))
    box_h = max(1.0, float(by2 - by1))

    y_min = by1 + box_h * config.KPT_MIN_Y_RATIO
    y_max = by2 + box_h * 0.08
    x_min = bx1 - box_w * 0.05
    x_max = bx2 + box_w * 0.05

    detalle_por_slot = {d["indice"]: d for d in kpts_detalle}

    # 1. Filtro de franja inferior (las ruedas siempre están en la mitad inferior del vehículo)
    en_franja: list[tuple[int, float, float, float]] = []
    for item in kpts_visibles:
        slot_i, gx, gy, kc = item
        if x_min <= gx <= x_max and y_min <= gy <= y_max:
            en_franja.append(item)
        else:
            if slot_i in detalle_por_slot:
                detalle_por_slot[slot_i]["visible"] = False
                detalle_por_slot[slot_i]["filtrado_por"] = "fuera_franja_ruedas"

    # 2. NMS espacial 2D: elimina keypoints duplicados sobre la misma rueda (conserva mayor confianza)
    min_dist = max(8.0, box_w * config.KPT_NMS_MIN_RATIO)
    min_dist_sq = min_dist * min_dist
    ordenados_conf = sorted(en_franja, key=lambda t: t[3], reverse=True)
    conservados: list[tuple[int, float, float, float]] = []
    for item in ordenados_conf:
        slot_i, gx, gy, kc = item
        duplicado = False
        for _s2, ox, oy, _c2 in conservados:
            dx = gx - ox
            dy = gy - oy
            if (dx * dx + dy * dy) < min_dist_sq:
                duplicado = True
                break
        if duplicado:
            if slot_i in detalle_por_slot:
                detalle_por_slot[slot_i]["visible"] = False
                detalle_por_slot[slot_i]["filtrado_por"] = "nms_duplicado"
        else:
            conservados.append(item)

    conservados.sort(key=lambda t: t[0])
    return conservados


def _parsear_detecciones_m3(
    pose_res,
    offset_x: int = 0,
    offset_y: int = 0,
) -> list[dict]:
    """Extrae cajas y keypoints individuales (con coordenadas y confianza) de la salida de M3."""
    if pose_res is None or pose_res.boxes is None or len(pose_res.boxes) == 0:
        return []
    salida: list[dict] = []
    has_kpts = pose_res.keypoints is not None and len(pose_res.keypoints) == len(pose_res.boxes)
    for idx in range(len(pose_res.boxes)):
        bx1, by1, bx2, by2 = map(int, pose_res.boxes.xyxy[idx].tolist())
        box_conf = round(float(pose_res.boxes.conf[idx]), 4)
        kpts_detalle: list[dict] = []
        kpts_visibles: list[tuple[int, float, float, float]] = []
        kpts_dudosos = 0

        if has_kpts:
            xy_pts = pose_res.keypoints.xy[idx].cpu().numpy()
            kconf = pose_res.keypoints.conf[idx].cpu().numpy() if pose_res.keypoints.conf is not None else None
            for slot_i, (px, py) in enumerate(xy_pts, start=1):
                kc = float(kconf[slot_i - 1]) if kconf is not None else (1.0 if (px > 0 or py > 0) else 0.0)
                gx = float(px) + offset_x
                gy = float(py) + offset_y
                visible = bool(kc >= config.CONF_KEYPOINT and (px > 0 or py > 0))
                if not visible and 0.30 <= kc < config.CONF_KEYPOINT and (px > 0 or py > 0):
                    kpts_dudosos += 1
                kpts_detalle.append({
                    "nombre": f"eje_{slot_i}",
                    "indice": slot_i,
                    "x": round(gx, 1) if (px > 0 or py > 0) else 0.0,
                    "y": round(gy, 1) if (px > 0 or py > 0) else 0.0,
                    "conf": round(kc, 4),
                    "visible": visible,
                })
                if visible:
                    kpts_visibles.append((slot_i, gx, gy, kc))

        bbox_global = [bx1 + offset_x, by1 + offset_y, bx2 + offset_x, by2 + offset_y]
        kpts_visibles = _filtrar_keypoints_geometrico(kpts_visibles, kpts_detalle, bbox_global)

        salida.append({
            "bbox": bbox_global,
            "conf_bbox": box_conf,
            "keypoints": kpts_detalle,
            "kpts_vis": kpts_visibles,
            "kpts_dudosos": kpts_dudosos,
        })
    return salida


def _asociar_m2_m3_uno_a_uno(
    vehiculos_m2: list[dict],
    detecciones_m3: list[dict],
) -> dict[int, tuple[dict, float, float]]:
    """Asocia detecciones de M2 con M3 de forma 1 a 1 mediante IoU y consistencia geométrica.

    Retorna {idx_m2: (det_m3, iou, ratio_kpts_dentro)}.
    """
    candidatos_pares: list[tuple[float, float, int, int]] = []
    for i, veh in enumerate(vehiculos_m2):
        vx1, vy1, vx2, vy2 = veh["bbox"]
        for j, det3 in enumerate(detecciones_m3):
            iou = calcular_iou(veh["bbox"], det3["bbox"])
            if iou < config.IOU_ASOCIACION:
                continue
            kpts_vis = det3["kpts_vis"]
            if kpts_vis:
                dentro = sum(
                    1
                    for _, kx, ky, _ in kpts_vis
                    if (vx1 - 15) <= kx <= (vx2 + 15) and (vy1 - 15) <= ky <= (vy2 + 15)
                )
                ratio_dentro = dentro / len(kpts_vis)
            else:
                ratio_dentro = 0.0
            if kpts_vis and ratio_dentro < 0.5:
                continue
            score = iou * 0.75 + ratio_dentro * 0.25
            candidatos_pares.append((score, iou, ratio_dentro, i, j))

    # Emparejamiento 1 a 1 codicioso por mayor score combinado (garantiza unicidad)
    candidatos_pares.sort(key=lambda t: (t[0], t[1]), reverse=True)
    m2_usados: set[int] = set()
    m3_usados: set[int] = set()
    emparejados: dict[int, tuple[dict, float, float]] = {}

    for _score, iou, ratio_dentro, i, j in candidatos_pares:
        if i in m2_usados or j in m3_usados:
            continue
        m2_usados.add(i)
        m3_usados.add(j)
        emparejados[i] = (detecciones_m3[j], round(iou, 4), round(ratio_dentro, 4))

    return emparejados


def _deduplicar_llantas(llantas: list[dict]) -> list[dict]:
    """Elimina cajas duplicadas sobre la misma llanta por IoU o cercanía entre centros."""
    if not llantas:
        return []
    ordenadas = sorted(llantas, key=lambda d: d["conf_bbox"], reverse=True)
    conservadas: list[dict] = []
    for cand in ordenadas:
        cx, cy = cand["cx"], cand["cy"]
        cw = max(1.0, float(cand["bbox"][2] - cand["bbox"][0]))
        ch = max(1.0, float(cand["bbox"][3] - cand["bbox"][1]))
        duplicada = False
        for kept in conservadas:
            if calcular_iou(cand["bbox"], kept["bbox"]) >= 0.35:
                duplicada = True
                break
            kw = max(1.0, float(kept["bbox"][2] - kept["bbox"][0]))
            kh = max(1.0, float(kept["bbox"][3] - kept["bbox"][1]))
            radio = 0.45 * min(max(cw, ch), max(kw, kh))
            dx = cx - kept["cx"]
            dy = cy - kept["cy"]
            if (dx * dx + dy * dy) < (radio * radio):
                duplicada = True
                break
        if not duplicada:
            conservadas.append(cand)
    return conservadas


def _parsear_llantas_m3(
    pose_res,
    offset_x: int = 0,
    offset_y: int = 0,
) -> list[dict]:
    """Extrae llantas individuales con su centro (keypoint 0) y 4 puntos de borde (keypoints 1..4)."""
    if pose_res is None or pose_res.boxes is None or len(pose_res.boxes) == 0:
        return []
    salida: list[dict] = []
    has_kpts = pose_res.keypoints is not None and len(pose_res.keypoints) == len(pose_res.boxes)
    for idx in range(len(pose_res.boxes)):
        bx1, by1, bx2, by2 = map(int, pose_res.boxes.xyxy[idx].tolist())
        box_conf = round(float(pose_res.boxes.conf[idx]), 4)
        gx1, gy1, gx2, gy2 = bx1 + offset_x, by1 + offset_y, bx2 + offset_x, by2 + offset_y
        cx = (gx1 + gx2) / 2.0
        cy = (gy1 + gy2) / 2.0
        conf_centro = box_conf
        rim_kpts: list[tuple[float, float, float]] = []

        if has_kpts:
            xy_pts = pose_res.keypoints.xy[idx].cpu().numpy()
            kconf = pose_res.keypoints.conf[idx].cpu().numpy() if pose_res.keypoints.conf is not None else None
            if len(xy_pts) > 0:
                px0, py0 = float(xy_pts[0][0]), float(xy_pts[0][1])
                kc0 = float(kconf[0]) if kconf is not None else (1.0 if (px0 > 0 or py0 > 0) else 0.0)
                if kc0 >= 0.30 and (px0 > 0 or py0 > 0):
                    cx = px0 + offset_x
                    cy = py0 + offset_y
                    conf_centro = round(kc0, 4)
            for ki in range(1, len(xy_pts)):
                px, py = float(xy_pts[ki][0]), float(xy_pts[ki][1])
                kc = float(kconf[ki]) if kconf is not None else (1.0 if (px > 0 or py > 0) else 0.0)
                if px > 0 or py > 0:
                    rim_kpts.append((px + offset_x, py + offset_y, round(kc, 4)))

        salida.append({
            "bbox": [gx1, gy1, gx2, gy2],
            "conf_bbox": box_conf,
            "cx": cx,
            "cy": cy,
            "conf_centro": conf_centro,
            "rim_kpts": rim_kpts,
        })
    return _deduplicar_llantas(salida)


def _asociar_llantas_a_vehiculos(
    vehiculos_m2: list[dict],
    llantas: list[dict],
) -> dict[int, tuple[dict, float, float]]:
    """Asocia cada llanta detectada (1 a 1) a su vehículo M2 correspondiente y construye det_m3."""
    if not vehiculos_m2 or not llantas:
        return {}

    asignadas: dict[int, list[dict]] = {i: [] for i in range(len(vehiculos_m2))}
    for ll in llantas:
        cx, cy = ll["cx"], ll["cy"]
        lw = max(1.0, float(ll["bbox"][2] - ll["bbox"][0]))
        lh = max(1.0, float(ll["bbox"][3] - ll["bbox"][1]))
        mejor_veh: int | None = None
        mejor_score = -1.0

        for i, veh in enumerate(vehiculos_m2):
            vx1, vy1, vx2, vy2 = veh["bbox"]
            vw = max(1.0, float(vx2 - vx1))
            vh = max(1.0, float(vy2 - vy1))
            if lw > 0.65 * vw or lh > 0.85 * vh:
                continue
            if not ((vx1 - 0.06 * vw) <= cx <= (vx2 + 0.06 * vw)):
                continue
            if not ((vy1 + 0.35 * vh) <= cy <= (vy2 + 0.10 * vh)):
                continue

            # Puntaje por contención de caja de llanta dentro del vehículo + cercanía a la base
            ix1, iy1 = max(vx1, ll["bbox"][0]), max(vy1, ll["bbox"][1])
            ix2, iy2 = min(vx2, ll["bbox"][2]), min(vy2, ll["bbox"][3])
            inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            ratio_cont = inter / max(1.0, lw * lh)
            rel_y = min(1.0, max(0.0, (cy - vy1) / vh))
            score = ratio_cont * 0.75 + rel_y * 0.25
            if score > mejor_score:
                mejor_score = score
                mejor_veh = i

        if mejor_veh is not None:
            asignadas[mejor_veh].append(ll)

    emparejados: dict[int, tuple[dict, float, float]] = {}
    for i, veh in enumerate(vehiculos_m2):
        lista = asignadas[i]
        if not lista:
            continue
        vx1, vy1, vx2, vy2 = veh["bbox"]
        vw = max(1.0, float(vx2 - vx1))
        min_dist = max(8.0, vw * config.KPT_NMS_MIN_RATIO)
        min_dist_sq = min_dist * min_dist

        # Deduplicación final intra-vehículo por distancia mínima entre centros
        lista_conf = sorted(lista, key=lambda d: (d["conf_bbox"], d["conf_centro"]), reverse=True)
        limpias: list[dict] = []
        for ll in lista_conf:
            if any(((ll["cx"] - k["cx"]) ** 2 + (ll["cy"] - k["cy"]) ** 2) < min_dist_sq for k in limpias):
                continue
            limpias.append(ll)

        # Ordenar ejes por coordenada X (de izquierda a derecha) y limitar a MAX_EJES
        limpias.sort(key=lambda d: d["cx"])
        limpias = limpias[: config.MAX_EJES]

        kpts_detalle: list[dict] = []
        kpts_visibles: list[tuple[int, float, float, float]] = []
        for slot_i, ll in enumerate(limpias, start=1):
            kpts_detalle.append({
                "nombre": f"eje_{slot_i}",
                "indice": slot_i,
                "x": round(float(ll["cx"]), 1),
                "y": round(float(ll["cy"]), 1),
                "conf": round(float(ll["conf_centro"]), 4),
                "conf_llanta": round(float(ll["conf_bbox"]), 4),
                "visible": True,
            })
            kpts_visibles.append((slot_i, float(ll["cx"]), float(ll["cy"]), float(ll["conf_centro"])))

        conf_media = round(sum(ll["conf_bbox"] for ll in limpias) / len(limpias), 4)
        ux1 = min(ll["bbox"][0] for ll in limpias)
        uy1 = min(ll["bbox"][1] for ll in limpias)
        ux2 = max(ll["bbox"][2] for ll in limpias)
        uy2 = max(ll["bbox"][3] for ll in limpias)

        det_m3 = {
            "bbox": [ux1, uy1, ux2, uy2],
            "conf_bbox": conf_media,
            "keypoints": kpts_detalle,
            "kpts_vis": kpts_visibles,
            "kpts_dudosos": 0,
            "llantas_vis": limpias,
        }
        emparejados[i] = (det_m3, 1.0, 1.0)

    return emparejados


def _evaluar_estado_ejes(
    categoria: str,
    det_m3: dict | None,
    iou_match: float | None,
) -> dict:
    """Evalúa ejes_observados, ejes_estimados y estado de confirmación sin inventar ejes ocultos."""
    if det_m3 is None:
        return {
            "ejes": None,
            "ejes_observados": 0,
            "ejes_estimados": None,
            "ejes_visibles": 0,
            "ejes_estado": "sin_asociacion_m3",
            "requiere_revision_ejes": True,
            "motivos_revision_ejes": ["sin_deteccion_m3_asociada"],
            "limite_esquema_7_alcanzado": False,
            "iou_m2_m3": None,
            "conf_bbox_m3": None,
            "keypoints_ejes": [],
            "_kpts_vis": [],
            "_llantas_vis": [],
        }

    kpts_vis = det_m3["kpts_vis"]
    n_obs = len(kpts_vis)
    motivos: list[str] = []

    if n_obs < 2:
        motivos.append("menos_de_2_ejes_visibles_oclusion_o_parcial")
    if n_obs == 4:
        motivos.append("conteo_4_ejes_requiere_confirmacion")
    if n_obs == config.MAX_EJES:
        motivos.append("limite_esquema_7_ejes_puede_superar_7")
    if det_m3["kpts_dudosos"] > 0:
        motivos.append(f"keypoints_confianza_intermedia:{det_m3['kpts_dudosos']}")
    if categoria in CATEGORIAS_DOS_EJES and n_obs >= 3:
        motivos.append(f"inconsistencia_categoria_{categoria}_con_{n_obs}_ejes")

    ejes_estimados = n_obs if 2 <= n_obs <= config.MAX_EJES else None
    if ejes_estimados is None:
        ejes_estado = "incierto"
        requiere_rev = True
    elif motivos:
        ejes_estado = "pendiente_confirmacion"
        requiere_rev = True
    else:
        ejes_estado = "confirmado"
        requiere_rev = False

    return {
        "ejes": ejes_estimados,
        "ejes_observados": n_obs,
        "ejes_estimados": ejes_estimados,
        "ejes_visibles": n_obs,
        "ejes_estado": ejes_estado,
        "requiere_revision_ejes": requiere_rev,
        "motivos_revision_ejes": motivos,
        "limite_esquema_7_alcanzado": n_obs >= config.MAX_EJES,
        "iou_m2_m3": iou_match,
        "conf_bbox_m3": det_m3["conf_bbox"],
        "keypoints_ejes": det_m3["keypoints"],
        "_kpts_vis": kpts_vis,
        "_llantas_vis": det_m3.get("llantas_vis", []),
    }


def inferir(bgr: np.ndarray) -> dict:
    """Pipeline unificado: M2 (multi-vehículo) + M3 (pose escena completa + IoU 1 a 1) + M1 (placa/OCR) + pasajeros."""
    cargar_modelos()
    h_img, w_img = bgr.shape[:2]
    seg_model = _MODELS["seg"]
    pose_model = _MODELS["pose"]
    pax_model = _MODELS["pasajeros"]
    device = resolver_dispositivo()
    modo_mock = False

    with _PREDICT_LOCK:
        # 1. Detección y segmentación de vehículos (M2)
        candidatos_veh: list[dict] = []
        if seg_model is None:
            if config.INFERENCE_MODE != "mock":
                raise ModeloNoDisponible(
                    _LOAD_ERRORS.get("m2") or f"Modelo M2 no disponible en {config.M2_MODEL_PATH}"
                )
            modo_mock = True
            candidatos_veh.append({
                "clase_id": None,
                "clase_modelo": "auto",
                "bbox": [0, 0, w_img, h_img],
                "crop_box": (0, 0, w_img, h_img),
                "area": w_img * h_img,
                "categoria": "auto",
                "confianza_categoria": None,
                "veh_poly": None,
            })
        else:
            conf_m2_efectivo = min(config.CONF_M2, config.CONF_M2_RESCATE)
            r = seg_model.predict(
                bgr,
                conf=conf_m2_efectivo,
                iou=config.IOU_M2,
                device=device,
                verbose=False,
            )[0]
            if r.boxes is None or len(r.boxes) == 0:
                raise ValueError("No se detectó ningún vehículo; capture otra toma")

            for idx_veh in range(len(r.boxes)):
                x1, y1, x2, y2 = map(int, r.boxes.xyxy[idx_veh].tolist())
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w_img, x2), min(h_img, y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                cls_id = int(r.boxes.cls[idx_veh])
                nombre_clase = str(r.names[cls_id])
                categoria = normalizar_categoria(nombre_clase)
                conf_cat = round(float(r.boxes.conf[idx_veh]), 4)

                bw, bh = max(1, x2 - x1), max(1, y2 - y1)
                mx, my = int(bw * 0.05), int(bh * 0.05)
                cx1, cy1 = max(0, x1 - mx), max(0, y1 - my)
                cx2, cy2 = min(w_img, x2 + mx), min(h_img, y2 + my)
                veh_poly = r.masks.xy[idx_veh] if (r.masks is not None and len(r.masks.xy) > idx_veh) else None

                candidatos_veh.append({
                    "clase_id": cls_id,
                    "clase_modelo": nombre_clase,
                    "bbox": [x1, y1, x2, y2],
                    "crop_box": (cx1, cy1, cx2, cy2),
                    "area": bw * bh,
                    "categoria": categoria,
                    "confianza_categoria": conf_cat,
                    "veh_poly": veh_poly,
                })

            if not candidatos_veh:
                raise ValueError("No se detectó ningún vehículo válido; capture otra toma")

        # 2. Detección de keypoints de ejes / llantas (M3) sobre escena completa + consenso multi-vehículo + asociación 1 a 1
        modo_llantas = _es_modelo_llantas(pose_model)
        detecciones_m3_escena: list[dict] = []
        emparejados_m3: dict[int, tuple[dict, float, float]] = {}
        if pose_model is not None:
            pose_res_full = pose_model.predict(
                bgr,
                conf=config.CONF_M3,
                iou=0.45,
                device=device,
                verbose=False,
            )[0]
            if modo_llantas:
                detecciones_m3_escena = _parsear_llantas_m3(pose_res_full, offset_x=0, offset_y=0)
            else:
                detecciones_m3_escena = _parsear_detecciones_m3(pose_res_full, offset_x=0, offset_y=0)

        if seg_model is not None:
            filtrados: list[dict] = []
            for cand in candidatos_veh:
                conf_c = cand["confianza_categoria"]
                if conf_c is None or conf_c >= config.CONF_M2:
                    filtrados.append(cand)
                    continue
                # Rescate por consenso M2+M3 en escenas con varios vehículos encimados
                if modo_llantas:
                    vx1, vy1, vx2, vy2 = cand["bbox"]
                    vw, vh = max(1.0, vx2 - vx1), max(1.0, vy2 - vy1)
                    llantas_dentro = sum(
                        1
                        for ll in detecciones_m3_escena
                        if (vx1 - 0.06 * vw) <= ll["cx"] <= (vx2 + 0.06 * vw)
                        and (vy1 + 0.35 * vh) <= ll["cy"] <= (vy2 + 0.10 * vh)
                    )
                    corroborado_m3 = llantas_dentro >= 2
                else:
                    corroborado_m3 = any(
                        calcular_iou(cand["bbox"], d3["bbox"]) >= 0.45
                        for d3 in detecciones_m3_escena
                    )
                if corroborado_m3:
                    filtrados.append(cand)
            candidatos_veh = filtrados
            if not candidatos_veh:
                raise ValueError("No se detectó ningún vehículo válido; capture otra toma")
            candidatos_veh.sort(key=lambda item: item["area"], reverse=True)

        if pose_model is not None:
            if modo_llantas:
                emparejados_m3 = _asociar_llantas_a_vehiculos(candidatos_veh, detecciones_m3_escena)
            else:
                emparejados_m3 = _asociar_m2_m3_uno_a_uno(candidatos_veh, detecciones_m3_escena)

        # 3. Modelo M4 de pasajeros (YOLOv8n-seg COCO, exclusivamente clase person ID 0)
        pax_detecciones: list[tuple[tuple[int, int, int, int], np.ndarray | None, float]] = []
        if config.PASAJEROS and pax_model is not None:
            p_res = pax_model.predict(
                bgr,
                conf=config.CONF_M4,
                iou=config.IOU_M4,
                classes=_persona_class_ids(pax_model),
                device=device,
                verbose=False,
            )[0]
            if p_res.boxes is not None and len(p_res.boxes) > 0:
                for p_idx in range(len(p_res.boxes)):
                    px1, py1, px2, py2 = map(int, p_res.boxes.xyxy[p_idx].tolist())
                    p_conf = float(p_res.boxes.conf[p_idx])
                    poly = p_res.masks.xy[p_idx] if (p_res.masks is not None and len(p_res.masks.xy) > p_idx) else None
                    pax_detecciones.append(((px1, py1, px2, py2), poly, p_conf))

        # 4. Consolidar M2 + M1 + M3 + pasajeros para CADA vehículo detectado
        detalles_internos: list[dict] = []
        es_unico = len(candidatos_veh) == 1
        m1_disponible = estado_m1()

        for idx_c, cand in enumerate(candidatos_veh):
            det_num = idx_c + 1
            cx1, cy1, cx2, cy2 = cand["crop_box"]
            x1, y1, x2, y2 = cand["bbox"]
            veh_crop = bgr[cy1:cy2, cx1:cx2]

            # M1 sobre el recorte del vehículo (conserva M2+M3 si faltase M1)
            if m1_disponible["m1_detector"] and m1_disponible["m1_ocr"]:
                m1 = inferir_placa_en(veh_crop)
                if m1.get("caja"):
                    bx1, by1, bx2, by2 = m1["caja"]
                    m1["caja"] = [cx1 + bx1, cy1 + by1, cx1 + bx2, cy1 + by2]
                if es_unico and m1.get("placa") is None:
                    m1_full = inferir_placa_en(bgr)
                    if m1_full.get("placa") is not None or (
                        m1.get("placa_cruda") is None and m1_full.get("placa_cruda")
                    ):
                        m1 = m1_full
            else:
                m1 = {"placa": None, "placa_cruda": None, "confianza": None, "caja": None}

            # M3 asociado 1 a 1 (con respaldo opcional en recorte solo si es único vehículo y no hubo match)
            if pose_model is None:
                if modo_mock:
                    info_ejes = {
                        "ejes": 2,
                        "ejes_observados": 2,
                        "ejes_estimados": 2,
                        "ejes_visibles": 2,
                        "ejes_estado": "mock",
                        "requiere_revision_ejes": False,
                        "motivos_revision_ejes": [],
                        "limite_esquema_7_alcanzado": False,
                        "iou_m2_m3": None,
                        "conf_bbox_m3": None,
                        "keypoints_ejes": [],
                        "_kpts_vis": [],
                        "_llantas_vis": [],
                    }
                else:
                    info_ejes = {
                        "ejes": None,
                        "ejes_observados": 0,
                        "ejes_estimados": None,
                        "ejes_visibles": 0,
                        "ejes_estado": "pendiente_m3",
                        "requiere_revision_ejes": True,
                        "motivos_revision_ejes": ["modelo_m3_no_cargado"],
                        "limite_esquema_7_alcanzado": False,
                        "iou_m2_m3": None,
                        "conf_bbox_m3": None,
                        "keypoints_ejes": [],
                        "_kpts_vis": [],
                        "_llantas_vis": [],
                    }
            else:
                match = emparejados_m3.get(idx_c)
                if match is not None:
                    det_m3, iou_match, _ratio = match
                    info_ejes = _evaluar_estado_ejes(cand["categoria"], det_m3, iou_match)
                    info_ejes["asociacion_metodo"] = "llantas_por_vehiculo" if modo_llantas else "escena_iou_1a1"
                elif es_unico:
                    pose_crop = pose_model.predict(
                        veh_crop, conf=config.CONF_M3, iou=0.45, device=device, verbose=False
                    )[0]
                    if modo_llantas:
                        llantas_crop = _parsear_llantas_m3(pose_crop, offset_x=cx1, offset_y=cy1)
                        emp_crop = _asociar_llantas_a_vehiculos([cand], llantas_crop)
                        if 0 in emp_crop:
                            det_c, iou_c, _ = emp_crop[0]
                            info_ejes = _evaluar_estado_ejes(cand["categoria"], det_c, iou_c)
                            info_ejes["asociacion_metodo"] = "llantas_recorte_respaldo"
                        else:
                            info_ejes = _evaluar_estado_ejes(cand["categoria"], None, None)
                            info_ejes["asociacion_metodo"] = "sin_match"
                    else:
                        dets_crop = _parsear_detecciones_m3(pose_crop, offset_x=cx1, offset_y=cy1)
                        if dets_crop:
                            mejor_crop = max(dets_crop, key=lambda d: d["conf_bbox"])
                            iou_c = round(calcular_iou(cand["bbox"], mejor_crop["bbox"]), 4)
                            info_ejes = _evaluar_estado_ejes(cand["categoria"], mejor_crop, iou_c)
                            info_ejes["asociacion_metodo"] = "recorte_respaldo"
                        else:
                            info_ejes = _evaluar_estado_ejes(cand["categoria"], None, None)
                            info_ejes["asociacion_metodo"] = "sin_match"
                else:
                    info_ejes = _evaluar_estado_ejes(cand["categoria"], None, None)
                    info_ejes["asociacion_metodo"] = "sin_match"

            # M4: evaluación de ocupantes visibles dentro del vehículo (excluyendo peatones, sin rostros)
            if config.PASAJEROS and pax_model is not None:
                info_m4 = _evaluar_ocupantes_m4(bgr, cand, pax_detecciones, m1.get("caja"))
            else:
                info_m4 = {
                    "pasajeros": None,
                    "conductor_detectado": None,
                    "pasajeros_adicionales": None,
                    "m4_detalle": {
                        "ocupantes_visibles": None,
                        "conductor_detectado": None,
                        "pasajeros_adicionales": None,
                        "estado_conteo": "m4_no_disponible",
                        "criterio_rol": "m4_no_disponible",
                        "visibilidad_cabina": None,
                        "peatones_descartados": 0,
                        "detalle_peatones_descartados": [],
                        "ocupantes": [],
                    },
                    "_pax_render": [],
                }

            conf_cat = cand["confianza_categoria"]
            conf_incierta = bool(conf_cat is not None and conf_cat < config.CONF_M2_COBRO)

            detalles_internos.append({
                "id_deteccion": f"veh_{det_num}",
                "clase_id": cand["clase_id"],
                "clase_modelo": cand["clase_modelo"],
                "categoria": cand["categoria"],
                "confianza_categoria": conf_cat,
                "confianza_incierta": conf_incierta,
                "bbox": [x1, y1, x2, y2],
                "centroide": [round((x1 + x2) / 2.0, 1), round((y1 + y2) / 2.0, 1)],
                "area_px": int(cand["area"]),
                "mascara_disponible": cand["veh_poly"] is not None,
                "mascara_poligono": _simplificar_poligono(cand["veh_poly"]),
                "zona_asociacion": {
                    "crop_bbox": [cx1, cy1, cx2, cy2],
                    "placa_bbox": m1.get("caja"),
                    "iou_m2_m3": info_ejes.get("iou_m2_m3"),
                    "asociacion_metodo": info_ejes.get("asociacion_metodo"),
                },
                "placa": m1.get("placa"),
                "placa_cruda": m1.get("placa_cruda"),
                "confianza": m1.get("confianza"),
                "ejes": info_ejes["ejes"],
                "ejes_observados": info_ejes["ejes_observados"],
                "ejes_estimados": info_ejes["ejes_estimados"],
                "ejes_visibles": info_ejes["ejes_visibles"],
                "ejes_estado": info_ejes["ejes_estado"],
                "requiere_revision_ejes": info_ejes["requiere_revision_ejes"],
                "motivos_revision_ejes": info_ejes["motivos_revision_ejes"],
                "limite_esquema_7_alcanzado": info_ejes["limite_esquema_7_alcanzado"],
                "conf_bbox_m3": info_ejes["conf_bbox_m3"],
                "keypoints_ejes": info_ejes["keypoints_ejes"],
                "pasajeros": info_m4["pasajeros"],
                "conductor_detectado": info_m4["conductor_detectado"],
                "pasajeros_adicionales": info_m4["pasajeros_adicionales"],
                "m4_detalle": info_m4["m4_detalle"],
                "mock": modo_mock,
                "_veh_poly": cand["veh_poly"],
                "_placa_caja": m1.get("caja"),
                "_kpts_vis": info_ejes["_kpts_vis"],
                "_llantas_vis": info_ejes.get("_llantas_vis", []),
                "_pax_render": info_m4["_pax_render"],
            })

    # Vehículo principal (carril de peaje): mayor área con placa y ejes; luego placa; luego ejes; si no, mayor área
    con_placa_y_ejes = [d for d in detalles_internos if d.get("placa") and d.get("ejes") is not None]
    if con_placa_y_ejes:
        principal = con_placa_y_ejes[0]
    else:
        con_placa = [d for d in detalles_internos if d.get("placa")]
        if con_placa:
            principal = con_placa[0]
        else:
            con_ejes = [d for d in detalles_internos if d.get("ejes") is not None]
            principal = con_ejes[0] if con_ejes else detalles_internos[0]

    evidencia = _dibujar_evidencia_multi(
        bgr=bgr,
        detalles_vehiculos=detalles_internos,
        principal=principal,
        modo_mock=modo_mock,
    )

    vehiculos_publicos = [
        {k: v for k, v in d.items() if not k.startswith("_")}
        for d in detalles_internos
    ]

    return {
        "placa": principal["placa"],
        "placa_cruda": principal["placa_cruda"],
        "confianza": principal["confianza"],
        "categoria": principal["categoria"],
        "clase_id": principal["clase_id"],
        "confianza_categoria": principal["confianza_categoria"],
        "confianza_incierta": principal["confianza_incierta"],
        "ejes": principal["ejes"],
        "ejes_observados": principal["ejes_observados"],
        "ejes_estimados": principal["ejes_estimados"],
        "ejes_visibles": principal["ejes_visibles"],
        "ejes_estado": principal["ejes_estado"],
        "requiere_revision_ejes": principal["requiere_revision_ejes"],
        "motivos_revision_ejes": principal["motivos_revision_ejes"],
        "limite_esquema_7_alcanzado": principal["limite_esquema_7_alcanzado"],
        "m3_disponible": pose_model is not None,
        "m4_disponible": pax_model is not None,
        "pasajeros": principal["pasajeros"],
        "conductor_detectado": principal["conductor_detectado"],
        "pasajeros_adicionales": principal["pasajeros_adicionales"],
        "m4_detalle": principal["m4_detalle"],
        "total_vehiculos": len(vehiculos_publicos),
        "total_detecciones_m3_escena": len(detecciones_m3_escena),
        "asociaciones_m2_m3": len(emparejados_m3),
        "vehiculos": vehiculos_publicos,
        "resumen_umbrales": {
            "conf_m2": config.CONF_M2,
            "iou_m2": config.IOU_M2,
            "conf_m2_cobro": config.CONF_M2_COBRO,
            "conf_m3": config.CONF_M3,
            "conf_keypoint": config.CONF_KEYPOINT,
            "iou_asociacion": config.IOU_ASOCIACION,
            "conf_m4": config.CONF_M4,
            "iou_m4": config.IOU_M4,
            "m4_min_overlap_veh": config.M4_MIN_OVERLAP_VEH,
            "m4_min_overlap_cabina": config.M4_MIN_OVERLAP_CABINA,
        },
        "evidencia": evidencia,
        "modo_ejecucion": "mock" if modo_mock else "real",
        "demo": modo_mock,
    }


def inferir_placa(bgr: np.ndarray) -> dict:
    """Ejecuta únicamente M1 (localización de placa + OCR) para modo consulta."""
    cargar_modelos()
    with _PREDICT_LOCK:
        m1 = inferir_placa_en(bgr)

    canvas = bgr.copy()
    h, w = canvas.shape[:2]
    caja = m1.get("caja")
    if caja:
        px1, py1, px2, py2 = [int(v) for v in caja]
        cv2.rectangle(canvas, (px1, py1), (px2, py2), (255, 180, 0), 3)
    banner_h = max(36, int(h * 0.06))
    cv2.rectangle(canvas, (0, 0), (w, banner_h), (15, 23, 42), -1)
    texto = m1.get("placa") or m1.get("placa_cruda") or "SIN LECTURA"
    cv2.putText(
        canvas,
        f"CONSULTA M1: {texto}",
        (12, int(banner_h * 0.68)),
        cv2.FONT_HERSHEY_DUPLEX,
        max(0.45, min(0.8, w / 900.0)),
        (248, 250, 252),
        2,
        cv2.LINE_AA,
    )
    evidencia = _codificar_evidencia(canvas)
    return {
        "modo": "m1",
        "placa": m1.get("placa"),
        "placa_cruda": m1.get("placa_cruda"),
        "confianza": m1.get("confianza"),
        "confianza_deteccion": m1.get("confianza_deteccion"),
        "caja": m1.get("caja"),
        "evidencia": evidencia,
    }


def inferir_m2_solo(bgr: np.ndarray) -> dict:
    """Ejecuta únicamente M2 (segmentación y clasificación vehicular) para pruebas individuales."""
    cargar_modelos()
    seg_model = _MODELS["seg"]
    if seg_model is None:
        raise ModeloNoDisponible(_LOAD_ERRORS.get("m2") or "Modelo M2 no disponible")

    device = resolver_dispositivo()
    canvas = bgr.copy()
    h, w = canvas.shape[:2]
    banner_h = max(40, int(h * 0.06))
    vehiculos: list[dict] = []

    with _PREDICT_LOCK:
        r = seg_model.predict(
            bgr,
            conf=config.CONF_M2,
            iou=config.IOU_M2,
            device=device,
            verbose=False,
        )[0]

    if r.boxes is not None and len(r.boxes) > 0:
        for idx in range(len(r.boxes)):
            x1, y1, x2, y2 = map(int, r.boxes.xyxy[idx].tolist())
            cls_id = int(r.boxes.cls[idx])
            nombre = str(r.names[cls_id])
            cat = normalizar_categoria(nombre)
            conf = round(float(r.boxes.conf[idx]), 4)
            poly = r.masks.xy[idx] if (r.masks is not None and len(r.masks.xy) > idx) else None
            color = COLORES_CATEGORIA.get(cat, (34, 197, 94))

            if poly is not None and len(poly) >= 3:
                overlay = canvas.copy()
                pts = poly.astype(np.int32).reshape((-1, 1, 2))
                cv2.fillPoly(overlay, [pts], color)
                cv2.addWeighted(overlay, 0.30, canvas, 0.70, 0, canvas)
                cv2.polylines(canvas, [pts], True, color, 2, cv2.LINE_AA)

            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 3)
            label = f"veh_{idx + 1} {cat.upper()} {conf * 100:.0f}%"
            (tw_l, th_l), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.56, 2)
            ly = max(banner_h + th_l + 10, y1)
            cv2.rectangle(canvas, (x1, ly - th_l - 8), (x1 + tw_l + 10, ly), color, -1)
            cv2.putText(canvas, label, (x1 + 5, ly - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (15, 23, 42), 2, cv2.LINE_AA)

            vehiculos.append({
                "id_deteccion": f"veh_{idx + 1}",
                "clase_id": cls_id,
                "clase_modelo": nombre,
                "categoria": cat,
                "confianza": conf,
                "bbox": [x1, y1, x2, y2],
                "mascara_disponible": poly is not None,
            })

    cv2.rectangle(canvas, (0, 0), (w, banner_h), (15, 23, 42), -1)
    cv2.line(canvas, (0, banner_h), (w, banner_h), (34, 197, 94), 2)
    resumen_cat = ", ".join(f"{v['categoria'].upper()} ({v['confianza'] * 100:.0f}%)" for v in vehiculos[:3]) or "SIN DETECCIONES"
    cv2.putText(
        canvas,
        f"M2 SEGMENTACION | VEHICULOS: {len(vehiculos)} | {resumen_cat}",
        (12, int(banner_h * 0.68)),
        cv2.FONT_HERSHEY_DUPLEX,
        max(0.44, min(0.75, w / 1100.0)),
        (248, 250, 252),
        2,
        cv2.LINE_AA,
    )
    return {
        "modo": "m2",
        "total_vehiculos": len(vehiculos),
        "vehiculos": vehiculos,
        "evidencia": _codificar_evidencia(canvas),
    }


def inferir_m3_solo(bgr: np.ndarray) -> dict:
    """Ejecuta únicamente M3 (detección de llantas / keypoints de ejes) para pruebas individuales."""
    cargar_modelos()
    pose_model = _MODELS["pose"]
    if pose_model is None:
        raise ModeloNoDisponible(_LOAD_ERRORS.get("m3") or "Modelo M3 no disponible")

    device = resolver_dispositivo()
    modo_llantas = _es_modelo_llantas(pose_model)
    canvas = bgr.copy()
    h, w = canvas.shape[:2]
    banner_h = max(40, int(h * 0.06))

    with _PREDICT_LOCK:
        pose_res = pose_model.predict(
            bgr,
            conf=config.CONF_M3,
            iou=0.45,
            device=device,
            verbose=False,
        )[0]

    detecciones: list[dict] = []
    if modo_llantas:
        llantas = _parsear_llantas_m3(pose_res)
        llantas.sort(key=lambda d: d["cx"])
        if len(llantas) >= 2:
            for a, b in zip(llantas, llantas[1:]):
                cv2.line(
                    canvas,
                    (int(round(a["cx"])), int(round(a["cy"]))),
                    (int(round(b["cx"])), int(round(b["cy"]))),
                    (0, 215, 255),
                    2,
                    cv2.LINE_AA,
                )
        for idx, ll in enumerate(llantas, start=1):
            lx1, ly1, lx2, ly2 = [int(v) for v in ll["bbox"]]
            cv2.rectangle(canvas, (lx1, ly1), (lx2, ly2), (0, 215, 255), 2, cv2.LINE_AA)
            for rx, ry, rc in ll.get("rim_kpts", []):
                if rc >= 0.35 and (rx > 0 or ry > 0):
                    cv2.circle(canvas, (int(round(rx)), int(round(ry))), 3, (255, 255, 255), -1, cv2.LINE_AA)
            cx, cy = int(round(ll["cx"])), int(round(ll["cy"]))
            cv2.circle(canvas, (cx, cy), 8, (0, 215, 255), -1, cv2.LINE_AA)
            cv2.circle(canvas, (cx, cy), 10, (15, 23, 42), 2, cv2.LINE_AA)
            cv2.putText(canvas, f"e{idx}", (cx + 10, cy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (0, 215, 255), 2, cv2.LINE_AA)
            detecciones.append({
                "indice": idx,
                "bbox": ll["bbox"],
                "conf_llanta": ll["conf_bbox"],
                "centro": [round(float(ll["cx"]), 1), round(float(ll["cy"]), 1)],
                "conf_centro": ll["conf_centro"],
            })
        total_ejes = len(llantas)
    else:
        dets = _parsear_detecciones_m3(pose_res)
        total_ejes = 0
        for idx, det in enumerate(dets, start=1):
            bx1, by1, bx2, by2 = det["bbox"]
            cv2.rectangle(canvas, (bx1, by1), (bx2, by2), (0, 215, 255), 2)
            kpts_vis = det["kpts_vis"]
            total_ejes += len(kpts_vis)
            if len(kpts_vis) >= 2:
                for a, b in zip(kpts_vis, kpts_vis[1:]):
                    cv2.line(canvas, (int(round(a[1])), int(round(a[2]))), (int(round(b[1])), int(round(b[2]))), (0, 215, 255), 2, cv2.LINE_AA)
            for slot_i, kx, ky, _kc in kpts_vis:
                cx, cy = int(round(kx)), int(round(ky))
                cv2.circle(canvas, (cx, cy), 8, (0, 215, 255), -1, cv2.LINE_AA)
                cv2.putText(canvas, f"e{slot_i}", (cx + 10, cy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 215, 255), 2, cv2.LINE_AA)
            detecciones.append({
                "indice": idx,
                "bbox": det["bbox"],
                "conf_bbox": det["conf_bbox"],
                "ejes_visibles": len(kpts_vis),
                "keypoints": det["keypoints"],
            })

    cv2.rectangle(canvas, (0, 0), (w, banner_h), (15, 23, 42), -1)
    cv2.line(canvas, (0, banner_h), (w, banner_h), (0, 215, 255), 2)
    cv2.putText(
        canvas,
        f"M3 EJES / LLANTAS ({'LLANTAS' if modo_llantas else 'VEHICULO'}) | DETECTADOS: {total_ejes}",
        (12, int(banner_h * 0.68)),
        cv2.FONT_HERSHEY_DUPLEX,
        max(0.44, min(0.75, w / 1100.0)),
        (248, 250, 252),
        2,
        cv2.LINE_AA,
    )
    return {
        "modo": "m3",
        "modo_m3": "llantas" if modo_llantas else "vehiculo_ejes",
        "ejes_detectados": total_ejes,
        "total_detecciones": len(detecciones),
        "detecciones": detecciones,
        "evidencia": _codificar_evidencia(canvas),
    }


def inferir_m4_solo(bgr: np.ndarray) -> dict:
    """Ejecuta únicamente M4 (YOLOv8n-seg COCO person=0) con máscaras opacas sin rostros."""
    cargar_modelos()
    pax_model = _MODELS["pasajeros"]
    if pax_model is None:
        raise ModeloNoDisponible(_LOAD_ERRORS.get("m4") or "Modelo M4 (pasajeros) no disponible")

    device = resolver_dispositivo()
    canvas = bgr.copy()
    h, w = canvas.shape[:2]
    banner_h = max(40, int(h * 0.06))
    personas: list[dict] = []

    with _PREDICT_LOCK:
        p_res = pax_model.predict(
            bgr,
            conf=config.CONF_M4,
            iou=config.IOU_M4,
            classes=_persona_class_ids(pax_model),
            device=device,
            verbose=False,
        )[0]

    if p_res.boxes is not None and len(p_res.boxes) > 0:
        for idx in range(len(p_res.boxes)):
            px1, py1, px2, py2 = map(int, p_res.boxes.xyxy[idx].tolist())
            conf = round(float(p_res.boxes.conf[idx]), 4)
            poly = p_res.masks.xy[idx] if (p_res.masks is not None and len(p_res.masks.xy) > idx) else None
            if poly is not None and len(poly) >= 3:
                pts = poly.astype(np.int32).reshape((-1, 1, 2))
                cv2.fillPoly(canvas, [pts], (11, 158, 245))
                cv2.polylines(canvas, [pts], True, (0, 100, 180), 2, cv2.LINE_AA)
            else:
                cv2.rectangle(canvas, (px1, py1), (px2, py2), (11, 158, 245), -1)
            cy_t = max(banner_h + 18, py1 - 6)
            cv2.putText(
                canvas,
                f"PAX {idx + 1} ({conf * 100:.0f}%)",
                (max(4, px1), cy_t),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (11, 158, 245),
                2,
                cv2.LINE_AA,
            )
            personas.append({
                "indice": idx + 1,
                "clase": "person",
                "confianza": conf,
                "bbox": [px1, py1, px2, py2],
                "mascara_disponible": poly is not None,
            })

    cv2.rectangle(canvas, (0, 0), (w, banner_h), (15, 23, 42), -1)
    cv2.line(canvas, (0, banner_h), (w, banner_h), (11, 158, 245), 2)
    cv2.putText(
        canvas,
        f"M4 PASAJEROS / PERSONAS (COCO ID 0) | DETECTADAS: {len(personas)} (MASCARA OPACA)",
        (12, int(banner_h * 0.68)),
        cv2.FONT_HERSHEY_DUPLEX,
        max(0.42, min(0.72, w / 1150.0)),
        (248, 250, 252),
        2,
        cv2.LINE_AA,
    )
    return {
        "modo": "m4",
        "total_personas": len(personas),
        "personas": personas,
        "privacidad": "mascaras_opacas_sin_rostros",
        "evidencia": _codificar_evidencia(canvas),
    }
