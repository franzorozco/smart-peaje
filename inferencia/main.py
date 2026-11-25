"""Servicio HTTP FastAPI unificado para inferencia de M1, M2, M3 y pasajeros."""
from contextlib import asynccontextmanager
import secrets
import time

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

import config
from vision import (
    ModeloNoDisponible,
    cargar_modelos,
    estado_modelos,
    inferir,
    inferir_m2_solo,
    inferir_m3_solo,
    inferir_m4_solo,
    inferir_placa,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not config.get_inference_token():
        raise RuntimeError("La variable de entorno INFERENCE_TOKEN es obligatoria.")
    cargar_modelos()
    yield


app = FastAPI(title="Smart Peaje · Servicio de Inferencia", version="1.0.0", lifespan=lifespan)


def autorizar(token: str) -> None:
    esperado = config.get_inference_token()
    if not esperado or not secrets.compare_digest(token or "", esperado):
        raise HTTPException(status_code=401, detail="No autorizado")


@app.get("/health")
def health():
    return {"status": "ok", **estado_modelos()}


@app.post("/predict")
def predict(
    file: UploadFile = File(...),
    modo: str = Form("caseta"),
    x_service_token: str = Header(default=""),
):
    autorizar(x_service_token)
    inicio = time.perf_counter()

    data = file.file.read(config.MAX_IMAGEN_BYTES + 1)
    if len(data) > config.MAX_IMAGEN_BYTES:
        raise HTTPException(status_code=413, detail="Imagen demasiado grande")

    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Imagen inválida")

    modos_validos = ("caseta", "consulta", "m1", "m2", "m3", "m4")
    if modo not in modos_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Modo inválido; usar uno de: {', '.join(modos_validos)}",
        )

    try:
        if modo == "caseta":
            resultado = inferir(img)
        elif modo in ("consulta", "m1"):
            resultado = inferir_placa(img)
        elif modo == "m2":
            resultado = inferir_m2_solo(img)
        elif modo == "m3":
            resultado = inferir_m3_solo(img)
        else:
            resultado = inferir_m4_solo(img)
    except ModeloNoDisponible as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {**resultado, "latencia_ms": round((time.perf_counter() - inicio) * 1000)}
