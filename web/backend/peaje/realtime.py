"""Integración con Pusher Channels para eventos en tiempo real sobre canal privado."""
import logging

from django.conf import settings
import pusher

logger = logging.getLogger("peaje.realtime")

CANAL_PEAJE = "private-peaje"


def esta_configurado() -> bool:
    return all([
        settings.PUSHER_APP_ID,
        settings.PUSHER_KEY,
        settings.PUSHER_SECRET,
        settings.PUSHER_CLUSTER,
    ])


def cliente_pusher() -> pusher.Pusher | None:
    if not esta_configurado():
        return None
    return pusher.Pusher(
        app_id=settings.PUSHER_APP_ID,
        key=settings.PUSHER_KEY,
        secret=settings.PUSHER_SECRET,
        cluster=settings.PUSHER_CLUSTER,
        ssl=True,
    )


def emitir_evento(evento: str, data: dict) -> None:
    client = cliente_pusher()
    if client is None:
        logger.debug("Pusher no configurado; evento '%s' omitido (%s).", evento, data)
        return
    try:
        client.trigger(CANAL_PEAJE, evento, data)
    except Exception as exc:
        logger.warning("Error emitiendo evento Pusher '%s': %s", evento, exc)


def autenticar_canal(channel_name: str, socket_id: str) -> dict:
    if channel_name != CANAL_PEAJE:
        raise ValueError("Canal no permitido")
    client = cliente_pusher()
    if client is None:
        raise RuntimeError("Pusher no está configurado en el servidor")
    return client.authenticate(channel=channel_name, socket_id=socket_id)
