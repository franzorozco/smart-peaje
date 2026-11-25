"""Manejador unificado de excepciones DRF para devolver siempre {"error": "..."}."""
from rest_framework.views import exception_handler

TRADUCCIONES = {
    "Authentication credentials were not provided.": "Autenticación requerida.",
    "Given token not valid for any token type": "Token inválido o expirado.",
    "Token is invalid or expired": "Token inválido o expirado.",
    "You do not have permission to perform this action.": "No tienes permisos para realizar esta acción.",
    "Not found.": "Recurso no encontrado.",
    "Request was throttled.": "Demasiadas peticiones. Intente nuevamente en un momento.",
}


def _traducir(texto: str) -> str:
    if texto in TRADUCCIONES:
        return TRADUCCIONES[texto]
    if texto.startswith("Request was throttled"):
        return "Demasiadas peticiones. Intente nuevamente en un momento."
    return texto


def _extraer_mensaje(data) -> str:
    if isinstance(data, dict):
        if "error" in data and isinstance(data["error"], str):
            return data["error"]
        if "detail" in data:
            return _traducir(str(data["detail"]))
        for campo, valor in data.items():
            if isinstance(valor, list) and valor:
                msg = _traducir(str(valor[0]))
                return msg if campo == "non_field_errors" else f"{campo}: {msg}"
            if isinstance(valor, str):
                return valor if campo == "non_field_errors" else f"{campo}: {valor}"
        return "Error en la solicitud."
    if isinstance(data, list) and data:
        return _traducir(str(data[0]))
    return str(data) if data else "Error en la solicitud."


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, dict) and "error" in data:
        return response

    mensaje = _extraer_mensaje(data)
    payload = {"error": mensaje}
    if isinstance(data, dict) and any(k not in ("detail", "code", "messages") for k in data):
        payload["detalles"] = data
    response.data = payload
    return response
