import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Title,
  Tooltip,
} from 'chart.js'
import {
  AlertTriangle,
  CarFront,
  Check,
  Coins,
  ImageOff,
  RefreshCw,
  Users,
} from 'lucide-react'
import { Bar, Doughnut } from 'react-chartjs-2'
import { Link } from 'react-router-dom'
import api from '../api'
import { useAuth } from '../auth/authContext'
import EstadoBadge from '../components/EstadoBadge'
import KpiCard from '../components/KpiCard'
import PasoDetalleModal from '../components/PasoDetalleModal'
import { useToast } from '../components/toastContext'
import { escuchar } from '../realtime'
import {
  etiquetaCategoria,
  etiquetaEstadoPaso,
  extraerErrorApi,
  formatBs,
  formatHora,
} from '../utils/format'

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
  Title
)

const COLORES_CATEGORIAS = [
  '#22c55e',
  '#3b82f6',
  '#f59e0b',
  '#8b5cf6',
  '#06b6d4',
]

export default function Dashboard() {
  const { esAdmin } = useAuth()
  const { mostrarToast } = useToast()

  const [casetas, setCasetas] = useState([])
  const [casetaId, setCasetaId] = useState('')
  const [fecha, setFecha] = useState('')
  const [resumen, setResumen] = useState(null)
  const [pasos, setPasos] = useState([])
  const [alertas, setAlertas] = useState([])
  const [nuevosIds, setNuevosIds] = useState(() => new Set())
  const [pasoSeleccionado, setPasoSeleccionado] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [resincronizando, setResincronizando] = useState(false)
  const [atendiendoId, setAtendiendoId] = useState(null)
  const [error, setError] = useState('')

  const inicializadoRef = useRef(false)
  const seenIdsRef = useRef(new Set())
  const filtroKeyRef = useRef('')
  const timersRef = useRef([])
  const recargarRef = useRef(null)

  const obtenerDatos = useCallback(async () => {
    const claveFiltro = `${casetaId}|${fecha}`
    if (filtroKeyRef.current !== claveFiltro) {
      filtroKeyRef.current = claveFiltro
      inicializadoRef.current = false
      seenIdsRef.current.clear()
    }

    const endpointResumen = casetaId
      ? `casetas/${casetaId}/resumen`
      : 'resumen'
    const paramsResumen = fecha ? { fecha } : {}
    const paramsPasos = { page_size: 12 }
    if (casetaId) paramsPasos.caseta = casetaId
    if (fecha) paramsPasos.fecha = fecha

    const [resResumen, resPasos, resAlertas] = await Promise.all([
      api.get(endpointResumen, { params: paramsResumen }),
      api.get('pasos/', { params: paramsPasos }),
      api.get('alertas/', { params: { atendida: false, page_size: 8 } }),
    ])

    const listaCruda = resPasos.data?.results || []
    const mapa = new Map()
    for (const p of listaCruda) {
      if (p?.id && !mapa.has(p.id)) {
        mapa.set(p.id, p)
      }
    }
    const listaUnica = Array.from(mapa.values())

    if (!inicializadoRef.current) {
      for (const p of listaUnica) {
        seenIdsRef.current.add(p.id)
      }
      inicializadoRef.current = true
    } else {
      const recienLlegados = []
      for (const p of listaUnica) {
        if (!seenIdsRef.current.has(p.id)) {
          seenIdsRef.current.add(p.id)
          recienLlegados.push(p.id)
        }
      }
      if (recienLlegados.length > 0) {
        setNuevosIds((prev) => {
          const next = new Set(prev)
          for (const id of recienLlegados) next.add(id)
          return next
        })
        const timer = setTimeout(() => {
          setNuevosIds((prev) => {
            const next = new Set(prev)
            for (const id of recienLlegados) next.delete(id)
            return next
          })
        }, 3200)
        timersRef.current.push(timer)
      }
    }

    setResumen(resResumen.data)
    setPasos(listaUnica)
    setAlertas(resAlertas.data?.results || [])
    setError('')
  }, [casetaId, fecha])

  useEffect(() => {
    recargarRef.current = obtenerDatos
  }, [obtenerDatos])

  useEffect(() => {
    let activo = true
    ;(async () => {
      try {
        const res = await api.get('casetas/')
        if (activo && Array.isArray(res.data)) {
          setCasetas(res.data)
        }
      } catch {
        // Las casetas pueden fallar silenciosamente sin bloquear resumen
      }
    })()
    return () => {
      activo = false
    }
  }, [])

  useEffect(() => {
    let activo = true
    ;(async () => {
      try {
        await obtenerDatos()
      } catch (err) {
        if (activo) {
          setError(extraerErrorApi(err, 'No se pudo cargar el panel.'))
        }
      } finally {
        if (activo) {
          setCargando(false)
          setResincronizando(false)
        }
      }
    })()
    return () => {
      activo = false
    }
  }, [obtenerDatos])

  useEffect(() => {
    return () => {
      for (const timer of timersRef.current) {
        clearTimeout(timer)
      }
      timersRef.current = []
    }
  }, [])

  useEffect(() => {
    let estadoPrevio = null

    const desuscribir = escuchar({
      onPaso: (payload) => {
        recargarRef.current?.().catch(() => {})
        mostrarToast({
          tipo: payload?.estado === 'pagado' ? 'success' : 'info',
          titulo: 'Nuevo paso detectado',
          mensaje: `Paso #${payload?.id ?? '—'} · Estado: ${etiquetaEstadoPaso(payload?.estado)}`,
        })
      },
      onAlerta: (payload, evento) => {
        recargarRef.current?.().catch(() => {})
        if (evento === 'nueva-alerta') {
          mostrarToast({
            tipo: 'warning',
            titulo: 'Nueva alerta operativa',
            mensaje: payload?.tipo
              ? `Tipo: ${payload.tipo} (#${payload?.id ?? ''})`
              : 'Se generó una nueva alerta en caseta.',
          })
        } else if (evento === 'alerta-atendida') {
          mostrarToast({
            tipo: 'info',
            titulo: 'Alerta atendida',
            mensaje: `La alerta #${payload?.id ?? ''} fue marcada como atendida.`,
          })
        }
      },
      onEstadoConexion: (estado) => {
        if (
          estadoPrevio &&
          estadoPrevio !== 'connected' &&
          estado === 'connected'
        ) {
          recargarRef.current?.().catch(() => {})
        }
        estadoPrevio = estado
      },
    })

    return desuscribir
  }, [mostrarToast])

  const handleResincronizar = async () => {
    setResincronizando(true)
    try {
      await obtenerDatos()
      mostrarToast({
        tipo: 'success',
        titulo: 'Datos sincronizados',
        mensaje: 'Se actualizaron métricas, pasos recientes y alertas.',
      })
    } catch (err) {
      setError(extraerErrorApi(err, 'No se pudo resincronizar el panel.'))
    } finally {
      setResincronizando(false)
    }
  }

  const handleAtenderAlerta = async (alertaId) => {
    setAtendiendoId(alertaId)
    try {
      await api.patch(`alertas/${alertaId}/`, { atendida: true })
      mostrarToast({
        tipo: 'success',
        titulo: 'Alerta atendida',
        mensaje: `Alerta #${alertaId} resuelta correctamente.`,
      })
      await obtenerDatos()
    } catch (err) {
      mostrarToast({
        tipo: 'error',
        titulo: 'Error al atender',
        mensaje: extraerErrorApi(err, 'No se pudo atender la alerta.'),
      })
    } finally {
      setAtendiendoId(null)
    }
  }

  const datosPorHora = useMemo(() => {
    const valores = Array.isArray(resumen?.por_hora)
      ? resumen.por_hora
      : Array(24).fill(0)
    return {
      labels: valores.map((_, h) => `${String(h).padStart(2, '0')}h`),
      datasets: [
        {
          label: 'Pasos',
          data: valores,
          backgroundColor: 'rgba(34, 197, 94, 0.75)',
          hoverBackgroundColor: '#22c55e',
          borderRadius: 5,
        },
      ],
    }
  }, [resumen])

  const opcionesBar = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0f172a',
          borderColor: 'rgba(148,163,184,0.2)',
          borderWidth: 1,
        },
      },
      scales: {
        x: {
          ticks: { color: '#94a3b8', font: { size: 11 } },
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          ticks: { color: '#94a3b8', precision: 0 },
          grid: { color: 'rgba(148, 163, 184, 0.12)' },
        },
      },
    }),
    []
  )

  const { datosCategoria, hayCategorias } = useMemo(() => {
    const mapa = resumen?.por_categoria || {}
    const entradas = Object.entries(mapa).filter(([, v]) => Number(v) > 0)
    return {
      hayCategorias: entradas.length > 0,
      datosCategoria: {
        labels: entradas.map(([k]) => etiquetaCategoria(k)),
        datasets: [
          {
            data: entradas.map(([, v]) => Number(v)),
            backgroundColor: entradas.map(
              (_, i) => COLORES_CATEGORIAS[i % COLORES_CATEGORIAS.length]
            ),
            borderColor: '#111827',
            borderWidth: 2,
          },
        ],
      },
    }
  }, [resumen])

  const opcionesDoughnut = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      cutout: '64%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: '#cbd5e1',
            padding: 14,
            usePointStyle: true,
            pointStyleWidth: 10,
          },
        },
      },
    }),
    []
  )

  return (
    <div className="page-stack">
      <div className="toolbar-card">
        <div className="toolbar-filters">
          <div className="field-inline">
            <label htmlFor="dash-caseta">Caseta</label>
            <select
              id="dash-caseta"
              value={casetaId}
              onChange={(e) => {
                setResincronizando(true)
                setCasetaId(e.target.value)
              }}
            >
              <option value="">Todas las casetas</option>
              {casetas.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nombre}
                </option>
              ))}
            </select>
          </div>

          <div className="field-inline">
            <label htmlFor="dash-fecha">Fecha</label>
            <input
              id="dash-fecha"
              type="date"
              value={fecha}
              onChange={(e) => {
                setResincronizando(true)
                setFecha(e.target.value)
              }}
            />
          </div>

          {fecha && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setResincronizando(true)
                setFecha('')
              }}
            >
              Hoy
            </button>
          )}
        </div>

        <button
          type="button"
          className="btn btn-secondary"
          onClick={handleResincronizar}
          disabled={resincronizando}
        >
          <RefreshCw size={16} className={resincronizando ? 'spin' : ''} />
          Resincronizar
        </button>
      </div>

      {error && (
        <div className="alert-banner alert-danger" role="alert">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      )}

      <div className="kpi-grid">
        <KpiCard
          titulo="Pasos hoy"
          valor={cargando ? '—' : resumen?.total_pasos ?? 0}
          subtitulo={`${resumen?.pagados ?? 0} pagados`}
          icono={CarFront}
          variante="info"
        />
        <KpiCard
          titulo="Recaudación hoy"
          valor={cargando ? '—' : formatBs(resumen?.recaudacion)}
          subtitulo="Solo pasos pagados"
          icono={Coins}
          variante="success"
        />
        <KpiCard
          titulo="Alertas pendientes"
          valor={cargando ? '—' : resumen?.alertas_pendientes ?? 0}
          subtitulo="Requieren revisión"
          icono={AlertTriangle}
          variante="warning"
        />
        <KpiCard
          titulo="Pasajeros"
          valor={cargando ? '—' : resumen?.pasajeros ?? 0}
          subtitulo={resumen?.fecha ? `Fecha: ${resumen.fecha}` : 'Conteo acumulado'}
          icono={Users}
          variante="default"
        />
      </div>

      <div className="charts-grid">
        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h2>Tráfico por hora</h2>
              <p className="muted text-sm">Distribución horaria (America/La_Paz)</p>
            </div>
          </div>
          <div className="chart-box">
            <Bar data={datosPorHora} options={opcionesBar} />
          </div>
        </section>

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h2>Por categoría</h2>
              <p className="muted text-sm">Clasificación vehicular detectada</p>
            </div>
          </div>
          <div className="chart-box chart-box-sm">
            {hayCategorias ? (
              <Doughnut data={datosCategoria} options={opcionesDoughnut} />
            ) : (
              <div className="chart-empty muted">
                Sin vehículos registrados en este periodo
              </div>
            )}
          </div>
        </section>
      </div>

      <div className="dashboard-bottom-grid">
        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h2>Pasos recientes</h2>
              <p className="muted text-sm">
                Haz clic en una fila para ver la evidencia completa
              </p>
            </div>
            <Link to="/pasos" className="btn btn-ghost btn-sm">
              Ver todos
            </Link>
          </div>

          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Evidencia</th>
                  <th>Placa</th>
                  <th>Categoría</th>
                  <th>Ejes</th>
                  <th>Pasajeros</th>
                  <th>Monto</th>
                  <th>Estado</th>
                  <th>Hora</th>
                </tr>
              </thead>
              <tbody>
                {cargando ? (
                  <tr>
                    <td colSpan={8} className="table-empty">
                      Cargando pasos recientes...
                    </td>
                  </tr>
                ) : pasos.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="table-empty">
                      No hay pasos registrados todavía.
                    </td>
                  </tr>
                ) : (
                  pasos.map((p) => (
                    <tr
                      key={p.id}
                      className={`clickable-row ${
                        nuevosIds.has(p.id) ? 'row-nueva' : ''
                      }`}
                      onClick={() => setPasoSeleccionado(p)}
                    >
                      <td>
                        {p.imagen ? (
                          <img
                            src={p.imagen}
                            alt={p.placa_normalizada || 'Evidencia'}
                            className="thumb-img"
                          />
                        ) : (
                          <span className="thumb-placeholder">
                            <ImageOff size={14} />
                          </span>
                        )}
                      </td>
                      <td>
                        <strong className="mono-plate">
                          {p.placa_normalizada || p.placa_leida || '—'}
                        </strong>
                      </td>
                      <td>{etiquetaCategoria(p.categoria_detectada)}</td>
                      <td>{p.ejes_detectados ?? '—'}</td>
                      <td>
                        {p.pasajeros !== null && p.pasajeros !== undefined
                          ? p.pasajeros
                          : 'N/D'}
                      </td>
                      <td>{formatBs(p.monto)}</td>
                      <td>
                        <EstadoBadge estado={p.estado} />
                      </td>
                      <td className="mono">{formatHora(p.created_at)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h2>Alertas pendientes</h2>
              <p className="muted text-sm">Incidencias sin atender</p>
            </div>
            <Link to="/alertas" className="btn btn-ghost btn-sm">
              Gestionar
            </Link>
          </div>

          {cargando ? (
            <p className="muted">Cargando alertas...</p>
          ) : alertas.length === 0 ? (
            <div className="empty-inline">
              No hay alertas pendientes en este momento.
            </div>
          ) : (
            <ul className="alerts-list">
              {alertas.map((alerta) => (
                <li key={alerta.id} className="alert-row-item">
                  <div className="alert-row-main">
                    <div className="alert-row-top">
                      <span className="alert-type-tag">{alerta.tipo}</span>
                      <span className="mono text-xs muted">
                        {formatHora(alerta.created_at)}
                      </span>
                    </div>
                    <div className="alert-row-sub">
                      <strong className="mono-plate">
                        {alerta.paso?.placa_normalizada ||
                          alerta.paso?.placa_leida ||
                          'Sin placa'}
                      </strong>
                      <span className="muted">
                        · {alerta.paso?.caseta_nombre || 'Caseta N/D'}
                      </span>
                    </div>
                    <div className="alert-row-badges">
                      <EstadoBadge estado={alerta.paso?.estado} />
                      {alerta.paso && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs"
                          onClick={() => setPasoSeleccionado(alerta.paso)}
                        >
                          Ver paso
                        </button>
                      )}
                    </div>
                  </div>

                  {esAdmin && (
                    <button
                      type="button"
                      className="btn btn-primary btn-xs"
                      disabled={atendiendoId === alerta.id}
                      onClick={() => handleAtenderAlerta(alerta.id)}
                    >
                      <Check size={14} />
                      {atendiendoId === alerta.id ? '...' : 'Atender'}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <PasoDetalleModal
        paso={pasoSeleccionado}
        onCerrar={() => setPasoSeleccionado(null)}
      />
    </div>
  )
}
