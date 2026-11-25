import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  Code2,
  ImagePlus,
  Loader2,
  Play,
  RotateCcw,
} from 'lucide-react'
import api from '../api'
import { etiquetaCategoria, extraerErrorApi } from '../utils/format'

const CONFIG_MODOS = {
  m1: {
    titulo: 'Prueba individual · M1 (Placas + OCR)',
    subtitulo:
      'Ejecuta únicamente el detector de placas YOLOv9-t ONNX y fast-plate-ocr sin correr M2, M3 ni M4.',
    endpointHint: 'POST /api/v1/pruebas/inferencia (modo=m1)',
    tip: 'Ideal para probar fotos frontales o recortes de placas bolivianas (3–4 dígitos + 3 letras).',
  },
  m2: {
    titulo: 'Prueba individual · M2 (Segmentación vehicular)',
    subtitulo:
      'Ejecuta únicamente vehiculos.pt (YOLOv8n-seg) para visualizar máscaras, cajas y clases (auto, bus, camion, minibus, moto).',
    endpointHint: 'POST /api/v1/pruebas/inferencia (modo=m2)',
    tip: 'No exige placa ni ejes: sirve para cualquier foto de vehículo desde cualquier ángulo.',
  },
  m3: {
    titulo: 'Prueba individual · M3 (Ejes y llantas)',
    subtitulo:
      'Ejecuta únicamente ejes.pt (YOLO-pose) para detectar llantas/keypoints y contar los ejes visibles.',
    endpointHint: 'POST /api/v1/pruebas/inferencia (modo=m3)',
    tip: 'No exige placa: ideal para probar fotos laterales o 3/4 de autos, minibuses y camiones.',
  },
  m4: {
    titulo: 'Prueba individual · M4 (Pasajeros / Personas)',
    subtitulo:
      'Ejecuta únicamente pasajeros.pt (YOLOv8n-seg COCO, clase person ID 0) dibujando máscaras opacas sin rostros.',
    endpointHint: 'POST /api/v1/pruebas/inferencia (modo=m4)',
    tip: 'No exige placa ni ejes: ideal para validar segmentación de ocupantes y privacidad sin rostros.',
  },
}

function ResumenResultado({ modo, resultado }) {
  if (!resultado) return null

  if (modo === 'm1') {
    const conf =
      resultado.confianza !== null && resultado.confianza !== undefined
        ? `${(Number(resultado.confianza) * 100).toFixed(1)}%`
        : '—'
    return (
      <div className="detail-list">
        <div className="detail-row">
          <span>Placa válida (formato BO)</span>
          <strong className="mono-plate">{resultado.placa || 'Sin placa válida'}</strong>
        </div>
        <div className="detail-row">
          <span>Lectura cruda (OCR)</span>
          <span className="mono">{resultado.placa_cruda || '—'}</span>
        </div>
        <div className="detail-row">
          <span>Confianza OCR</span>
          <span>{conf}</span>
        </div>
        <div className="detail-row">
          <span>Latencia</span>
          <span>{resultado.latencia_ms ?? '—'} ms</span>
        </div>
      </div>
    )
  }

  if (modo === 'm2') {
    const lista = Array.isArray(resultado.vehiculos) ? resultado.vehiculos : []
    return (
      <div className="detail-list">
        <div className="detail-row">
          <span>Vehículos detectados</span>
          <strong>{resultado.total_vehiculos ?? lista.length}</strong>
        </div>
        <div className="detail-row">
          <span>Latencia</span>
          <span>{resultado.latencia_ms ?? '—'} ms</span>
        </div>
        {lista.map((v) => (
          <div key={v.id_deteccion} className="detail-row">
            <span className="mono">{v.id_deteccion}</span>
            <span>
              <strong>{etiquetaCategoria(v.categoria)}</strong> ({(v.confianza * 100).toFixed(1)}%)
              {v.mascara_disponible ? ' · máscara OK' : ''}
            </span>
          </div>
        ))}
      </div>
    )
  }

  if (modo === 'm3') {
    const lista = Array.isArray(resultado.detecciones) ? resultado.detecciones : []
    return (
      <div className="detail-list">
        <div className="detail-row">
          <span>Modo M3 activo</span>
          <span className="mono">{resultado.modo_m3 || '—'}</span>
        </div>
        <div className="detail-row">
          <span>Ejes / llantas detectados</span>
          <strong>{resultado.ejes_detectados ?? 0}</strong>
        </div>
        <div className="detail-row">
          <span>Latencia</span>
          <span>{resultado.latencia_ms ?? '—'} ms</span>
        </div>
        {lista.map((d) => (
          <div key={d.indice} className="detail-row">
            <span className="mono">e{d.indice}</span>
            <span>
              {d.conf_llanta !== undefined
                ? `Conf. llanta ${(d.conf_llanta * 100).toFixed(1)}% · centro [${d.centro?.join(', ')}]`
                : `Ejes visibles: ${d.ejes_visibles ?? 0}`}
            </span>
          </div>
        ))}
      </div>
    )
  }

  // m4
  const personas = Array.isArray(resultado.personas) ? resultado.personas : []
  return (
    <div className="detail-list">
      <div className="detail-row">
        <span>Personas / pasajeros segmentados</span>
        <strong>{resultado.total_personas ?? personas.length}</strong>
      </div>
      <div className="detail-row">
        <span>Privacidad</span>
        <span>Máscaras opacas (sin rostros)</span>
      </div>
      <div className="detail-row">
        <span>Latencia</span>
        <span>{resultado.latencia_ms ?? '—'} ms</span>
      </div>
      {personas.map((p) => (
        <div key={p.indice} className="detail-row">
          <span className="mono">PAX #{p.indice}</span>
          <span>
            person (ID 0) · {(p.confianza * 100).toFixed(1)}%
            {p.mascara_disponible ? ' · máscara OK' : ''}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function PruebaModelo({ modo }) {
  const cfg = CONFIG_MODOS[modo] || CONFIG_MODOS.m1
  const inputRef = useRef(null)

  const [archivo, setArchivo] = useState(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [ejecutando, setEjecutando] = useState(false)
  const [resultado, setResultado] = useState(null)
  const [error, setError] = useState('')
  const [verJson, setVerJson] = useState(false)

  useEffect(() => {
    setResultado(null)
    setError('')
    setVerJson(false)
  }, [modo])

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [previewUrl])

  const seleccionarArchivo = (evento) => {
    const file = evento.target.files?.[0]
    evento.target.value = ''
    if (!file) return
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setArchivo(file)
    setPreviewUrl(URL.createObjectURL(file))
    setResultado(null)
    setError('')
  }

  const ejecutarPrueba = async () => {
    if (!archivo || ejecutando) return
    setEjecutando(true)
    setError('')
    try {
      const formData = new FormData()
      formData.append('file', archivo)
      formData.append('modo', modo)
      const res = await api.post('pruebas/inferencia', formData)
      setResultado(res.data)
    } catch (err) {
      setError(extraerErrorApi(err, `No se pudo ejecutar la prueba de ${modo.toUpperCase()}.`))
    } finally {
      setEjecutando(false)
    }
  }

  const limpiar = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setArchivo(null)
    setPreviewUrl('')
    setResultado(null)
    setError('')
  }

  const jsonSinImagen = resultado
    ? { ...resultado, evidencia: resultado.evidencia ? '<base64 JPEG>' : null }
    : null

  return (
    <div className="page-stack">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h2>{cfg.titulo}</h2>
            <p className="muted text-sm">{cfg.subtitulo}</p>
            <p className="mono text-xs muted" style={{ marginTop: '0.35rem' }}>
              {cfg.endpointHint} · No registra pasos ni cobra peaje
            </p>
          </div>
        </div>

        <p className="text-sm muted" style={{ marginBottom: '1rem' }}>
          {cfg.tip}
        </p>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={seleccionarArchivo}
          />
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => inputRef.current?.click()}
            disabled={ejecutando}
          >
            <ImagePlus size={16} />
            {archivo ? 'Cambiar imagen' : 'Seleccionar imagen'}
          </button>

          <button
            type="button"
            className="btn btn-primary"
            onClick={ejecutarPrueba}
            disabled={!archivo || ejecutando}
          >
            {ejecutando ? (
              <>
                <Loader2 size={16} className="spin" />
                Analizando {modo.toUpperCase()}...
              </>
            ) : (
              <>
                <Play size={16} />
                Ejecutar {modo.toUpperCase()}
              </>
            )}
          </button>

          {archivo && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={limpiar}
              disabled={ejecutando}
            >
              <RotateCcw size={15} />
              Limpiar
            </button>
          )}

          {archivo && (
            <span className="mono text-xs muted">{archivo.name}</span>
          )}
        </div>
      </section>

      {error && (
        <div className="alert-banner alert-danger" role="alert">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      )}

      {(previewUrl || resultado) && (
        <div className="panel-card">
          <div className="paso-detail-grid">
            <div className="paso-detail-image">
              <div className="evidence-frame">
                <img
                  src={resultado?.evidencia || previewUrl}
                  alt={`Resultado ${modo.toUpperCase()}`}
                />
              </div>
              <p className="text-xs muted" style={{ marginTop: '0.45rem' }}>
                {resultado?.evidencia
                  ? `Imagen anotada devuelta por ${modo.toUpperCase()}`
                  : 'Vista previa local (haz clic en Ejecutar para ver el resultado de la IA)'}
              </p>
            </div>

            <div className="paso-detail-meta">
              {resultado ? (
                <>
                  <ResumenResultado modo={modo} resultado={resultado} />
                  <div style={{ marginTop: '1rem' }}>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setVerJson((v) => !v)}
                    >
                      <Code2 size={15} />
                      {verJson ? 'Ocultar JSON' : 'Ver JSON de respuesta'}
                    </button>
                  </div>
                  {verJson && (
                    <pre
                      className="mono text-xs"
                      style={{
                        marginTop: '0.6rem',
                        padding: '0.75rem',
                        borderRadius: '8px',
                        background: 'rgba(15, 23, 42, 0.7)',
                        overflowX: 'auto',
                        maxHeight: '260px',
                      }}
                    >
                      {JSON.stringify(jsonSinImagen, null, 2)}
                    </pre>
                  )}
                </>
              ) : (
                <p className="muted text-sm">
                  Imagen cargada. Presiona <strong>Ejecutar {modo.toUpperCase()}</strong> para ver el resultado individual de este modelo.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
