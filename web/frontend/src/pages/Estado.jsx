import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  Cpu,
  Database,
  Radio,
  RefreshCw,
  Server,
} from 'lucide-react'
import api from '../api'
import EstadoBadge from '../components/EstadoBadge'
import { realtimeConfigurado } from '../realtime'
import { extraerErrorApi, formatFechaHora } from '../utils/format'

function renderValorGpu(gpu) {
  if (gpu === undefined || gpu === null) return 'N/D'
  if (typeof gpu === 'boolean') return gpu ? 'Disponible' : 'No disponible (CPU)'
  if (typeof gpu === 'object') return JSON.stringify(gpu)
  return String(gpu)
}

function renderModelos(modelos) {
  if (!modelos) return null
  if (Array.isArray(modelos)) {
    if (modelos.length === 0) return <span className="muted">Sin modelos reportados</span>
    return (
      <ul className="models-list">
        {modelos.map((m, idx) => (
          <li key={idx}>
            <span>{typeof m === 'object' ? JSON.stringify(m) : String(m)}</span>
          </li>
        ))}
      </ul>
    )
  }
  if (typeof modelos === 'object') {
    const entries = Object.entries(modelos)
    if (entries.length === 0) return <span className="muted">Sin modelos reportados</span>
    return (
      <ul className="models-list">
        {entries.map(([nombre, valor]) => (
          <li key={nombre}>
            <span className="mono">{nombre}</span>
            <span className="muted">
              {typeof valor === 'boolean'
                ? valor
                  ? 'Cargado'
                  : 'No cargado'
                : typeof valor === 'object'
                  ? JSON.stringify(valor)
                  : String(valor)}
            </span>
          </li>
        ))}
      </ul>
    )
  }
  return <span>{String(modelos)}</span>
}

export default function Estado() {
  const [estado, setEstado] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [actualizando, setActualizando] = useState(false)
  const [error, setError] = useState('')
  const [ultimaLectura, setUltimaLectura] = useState(null)

  const cargarEstado = useCallback(async () => {
    const res = await api.get('estado')
    setEstado(res.data)
    setUltimaLectura(new Date().toISOString())
    setError('')
  }, [])

  useEffect(() => {
    let activo = true
    ;(async () => {
      try {
        await cargarEstado()
      } catch (err) {
        if (activo) {
          setError(extraerErrorApi(err, 'No se pudo consultar el estado del sistema.'))
        }
      } finally {
        if (activo) setCargando(false)
      }
    })()

    const intervalo = setInterval(() => {
      cargarEstado().catch((err) => {
        if (activo) {
          setError(extraerErrorApi(err, 'Error al actualizar el estado.'))
        }
      })
    }, 15000)

    return () => {
      activo = false
      clearInterval(intervalo)
    }
  }, [cargarEstado])

  const handleActualizar = async () => {
    setActualizando(true)
    try {
      await cargarEstado()
    } catch (err) {
      setError(extraerErrorApi(err, 'No se pudo actualizar el estado.'))
    } finally {
      setActualizando(false)
    }
  }

  const inf = estado?.inferencia
  const detalle = inf?.detalle
  const pusherFront = realtimeConfigurado()

  return (
    <div className="page-stack">
      <div className="toolbar-card">
        <div className="muted text-sm">
          Actualización automática cada 15 segundos
          {ultimaLectura ? ` · Última consulta: ${formatFechaHora(ultimaLectura)}` : ''}
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={handleActualizar}
          disabled={actualizando}
        >
          <RefreshCw size={16} className={actualizando ? 'spin' : ''} />
          Actualizar
        </button>
      </div>

      {error && (
        <div className="alert-banner alert-danger" role="alert">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      )}

      {cargando ? (
        <div className="panel-card empty-state">
          <div className="spinner" />
          <p className="muted">Consultando estado de servicios...</p>
        </div>
      ) : (
        <div className="status-grid">
          <section className="panel-card status-card">
            <div className="status-card-header">
              <div className="status-title-wrap">
                <Server size={20} className="text-green" />
                <h2>Backend API</h2>
              </div>
              <EstadoBadge estado={estado?.backend || 'error'} />
            </div>
            <div className="detail-list">
              <div className="detail-row">
                <span>Estado</span>
                <span>{estado?.backend || '—'}</span>
              </div>
              <div className="detail-row">
                <span>Hora del servidor</span>
                <span className="mono">{formatFechaHora(estado?.hora)}</span>
              </div>
            </div>
          </section>

          <section className="panel-card status-card">
            <div className="status-card-header">
              <div className="status-title-wrap">
                <Database size={20} className="text-green" />
                <h2>Base de datos</h2>
              </div>
              <EstadoBadge
                estado={estado?.base_datos === 'ok' ? 'ok' : 'error'}
                texto={estado?.base_datos === 'ok' ? 'Conectada' : 'Error'}
              />
            </div>
            <div className="detail-list">
              <div className="detail-row">
                <span>Respuesta</span>
                <span>{estado?.base_datos || '—'}</span>
              </div>
            </div>
          </section>

          <section className="panel-card status-card status-card-wide">
            <div className="status-card-header">
              <div className="status-title-wrap">
                <Cpu size={20} className="text-green" />
                <h2>Servicio de Inferencia (IA)</h2>
              </div>
              <EstadoBadge
                estado={inf?.disponible ? 'ok' : 'error'}
                texto={inf?.disponible ? 'Disponible' : 'No disponible'}
              />
            </div>

            {detalle?.demo && (
              <div className="alert-banner alert-warning" style={{ marginBottom: '0.85rem' }}>
                <AlertTriangle size={18} />
                <span>
                  Advertencia: el servicio de inferencia se encuentra en modo{' '}
                  <strong>MOCK / DEMO</strong>.
                </span>
              </div>
            )}

            {detalle?.modelos?.m2_segmentacion && !detalle?.modelos?.m3_keypoints && !detalle?.demo && (
              <div className="alert-banner alert-warning" style={{ marginBottom: '0.85rem' }}>
                <AlertTriangle size={18} />
                <span>
                  M2 (segmentación de vehículos) activo en modo real. Conteo de ejes{' '}
                  <strong>pendiente de M3</strong> (no se generan tarifas definitivas hasta cargar{' '}
                  <code>ejes.pt</code>).
                </span>
              </div>
            )}

            {inf?.error && (
              <div className="alert-banner alert-danger" style={{ marginBottom: '0.85rem' }}>
                <AlertTriangle size={18} />
                <span>{inf.error}</span>
              </div>
            )}

            <div className="detail-list">
              <div className="detail-row">
                <span>URL configurada</span>
                <span className="mono text-sm">{inf?.url_configurada ? 'Activa' : 'No configurada'}</span>
              </div>
              <div className="detail-row">
                <span>Modo de ejecución</span>
                <span className="mono">{detalle?.modo_ejecucion || '—'}</span>
              </div>
              <div className="detail-row">
                <span>Latencia</span>
                <span>
                  {inf?.latencia_ms !== null && inf?.latencia_ms !== undefined
                    ? `${inf.latencia_ms} ms`
                    : '—'}
                </span>
              </div>
              <div className="detail-row">
                <span>Aceleración GPU</span>
                <span>{renderValorGpu(detalle?.gpu)}</span>
              </div>
              {detalle?.m2?.cargado && (
                <>
                  <div className="detail-row">
                    <span>M2 (CONF / IoU)</span>
                    <span className="mono">
                      {detalle.m2.conf_umbral} / {detalle.m2.iou_umbral}
                    </span>
                  </div>
                  <div className="detail-row">
                    <span>Clases M2</span>
                    <span className="mono text-sm">
                      {Array.isArray(detalle.clases_m2) ? detalle.clases_m2.join(', ') : '—'}
                    </span>
                  </div>
                </>
              )}
              {detalle?.m3?.cargado && (
                <>
                  <div className="detail-row">
                    <span>M3 (CONF / KPT / IoU)</span>
                    <span className="mono">
                      {detalle.m3.conf_umbral} / {detalle.m3.conf_keypoint} / {detalle.m3.iou_asociacion}
                    </span>
                  </div>
                  <div className="detail-row">
                    <span>M3 esquema Pose</span>
                    <span className="mono text-sm">
                      {Array.isArray(detalle.m3.kpt_shape)
                        ? `kpt_shape [${detalle.m3.kpt_shape.join(', ')}] (${detalle.m3.modo_m3 || 'pose'})`
                        : '—'}
                    </span>
                  </div>
                </>
              )}
              {detalle?.m4?.cargado && (
                <>
                  <div className="detail-row">
                    <span>M4 Pasajeros (CONF / IoU)</span>
                    <span className="mono">
                      {detalle.m4.conf_umbral} / {detalle.m4.iou_umbral}
                    </span>
                  </div>
                  <div className="detail-row">
                    <span>M4 Modelo / Clase</span>
                    <span className="mono text-sm">
                      {detalle.m4.manifiesto?.arquitectura || 'YOLOv8n-seg'} · person (ID 0)
                    </span>
                  </div>
                </>
              )}
            </div>

            {detalle?.modelos && (
              <div className="models-section">
                <h3>Modelos cargados</h3>
                {renderModelos(detalle.modelos)}
              </div>
            )}
          </section>

          <section className="panel-card status-card">
            <div className="status-card-header">
              <div className="status-title-wrap">
                <Radio size={20} className="text-green" />
                <h2>Pusher / Tiempo real</h2>
              </div>
              <EstadoBadge
                estado={estado?.pusher?.configurado ? 'ok' : 'pendiente'}
                texto={
                  estado?.pusher?.configurado ? 'Configurado' : 'No configurado'
                }
              />
            </div>
            <div className="detail-list">
              <div className="detail-row">
                <span>Backend Pusher</span>
                <span>
                  {estado?.pusher?.configurado ? 'Habilitado' : 'Sin credenciales'}
                </span>
              </div>
              <div className="detail-row">
                <span>Frontend Pusher</span>
                <span>
                  {pusherFront ? 'Habilitado' : 'Pendiente (.env)'}
                </span>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
