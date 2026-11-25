import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Check, Eye, ImageOff } from 'lucide-react'
import api from '../api'
import { useAuth } from '../auth/authContext'
import EstadoBadge from '../components/EstadoBadge'
import Paginacion from '../components/Paginacion'
import PasoDetalleModal from '../components/PasoDetalleModal'
import { useToast } from '../components/toastContext'
import { escuchar } from '../realtime'
import {
  etiquetaCategoria,
  extraerErrorApi,
  formatBs,
  formatFechaHora,
} from '../utils/format'

const TAMANIO_PAGINA = 25

export default function Alertas() {
  const { esAdmin } = useAuth()
  const { mostrarToast } = useToast()

  const [filtroAtendida, setFiltroAtendida] = useState('false')
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState({ count: 0, results: [] })
  const [cargando, setCargando] = useState(true)
  const [atendiendoId, setAtendiendoId] = useState(null)
  const [error, setError] = useState('')
  const [pasoSeleccionado, setPasoSeleccionado] = useState(null)

  const recargarRef = useRef(null)

  const cargarAlertas = useCallback(async () => {
    const params = {
      page: pagina,
      page_size: TAMANIO_PAGINA,
    }
    if (filtroAtendida !== '') {
      params.atendida = filtroAtendida
    }
    const res = await api.get('alertas/', { params })
    setDatos({
      count: res.data?.count ?? 0,
      results: res.data?.results || [],
    })
    setError('')
  }, [filtroAtendida, pagina])

  useEffect(() => {
    recargarRef.current = cargarAlertas
  }, [cargarAlertas])

  useEffect(() => {
    let activo = true
    ;(async () => {
      try {
        await cargarAlertas()
      } catch (err) {
        if (activo) {
          setError(extraerErrorApi(err, 'No se pudieron cargar las alertas.'))
        }
      } finally {
        if (activo) setCargando(false)
      }
    })()
    return () => {
      activo = false
    }
  }, [cargarAlertas])

  useEffect(() => {
    const desuscribir = escuchar({
      onAlerta: (payload, evento) => {
        recargarRef.current?.().catch(() => {})
        if (evento === 'nueva-alerta') {
          mostrarToast({
            tipo: 'warning',
            titulo: 'Nueva alerta recibida',
            mensaje: payload?.tipo
              ? `Tipo: ${payload.tipo}`
              : 'Se registró una alerta en tiempo real.',
          })
        } else if (evento === 'alerta-atendida') {
          mostrarToast({
            tipo: 'info',
            titulo: 'Alerta atendida',
            mensaje: `Alerta #${payload?.id ?? ''} actualizada.`,
          })
        }
      },
    })
    return desuscribir
  }, [mostrarToast])

  const handleAtender = async (id) => {
    setAtendiendoId(id)
    try {
      await api.patch(`alertas/${id}/`, { atendida: true })
      mostrarToast({
        tipo: 'success',
        titulo: 'Alerta atendida',
        mensaje: `La alerta #${id} fue marcada como atendida.`,
      })
      await cargarAlertas()
    } catch (err) {
      mostrarToast({
        tipo: 'error',
        titulo: 'No se pudo atender',
        mensaje: extraerErrorApi(err, 'Error al actualizar la alerta.'),
      })
    } finally {
      setAtendiendoId(null)
    }
  }

  return (
    <div className="page-stack">
      <div className="toolbar-card">
        <div className="segmented-tabs" role="tablist" aria-label="Filtrar alertas">
          <button
            type="button"
            className={`tab-btn ${filtroAtendida === 'false' ? 'active' : ''}`}
            onClick={() => {
              setCargando(true)
              setFiltroAtendida('false')
              setPagina(1)
            }}
          >
            Pendientes
          </button>
          <button
            type="button"
            className={`tab-btn ${filtroAtendida === 'true' ? 'active' : ''}`}
            onClick={() => {
              setCargando(true)
              setFiltroAtendida('true')
              setPagina(1)
            }}
          >
            Atendidas
          </button>
          <button
            type="button"
            className={`tab-btn ${filtroAtendida === '' ? 'active' : ''}`}
            onClick={() => {
              setCargando(true)
              setFiltroAtendida('')
              setPagina(1)
            }}
          >
            Todas
          </button>
        </div>

        {!esAdmin && (
          <span className="muted text-sm">
            Solo los administradores pueden marcar alertas como atendidas.
          </span>
        )}
      </div>

      {error && (
        <div className="alert-banner alert-danger" role="alert">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      )}

      <div className="panel-card">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Evidencia</th>
                <th>Tipo de alerta</th>
                <th>Placa</th>
                <th>Categoría</th>
                <th>Caseta</th>
                <th>Monto</th>
                <th>Estado paso</th>
                <th>Estado alerta</th>
                <th>Fecha</th>
                <th className="text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {cargando ? (
                <tr>
                  <td colSpan={10} className="table-empty">
                    Cargando alertas...
                  </td>
                </tr>
              ) : datos.results.length === 0 ? (
                <tr>
                  <td colSpan={10} className="table-empty">
                    No hay alertas para el filtro seleccionado.
                  </td>
                </tr>
              ) : (
                datos.results.map((alerta) => {
                  const paso = alerta.paso
                  return (
                    <tr key={alerta.id}>
                      <td>
                        {paso?.imagen ? (
                          <img
                            src={paso.imagen}
                            alt={paso.placa_normalizada || 'Evidencia'}
                            className="thumb-img clickable-thumb"
                            onClick={() => setPasoSeleccionado(paso)}
                          />
                        ) : (
                          <span className="thumb-placeholder">
                            <ImageOff size={14} />
                          </span>
                        )}
                      </td>
                      <td>
                        <span className="alert-type-tag">{alerta.tipo}</span>
                      </td>
                      <td>
                        <strong className="mono-plate">
                          {paso?.placa_normalizada || paso?.placa_leida || '—'}
                        </strong>
                      </td>
                      <td>{etiquetaCategoria(paso?.categoria_detectada)}</td>
                      <td>{paso?.caseta_nombre || '—'}</td>
                      <td>{paso ? formatBs(paso.monto) : '—'}</td>
                      <td>
                        <EstadoBadge estado={paso?.estado} />
                      </td>
                      <td>
                        <EstadoBadge
                          estado={alerta.atendida ? 'atendida' : 'pendiente'}
                        />
                      </td>
                      <td className="mono text-sm">
                        {formatFechaHora(alerta.created_at)}
                      </td>
                      <td className="text-right">
                        <div className="row-actions">
                          {paso && (
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              onClick={() => setPasoSeleccionado(paso)}
                            >
                              <Eye size={15} />
                              Paso
                            </button>
                          )}
                          {esAdmin && !alerta.atendida && (
                            <button
                              type="button"
                              className="btn btn-primary btn-sm"
                              disabled={atendiendoId === alerta.id}
                              onClick={() => handleAtender(alerta.id)}
                            >
                              <Check size={15} />
                              {atendiendoId === alerta.id
                                ? 'Guardando...'
                                : 'Atender'}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        <Paginacion
          pagina={pagina}
          total={datos.count}
          tamanioPagina={TAMANIO_PAGINA}
          onCambiarPagina={(nueva) => {
            setCargando(true)
            setPagina(nueva)
          }}
        />
      </div>

      <PasoDetalleModal
        paso={pasoSeleccionado}
        onCerrar={() => setPasoSeleccionado(null)}
      />
    </div>
  )
}
