# Informe Técnico: Datasets, Fuentes y Métricas Reales del Proyecto

Este documento reúne las fuentes verificables de los datasets originales y adaptados, las transformaciones realizadas y las métricas reales medidas sobre los conjuntos de evaluación del sistema **Smart Peaje**. No incluye credenciales, API keys ni enlaces temporales de descarga.

---

## 1. Fuentes de Datasets (Originales vs. Adaptados)

### 1.1 M1 — Detección de placas y OCR (reutilizado del laboratorio anterior)
- **Origen verificable:** artefactos del laboratorio previo contenidos en la carpeta `/placas/` del repositorio (conservados sin modificaciones):
  - **Detector de placas:** `placas/modelo/yolo-v9-t-384-license-plates-end2end.onnx` (YOLOv9-t exportado a ONNX, entrada `384×384`, lógica de preproceso y decodificación en `placas/detector.py`).
  - **Reconocimiento OCR:** `placas/modelo/cct_xs_v2_global.onnx` + `placas/modelo/cct_xs_v2_global_plate_config.yaml`, ejecutado con la librería `fast-plate-ocr` (`LicensePlateRecognizer`, ver `placas/placas_fastocr.py`).
  - **Integración en el servicio:** `inferencia/ocr_adapter.py` (normalización a mayúsculas alfanuméricas y validación de formato boliviano `^\d{3,4}[A-Z]{3}$`).
- **Nota de trazabilidad:** no se incorporan enlaces externos de datasets no comprobables para M1; se documentan exclusivamente los artefactos presentes en `/placas/`.

---

### 1.2 M2 — Segmentación de instancias vehiculares (`vehiculos.pt`)
| Concepto | Detalle |
|---|---|
| **Dataset público original** | **Vehicle Classification V2**, versión 1, Roboflow Universe |
| **Enlace oficial** | https://universe.roboflow.com/franz-orozco/vehicle-classification-v2-t9ukm/dataset/1 |
| **Formato original** | YOLOv8 Segmentation (`yolov8`) |
| **Volumen original** | 3.680 imágenes |
| **Transformaciones y limpieza (dataset adaptado)** | Filtrado de imágenes inconsistentes/duplicadas, validación de polígonos de segmentación y normalización a las 5 clases requeridas por el tarifario (`auto`, `bus`, `camion`, `minibus`, `moto`) |
| **Distribución final (adaptado)** | **1.798 imágenes** totales: **1.268 entrenamiento**, **367 validación** y **163 prueba** |
| **Notebook de entrenamiento** | `entrenamiento/M2_segmentacion.ipynb` (`yolov8n-seg.pt`, `imgsz=640`) |

---

### 1.3 M3 — Detección y conteo de ejes (`ejes.pt`)

#### Datasets públicos originales
1. **Vehicle Wheel Pose** (Roboflow Universe)
   - **Autor / Workspace:** `trafficanalyse`
   - **Enlace oficial:** https://universe.roboflow.com/trafficanalyse/vehicle_wheel_pose
   - **Formato original:** COCO JSON (cajas de vehículos y anotaciones de ruedas)
   - **Licencia:** según términos publicados en la ficha del proyecto en Roboflow Universe.
2. **Truck Image Dataset v2.0.0** (Universidad de São Paulo, Brasil)
   - **Autores:** Leandro Arab Marcomini y André Luiz Cunha
   - **Enlace oficial (Zenodo):** https://zenodo.org/records/7695824
   - **DOI:** https://doi.org/10.5281/zenodo.7695824
   - **Publicación científica relacionada:** Marcomini, L. A., & Cunha, A. L. (2022). *Truck Axle Detection with Convolutional Neural Networks*. https://arxiv.org/abs/2204.01868
   - **Licencia:** **Creative Commons Attribution 4.0 International (CC BY 4.0)** (permite compartir y adaptar con atribución explícita a los autores y a Zenodo 7695824).
   - **Formato original:** anotaciones de vehículos pesados y posiciones de ejes/ruedas en vista lateral.

#### Dataset adaptado y combinado del proyecto (`m3_adaptado_v2`)
- **Diferenciación respecto a los originales:** ambos datasets públicos fueron procesados, normalizados y combinados mediante scripts propios en un único dataset YOLO-pose estandarizado para el peaje.
- **Transformaciones realizadas:**
  - Conversión de etiquetas a una sola clase denominada `vehiculo`.
  - Esquema uniforme de keypoints `kpt_shape: [7, 3]` (`eje_1` a `eje_7`, ordenados espacialmente de frente a atrás, con visibilidad `v ∈ {0, 2}`).
  - Deduplicación estricta por hash MD5 (`0` duplicados cruzados y `0` fuga de escenas entre `train`, `valid` y `test`).
  - Auditoría manual de casos extremos con >7 ejes (camiones rodotrem de 9 ejes).
- **Distribución final (adaptado):** **1.513 imágenes** y **3.619 instancias vehiculares**, distribuidas en:
  - **Entrenamiento (`train`):** 1.031 imágenes (2.738 instancias)
  - **Validación (`valid`):** 318 imágenes (612 instancias)
  - **Prueba (`test`):** 164 imágenes (269 instancias)
- **Scripts de conversión propios:**
  - `entrenamiento/convertir_coco_m3.py` (conversión inicial v1)
  - `entrenamiento/convertir_m3_v2.py` (combinación y validación v2 con USP Truck Image Dataset v2.0.0)
- **Notebook de entrenamiento:** `entrenamiento/M3_keypoints.ipynb` (`yolov8n-pose.pt`, `imgsz=640`).

---

## 2. Métricas Reales de Modelos de Visión por Computadora

| Modelo | Dataset adaptado (train / valid / test) | Clases / Keypoints | Métrica principal | Valor medido |
|---|---|---|---|---|
| **M1 (Detector + OCR)** | Artefactos `/placas/` (YOLOv9-t ONNX + `fast-plate-ocr` CCT ONNX) | Placas bolivianas (`^\d{3,4}[A-Z]{3}$`) | Exactitud OCR en pruebas locales (`evaluar_ocr.py`) | Validado sobre capturas reales (ej. `9000LAB` 97.75%, `2432UYN` 100%, `4257XCR` 99.99%) |
| **M2 (`vehiculos.pt`)** | 1.798 imágenes (`1.268 / 367 / 163`) | `auto, bus, camion, minibus, moto` | `box_mAP50` / `mask_mAP50` / `mask_mAP50-95` (test) | `0.9455` / `0.9443` / `0.8814` |
| **M3 (`ejes_v2`, `kpt_shape: [7, 3]`)** | 1.513 imágenes, 3.619 instancias (`1.031 / 318 / 164`) | `vehiculo` (`eje_1..eje_7`) | `mAP50(P)` / `mAP50-95(P)` (test) | `0.8933` / `0.8471` |
| **M3 (Conteo de ejes v2)** | 269 instancias en `test` (246 detectadas) | 2 a 7 ejes visibles | Exactitud entre detectados / MAE | `95.93%` (`236/246`) / `MAE = 0.0528` |
| **Pasajeros (`yolo11n-seg.pt`)** | Pesos preentrenados COCO (`person`) | Clase `person` (máscara opaca sin rostros) | Conteo anónimo integrado en `pasos.pasajeros` | Activo en inferencia |

## 3. Latencia y Tiempo Real

| Métrica | Procedimiento de medición | p50 (ms) | p95 (ms) | Observaciones |
|---|---|---|---|---|
| **Inferencia completa local (CPU)** | Validación de integración M1+M2+M3 (`reporte_integracion_completa.json`) | `260 ms` | — | En GPU (RunPod) se espera `< 100 ms` |
| **Inferencia M1 (`evaluar_ocr.py`)** | `python inferencia/evaluar_ocr.py <carpeta>` | _Completar en nube_ | _Completar en nube_ | |
| **Latencia extremo a extremo** | Envío desde app móvil hasta respuesta de `/pasos/frame` | _Completar en nube_ | _Completar en nube_ | |
| **Tasa de capturas rechazadas** | Capturas con HTTP 422 / total capturas × 100 | _Completar en pruebas_ | — | |
| **Latencia tiempo real (Pusher)** | Desde confirmación de registro hasta actualización en panel React | _Completar en nube_ | _Completar en nube_ | |
