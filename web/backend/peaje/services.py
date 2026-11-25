"""Servicios de integración con IA y registro transaccional de pasos y alertas."""
from decimal import Decimal
import re
import time

from django.conf import settings
from django.db import transaction
import requests

from .consultas import formato_valido, normalizar
from .models import Alerta, Caseta, Evidencia, Paso, Tarifa, Usuario, Vehiculo
from .realtime import emitir_evento


class IANoDisponible(RuntimeError):
    """Error lanzado cuando el servicio de inferencia remoto no responde o no está listo."""


class CapturaAjenaError(ValueError):
    """Error lanzado cuando captura_id ya pertenece a otro usuario o caseta."""


def llamar_ia(imagen_bytes: bytes, modo: str = "caseta") -> dict:
    if not settings.INFERENCE_URL:
        raise IANoDisponible("INFERENCE_URL no está configurada.")
    try:
        resp = requests.post(
            settings.INFERENCE_URL,
            headers={"X-Service-Token": settings.INFERENCE_TOKEN},
            files={"file": ("frame.jpg", imagen_bytes, "image/jpeg")},
            data={"modo": modo},
            timeout=(5, 45),
        )
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise IANoDisponible("Servicio de inferencia no disponible.") from exc
    except requests.RequestException as exc:
        raise IANoDisponible("Error al comunicarse con el servicio de inferencia.") from exc

    if resp.status_code == 422:
        try:
            detalle = resp.json().get("detail") or resp.json().get("error") or "Lectura no concluyente."
        except Exception:
            detalle = "Lectura no concluyente."
        raise ValueError(detalle)

    if resp.status_code == 503:
        raise IANoDisponible("Modelos de inferencia no disponibles en el servidor de IA.")

    if resp.status_code == 400:
        try:
            detalle = resp.json().get("detail") or "Imagen o modo inválido."
        except Exception:
            detalle = "Imagen o modo inválido."
        raise ValueError(detalle)

    try:
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise IANoDisponible(f"Error del servicio de inferencia (HTTP {resp.status_code}).") from exc

    return resp.json()


def ia_health() -> dict:
    url = settings.INFERENCE_URL
    if not url:
        return {
            "url_configurada": False,
            "disponible": False,
            "latencia_ms": None,
            "detalle": None,
            "error": "INFERENCE_URL no configurada",
        }
    health_url = re.sub(r"/predict/?$", "/health", url)
    if health_url == url and not health_url.endswith("/health"):
        health_url = url.rstrip("/") + "/health"

    inicio = time.perf_counter()
    try:
        resp = requests.get(health_url, timeout=5)
        lat_ms = round((time.perf_counter() - inicio) * 1000)
        resp.raise_for_status()
        return {
            "url_configurada": True,
            "disponible": True,
            "latencia_ms": lat_ms,
            "detalle": resp.json(),
            "error": None,
        }
    except Exception as exc:
        lat_ms = round((time.perf_counter() - inicio) * 1000)
        return {
            "url_configurada": True,
            "disponible": False,
            "latencia_ms": lat_ms,
            "detalle": None,
            "error": str(exc),
        }


def resolver_tarifa(categoria: str, ejes: int) -> Tarifa:
    t = Tarifa.objects.filter(categoria=categoria, ejes=ejes).first()
    if t is not None:
        return t
    if categoria in ("moto", "auto", "minibus"):
        t = Tarifa.objects.filter(categoria=categoria).order_by("ejes").first()
        if t is not None:
            return t
    raise ValueError("Sin tarifa para categoría/ejes; requiere revisión")


@transaction.atomic
def registrar(
    pred: dict,
    captura_id,
    caseta: Caseta,
    usuario: Usuario,
    evidencia_bytes: bytes | None,
    latencia_ms: int | None = None,
) -> tuple[Paso, bool, Decimal | None]:
    """Consolida un paso idempotente por captura_id, actualiza saldo simulado y emite alertas."""
    caseta = Caseta.objects.select_for_update().get(pk=caseta.pk)
    anterior = Paso.objects.filter(captura_id=captura_id).first()
    if anterior:
        if anterior.usuario_id != usuario.pk or anterior.caseta_id != caseta.pk:
            raise CapturaAjenaError("Captura ajena")
        return anterior, False, None

    p = normalizar(pred.get("placa") or "")
    c = (pred.get("categoria") or "").strip().lower()
    e = pred.get("ejes")
    if not p or not formato_valido(p) or not c:
        raise ValueError("Solicitar otra captura")
    if e is None and pred.get("ejes_estado") == "pendiente_m3":
        raise ValueError("Solicitar otra captura")

    e_int = int(e) if e is not None else 0
    vehiculo = Vehiculo.objects.select_for_update().filter(placa=p).first()
    ejes_pendiente_confirmacion = (
        e is None
        or pred.get("ejes_estado") in ("pendiente_confirmacion", "sin_asociacion_m3", "incierto")
        or bool(pred.get("requiere_revision_ejes"))
        or bool(pred.get("limite_esquema_7_alcanzado"))
    )
    tarifa = None if ejes_pendiente_confirmacion else resolver_tarifa(c, e_int)

    saldo_restante: Decimal | None = None
    if ejes_pendiente_confirmacion:
        estado = "revision"
        monto = Decimal("0.00")
        saldo_restante = vehiculo.saldo if vehiculo else None
    elif not vehiculo:
        estado = "no_registrado"
        monto = tarifa.monto
    elif not vehiculo.activo:
        estado = "inactivo"
        monto = tarifa.monto
        saldo_restante = vehiculo.saldo
    elif vehiculo.categoria != c or vehiculo.ejes != e_int:
        estado = "revision"
        monto = Decimal("0.00")
        saldo_restante = vehiculo.saldo
    elif vehiculo.saldo < tarifa.monto:
        estado = "sin_saldo"
        monto = tarifa.monto
        saldo_restante = vehiculo.saldo
    else:
        estado = "pagado"
        monto = tarifa.monto
        vehiculo.saldo -= tarifa.monto
        vehiculo.save(update_fields=["saldo"])
        saldo_restante = vehiculo.saldo

    paso = Paso.objects.create(
        captura_id=captura_id,
        placa_leida=pred.get("placa_cruda") or p,
        placa_normalizada=p,
        confianza_ocr=pred.get("confianza"),
        categoria_detectada=c,
        ejes_detectados=e_int,
        pasajeros=pred.get("pasajeros"),
        monto=monto,
        caseta=caseta,
        usuario=usuario,
        imagen_url=f"evidencias/{captura_id}.jpg",
        estado=estado,
        latencia_ms=latencia_ms,
    )

    if evidencia_bytes:
        Evidencia.objects.create(
            paso=paso,
            contenido=evidencia_bytes,
            content_type="image/jpeg",
        )

    alerta = None
    if estado != "pagado":
        alerta = Alerta.objects.create(paso=paso, tipo=estado)

    def _notificar() -> None:
        emitir_evento("nuevo-paso", {"id": paso.pk, "estado": paso.estado})
        if alerta is not None:
            emitir_evento("nueva-alerta", {"id": alerta.pk, "tipo": alerta.tipo})

    transaction.on_commit(_notificar)
    return paso, True, saldo_restante
