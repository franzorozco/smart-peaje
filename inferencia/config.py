"""Configuración del servicio de inferencia leída desde variables de entorno."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent


def _cargar_env_local() -> None:
    """Carga variables desde inferencia/.env si existe, sin sobreescribir el entorno."""
    env_path = BASE_DIR / ".env"
    if not env_path.is_file():
        return
    for linea in env_path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")
        if clave and clave not in os.environ:
            os.environ[clave] = valor


_cargar_env_local()


def _env_float(nombre: str, defecto: float) -> float:
    raw = os.environ.get(nombre)
    if raw is None or raw.strip() == "":
        return defecto
    return float(raw)


def _env_bool(nombre: str, defecto: bool) -> bool:
    raw = os.environ.get(nombre)
    if raw is None or raw.strip() == "":
        return defecto
    return raw.strip().lower() in ("1", "true", "yes", "si", "on")


def _resolver_ruta(valor: str, defecto: Path) -> Path:
    limpio = (valor or "").strip()
    if not limpio:
        return defecto
    p = Path(limpio)
    if not p.is_absolute():
        p = (ROOT_DIR / p).resolve()
    return p


def get_inference_token() -> str:
    """Obtiene el token interno obligatorio para autenticar peticiones al servicio."""
    _cargar_env_local()
    return os.environ.get("INFERENCE_TOKEN", "").strip()


INFERENCE_TOKEN = get_inference_token()

MODELOS_DIR = _resolver_ruta(os.environ.get("MODELOS_DIR", ""), BASE_DIR / "modelos")
M2_MODEL_PATH = _resolver_ruta(os.environ.get("M2_MODEL_PATH", ""), MODELOS_DIR / "vehiculos.pt")
M2_MANIFEST_PATH = _resolver_ruta(os.environ.get("M2_MANIFEST_PATH", ""), MODELOS_DIR / "vehiculos.manifest.json")
M3_MODEL_PATH = _resolver_ruta(os.environ.get("M3_MODEL_PATH", ""), MODELOS_DIR / "ejes.pt")
M3_MANIFEST_PATH = _resolver_ruta(os.environ.get("M3_MANIFEST_PATH", ""), MODELOS_DIR / "ejes.manifest.json")
M4_MODEL_PATH = _resolver_ruta(os.environ.get("M4_MODEL_PATH", ""), MODELOS_DIR / "pasajeros.pt")
M4_MANIFEST_PATH = _resolver_ruta(os.environ.get("M4_MANIFEST_PATH", ""), MODELOS_DIR / "pasajeros.manifest.json")

# Modo de ejecución: 'real' (producción, exige pesos reales) o 'mock' (solo pruebas sin pesos).
_raw_mode = os.environ.get("INFERENCE_MODE", "").strip().lower()
if _raw_mode in ("real", "mock"):
    INFERENCE_MODE = _raw_mode
else:
    INFERENCE_MODE = "mock" if _env_bool("INFERENCE_DEMO", False) else "real"

INFERENCE_DEMO = INFERENCE_MODE == "mock"

# Dispositivo de ejecución: 'auto' usa GPU 0 si CUDA está disponible, si no 'cpu'.
INFERENCE_DEVICE = os.environ.get("INFERENCE_DEVICE", "auto").strip() or "auto"

# Umbrales iniciales sujetos a calibración (variables de entorno)
CONF_M2 = _env_float("CONF_M2", _env_float("SEG_CONF", 0.50))
CONF_M2_RESCATE = _env_float("CONF_M2_RESCATE", 0.25)
IOU_M2 = _env_float("IOU_M2", 0.45)
CONF_M2_COBRO = _env_float("CONF_M2_COBRO", 0.60)
SEG_CONF = CONF_M2

CONF_M3 = _env_float("CONF_M3", _env_float("POSE_CONF", 0.25))
CONF_KEYPOINT = _env_float("CONF_KEYPOINT", _env_float("KPT_CONF", 0.55))
KPT_NMS_MIN_RATIO = _env_float("KPT_NMS_MIN_RATIO", 0.055)
KPT_MIN_Y_RATIO = _env_float("KPT_MIN_Y_RATIO", 0.45)
IOU_ASOCIACION = _env_float("IOU_ASOCIACION", 0.50)
POSE_CONF = CONF_M3
KPT_CONF = CONF_KEYPOINT

PLACA_CONF = _env_float("PLACA_CONF", 0.25)

MAX_EJES = int(_env_float("MAX_EJES", 7))

# M4: Identificación y conteo de pasajeros visibles mediante segmentación (YOLOv8n-seg COCO person=0)
PASAJEROS = _env_bool("M4_HABILITADO", _env_bool("PASAJEROS", True))
PASAJEROS_MODELO = os.environ.get("PASAJEROS_MODELO", "pasajeros.pt").strip() or "pasajeros.pt"
CONF_M4 = _env_float("CONF_M4", 0.30)
IOU_M4 = _env_float("IOU_M4", 0.45)
M4_MIN_OVERLAP_VEH = _env_float("M4_MIN_OVERLAP_VEH", 0.35)
M4_MIN_OVERLAP_CABINA = _env_float("M4_MIN_OVERLAP_CABINA", 0.20)
M4_MIN_BRILLO_CABINA = _env_float("M4_MIN_BRILLO_CABINA", 55.0)
M4_MIN_CONTRASTE_CABINA = _env_float("M4_MIN_CONTRASTE_CABINA", 20.0)
M4_MAX_REFLEJO_RATIO = _env_float("M4_MAX_REFLEJO_RATIO", 0.35)
M4_MIN_CABIN_PX = int(_env_float("M4_MIN_CABIN_PX", 48))

MAX_IMAGEN_MB = int(_env_float("MAX_IMAGEN_MB", 8))
MAX_IMAGEN_BYTES = MAX_IMAGEN_MB * 1024 * 1024
