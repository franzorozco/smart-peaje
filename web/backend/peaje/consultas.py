"""Consultas de placas, estados y sugerencias por similitud OCR sin modificar saldos ni pasos."""
import itertools
import re

from django.utils import timezone

from .models import Paso, Vehiculo

PATRON_PLACA = re.compile(r"^\d{3,4}[A-Z]{3}$")

GRUPOS_OCR = {
    "O": ("O", "0"),
    "0": ("0", "O"),
    "I": ("I", "1"),
    "1": ("1", "I"),
    "B": ("B", "8"),
    "8": ("8", "B"),
    "S": ("S", "5"),
    "5": ("5", "S"),
}


def normalizar(placa: str) -> str:
    """Normaliza la placa a mayúsculas alfanuméricas sin espacios ni guiones."""
    return re.sub(r"[^A-Z0-9]", "", (placa or "").upper())


def formato_valido(placa: str) -> bool:
    """Verifica el patrón de placa de 3-4 dígitos seguidos de 3 letras."""
    return bool(PATRON_PLACA.fullmatch(placa or ""))


def sugerir(placa: str) -> list[str]:
    """Genera sugerencias para confusiones OCR (O<->0, I<->1, B<->8, S<->5) existentes en BD."""
    p = normalizar(placa)
    if not p or len(p) > 12:
        return []
    opciones = [GRUPOS_OCR.get(c, (c,)) for c in p]
    candidatos: list[str] = []
    for comb in itertools.islice(itertools.product(*opciones), 512):
        cand = "".join(comb)
        if cand != p and formato_valido(cand):
            candidatos.append(cand)
    if not candidatos:
        return []

    en_veh = set(Vehiculo.objects.filter(placa__in=candidatos).values_list("placa", flat=True))
    en_pasos = set(Paso.objects.filter(placa_normalizada__in=candidatos).values_list("placa_normalizada", flat=True))
    encontrados = en_veh | en_pasos
    if not encontrados:
        return []

    ordenados = sorted(
        encontrados,
        key=lambda c: (sum(a != b for a, b in zip(c, p)), c),
    )
    return ordenados[:5]


def consultar_placa(texto: str) -> dict:
    """Consulta una placa en PostgreSQL y clasifica exactamente uno de los cuatro estados."""
    p = normalizar(texto)
    if not formato_valido(p):
        sugs = sugerir(p)
        msg = f"Formato de placa no válido: '{p}'."
        if sugs:
            msg += f" ¿Quisiste decir {', '.join(sugs)}?"
        return {
            "placa": p,
            "formato_valido": False,
            "estado": None,
            "vehiculo": None,
            "ultimo_paso": None,
            "total_pasos": 0,
            "sugerencias": sugs,
            "mensaje": msg,
        }

    v = Vehiculo.objects.filter(placa=p).first()
    pasos_qs = Paso.objects.select_related("caseta").filter(placa_normalizada=p).order_by("-created_at")
    total_pasos = pasos_qs.count()
    ultimo = pasos_qs.first()

    if v and ultimo:
        estado = "Registrada y con paso"
    elif v:
        estado = "Registrada sin paso"
    elif ultimo:
        estado = "Identificada no registrada"
    else:
        estado = "No existe"

    vehiculo_data = (
        {
            "placa": v.placa,
            "categoria": v.categoria,
            "ejes": v.ejes,
            "activo": v.activo,
        }
        if v
        else None
    )

    detalle = None
    if ultimo:
        fecha_local = timezone.localtime(ultimo.created_at)
        detalle = {
            "fecha": fecha_local.isoformat(),
            "caseta": ultimo.caseta.nombre,
            "categoria": ultimo.categoria_detectada,
            "monto": str(ultimo.monto),
            "estado_pago": ultimo.estado,
        }

    sugs = sugerir(p) if estado == "No existe" else []

    if estado == "Registrada y con paso" and detalle:
        mensaje = (
            f"La placa {p} está registrada ({v.categoria}, {v.ejes} ejes) y tiene {total_pasos} paso(s). "
            f"Último paso: {detalle['fecha'][:19].replace('T', ' ')} en {detalle['caseta']}, "
            f"categoría {detalle['categoria']}, monto Bs {detalle['monto']} ({detalle['estado_pago']})."
        )
    elif estado == "Registrada sin paso":
        mensaje = (
            f"La placa {p} está registrada ({v.categoria}, {v.ejes} ejes), "
            "pero nunca ha registrado un paso por el peaje."
        )
    elif estado == "Identificada no registrada" and detalle:
        mensaje = (
            f"La placa {p} fue identificada por cámara pero NO está registrada en el sistema (posible evasión). "
            f"Último paso: {detalle['fecha'][:19].replace('T', ' ')} en {detalle['caseta']}, "
            f"categoría {detalle['categoria']}, monto Bs {detalle['monto']} ({detalle['estado_pago']})."
        )
    else:
        mensaje = f"No existe ningún registro ni paso para la placa {p}."
        if sugs:
            mensaje += f" ¿Quisiste decir {', '.join(sugs)}?"

    return {
        "placa": p,
        "formato_valido": True,
        "estado": estado,
        "vehiculo": vehiculo_data,
        "ultimo_paso": detalle,
        "total_pasos": total_pasos,
        "sugerencias": sugs,
        "mensaje": mensaje,
    }


def historial_placa(texto: str):
    """Obtiene hasta los 100 pasos más recientes de una placa normalizada."""
    p = normalizar(texto)
    qs = (
        Paso.objects.select_related("caseta", "usuario")
        .filter(placa_normalizada=p)
        .order_by("-created_at")[:100]
    )
    return p, qs
