"""Agente conversacional consultivo basado en herramientas deterministas (sin inventar datos)."""
import json
import logging
import re

from django.conf import settings
import requests

from .consultas import consultar_placa, historial_placa, normalizar
from .services import llamar_ia

logger = logging.getLogger("peaje.agente")

PATRON_CANDIDATO = re.compile(r"\b([0-9OISB]{3,4}[\s-]?[A-Z0-9]{3})\b", re.IGNORECASE)
PALABRAS_HISTORIAL = ("historial", "pasos", "registros", "recorrido", "movimientos")
MAX_IMAGEN_BYTES = 8 * 1024 * 1024


def _extraer_candidato_regex(mensaje: str) -> str | None:
    for match in PATRON_CANDIDATO.finditer(mensaje.upper()):
        cand = normalizar(match.group(1))
        # Evita falsos positivos con palabras comunes como SISTEMA o SOBRINO
        if any(ch.isdigit() for ch in cand):
            return cand
    return None


def _extraer_con_gemini(mensaje: str) -> tuple[str | None, str | None]:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        return None, None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Eres un clasificador de intenciones para un sistema de peaje. "
                            "Extrae únicamente la herramienta ('consultar_placa', 'historial' o 'aclaracion') "
                            "y la placa si el usuario menciona alguna (solo dígitos/letras). "
                            f"Mensaje del usuario: {mensaje}"
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "tool": {"type": "STRING", "enum": ["consultar_placa", "historial", "aclaracion"]},
                    "placa": {"type": "STRING", "nullable": True},
                },
                "required": ["tool"],
            },
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        texto = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(texto)
        tool = parsed.get("tool")
        placa = normalizar(parsed.get("placa") or "")
        return tool, (placa or None)
    except Exception as exc:
        logger.debug("Fallback Gemini omitido: %s", exc)
        return None, None


def _respuesta_historial(placa: str, pasos) -> str:
    total = len(pasos)
    if total == 0:
        return f"No existen pasos registrados para la placa {placa}."
    ultimo = pasos[0]
    return (
        f"Se encontraron {total} paso(s) para la placa {placa}. "
        f"El más reciente fue el {ultimo.created_at:%Y-%m-%d %H:%M} en {ultimo.caseta.nombre}, "
        f"categoría {ultimo.categoria_detectada}, monto Bs {ultimo.monto} (estado: {ultimo.estado})."
    )


def ejecutar_agente(mensaje: str = "", file_obj=None, serializer_context: dict | None = None) -> dict:
    """Ejecuta el agente usando herramientas reales de BD e IA sin inventar respuestas."""
    if file_obj is not None:
        data = file_obj.read(MAX_IMAGEN_BYTES + 1)
        if len(data) > MAX_IMAGEN_BYTES:
            raise ValueError("Imagen demasiado grande (máximo 8 MB).")
        res_ia = llamar_ia(data, modo="consulta")
        placa = normalizar(res_ia.get("placa") or "")
        placa_cruda = normalizar(res_ia.get("placa_cruda") or "")
        confianza = res_ia.get("confianza")

        if placa:
            info = consultar_placa(placa)
            conf_txt = f" (confianza OCR {round(confianza * 100, 1)}%)" if confianza is not None else ""
            return {
                "respuesta": f"Placa detectada: {placa}{conf_txt}. {info['mensaje']}",
                "tool": "consultar_imagen",
                "estado": info["estado"],
                "datos": {
                    "lectura": {"placa": placa, "placa_cruda": placa_cruda, "confianza": confianza},
                    **info,
                },
                "sugerencias": info["sugerencias"],
                "requiere": None,
            }

        if placa_cruda:
            info = consultar_placa(placa_cruda)
            sugs = info.get("sugerencias") or []
            if sugs:
                resp_txt = (
                    f"La lectura '{placa_cruda}' no es concluyente o tiene formato inválido. "
                    f"¿Quisiste decir {', '.join(sugs)}? Si no coincide, envíe otra imagen más nítida."
                )
            else:
                resp_txt = "No se detectó una placa legible en la imagen. Envíe otra fotografía más clara."
            return {
                "respuesta": resp_txt,
                "tool": "consultar_imagen",
                "estado": info.get("estado"),
                "datos": {
                    "lectura": {"placa": None, "placa_cruda": placa_cruda, "confianza": confianza},
                    **info,
                },
                "sugerencias": sugs,
                "requiere": "imagen",
            }

        return {
            "respuesta": "No se detectó una placa legible en la imagen. Por favor envíe otra imagen.",
            "tool": "consultar_imagen",
            "estado": None,
            "datos": None,
            "sugerencias": [],
            "requiere": "imagen",
        }

    texto = (mensaje or "").strip()
    if not texto:
        return {
            "respuesta": "Indíqueme la placa del vehículo (por ejemplo 9000LAB) o envíe una foto de la placa.",
            "tool": "aclaracion",
            "estado": None,
            "datos": None,
            "sugerencias": [],
            "requiere": "placa",
        }

    lower = texto.lower()
    es_historial = any(pal in lower for pal in PALABRAS_HISTORIAL)
    candidato = _extraer_candidato_regex(texto)

    if not candidato:
        tool_llm, placa_llm = _extraer_con_gemini(texto)
        if placa_llm:
            candidato = placa_llm
        if tool_llm == "historial":
            es_historial = True

    if not candidato:
        return {
            "respuesta": "Indíqueme la placa del vehículo (por ejemplo 9000LAB o 1234ABC) o envíe una foto.",
            "tool": "aclaracion",
            "estado": None,
            "datos": None,
            "sugerencias": [],
            "requiere": "placa",
        }

    if es_historial:
        from .serializers import PasoSerializer

        placa_norm, pasos_qs = historial_placa(candidato)
        pasos_list = list(pasos_qs)
        serializados = PasoSerializer(pasos_list, many=True, context=serializer_context or {}).data
        info = consultar_placa(placa_norm)
        return {
            "respuesta": _respuesta_historial(placa_norm, pasos_list),
            "tool": "historial",
            "estado": info["estado"],
            "datos": {
                "placa": placa_norm,
                "total": len(serializados),
                "pasos": serializados,
                "ultimo_paso": info["ultimo_paso"],
                "vehiculo": info["vehiculo"],
            },
            "sugerencias": info["sugerencias"],
            "requiere": None,
        }

    info = consultar_placa(candidato)
    return {
        "respuesta": info["mensaje"],
        "tool": "consultar_placa",
        "estado": info["estado"],
        "datos": info,
        "sugerencias": info["sugerencias"],
        "requiere": None,
    }
