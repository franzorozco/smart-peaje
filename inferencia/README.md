# Servicio de Inferencia — Smart Peaje (M1 + M2 + M3 + Pasajeros)

Microservicio FastAPI que unifica los modelos de visión por computadora:
- **M1**: Detección de placa (`YOLOv9-t ONNX`) + OCR (`fast-plate-ocr`) reutilizando `/placas/` sin modificarlo.
- **M2**: Segmentación de instancias (`vehiculos.pt`) para clasificar `moto`, `auto`, `minibus`, `camion`, `bus`.
- **M3**: Detección de keypoints de ruedas (`ejes.pt`) para contar ejes (`2..6`).
- **Pasajeros (adicional)**: Segmentación anónima de personas dentro del vehículo (`yolo11n-seg.pt`) ocultando con máscara sólida.

## 1. Ejecución local (Windows PowerShell)

```powershell
cd inferencia
uv venv .venv --python 3.12
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt

# Opcional si aún no tienes vehiculos.pt / ejes.pt (solo pruebas locales):
$env:INFERENCE_DEMO = "1"
$env:INFERENCE_TOKEN = "dev"

python diagnostico.py
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

En Windows CPU tienes el freeze completo de referencia en `requirements-lock-windows-cpu.txt`.

## 2. Despliegue en RunPod (GPU Pod, +5 pts adicionales)

1. Crea un Pod con plantilla PyTorch 2.x (CUDA) y expón el puerto HTTP `8000`.
2. Configura las variables de entorno en el Pod: `INFERENCE_TOKEN`, `INFERENCE_DEMO=0`, y opcionalmente `M2_URL` / `M3_URL`.
3. Clona el repositorio en `/workspace` y ejecuta:

```bash
cd /workspace/sistema-peaje/inferencia
bash runpod_setup.sh
```

4. Si subiste `vehiculos.pt` y `ejes.pt` manualmente, colócalos en `inferencia/modelos/`.
5. Inicia el servidor:

```bash
source .venv/bin/activate
bash start.sh
```

6. Copia la URL HTTPS del puerto `8000` (ej. `https://<pod-id>-8000.proxy.runpod.net/predict`) en la variable `INFERENCE_URL` de Django. Verifica `GET /health`.

## 3. Despliegue alternativo en Google Colab

1. Monta Google Drive y clona el repo en `/content/sistema-peaje`.
2. Copia `vehiculos.pt` y `ejes.pt` a `/content/sistema-peaje/inferencia/modelos/`.
3. Instala `pip install -r inferencia/requirements.txt` y exporta `INFERENCE_TOKEN`.
4. Ejecuta `uvicorn main:app --host 0.0.0.0 --port 8000` dentro de `inferencia/` y publica el puerto por un túnel HTTPS autorizado vinculado al runtime de Colab.
