import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Camera, Eye, ImageOff, Loader2, Search, X } from 'lucide-react'
import api from '../api'
import EstadoBadge from '../components/EstadoBadge'
import Paginacion from '../components/Paginacion'
import PasoDetalleModal from '../components/PasoDetalleModal'
import {
  ESTADOS_PASO,
  etiquetaCategoria,
  extraerErrorApi,
  formatBs,
  formatFechaHora,
} from '../utils/format'

const TAMANIO_PAGINA = 25

export default function Pasos() {
  const [casetas, setCasetas] = useState([])
  const [filtros, setFiltros] = useState({
    placa: '',
    estado: '',
    caseta: '',
    fecha: '',
  })
  const [placaInput, setPlacaInput] = useState('')
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState({ count: 0, results: [] })
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [pasoActivo, setPasoActivo] = useState(null)
  const [procesandoCaseta, setProcesandoCaseta] = useState(false)
  const [recargarSeq, setRecargarSeq] = useState(0)
  const fileInputRef = useRef(null)

  useEffect(() => {
    let activo = true
    ;(async () => {
      try {
        const res = await api.get('casetas/')
        if (activo && Array.isArray(res.data)) {
          setCasetas(res.data)
        }
      } catch {
        // Silencioso si no hay casetas disponibles
      }
    })()
    return () => {
      activo = false
    }
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => {
      setFiltros((prev) =>
        prev.placa === placaInput ? prev : { ...prev, placa: placaInput }
      )
      setPagina(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [placaInput])

  useEffect(() => {
    let activo = true
    ;(async () => {
      try {
        const params = {
          page: pagina,
          page_size: TAMANIO_PAGINA,
        }
        if (filtros.placa.trim()) params.placa = filtros.placa.trim()
        if (filtros.estado) params.estado = filtros.estado
        if (filtros.caseta) params.caseta = filtros.caseta
        if (filtros.fecha) params.fecha = filtros.fecha

        const res = await api.get('pasos/', { params })
        if (!activo) return
        setDatos({
          count: res.data?.count ?? 0,
          results: res.data?.results || [],
        })
        setError('')
      } catch (err) {
        if (activo) {
          setError(extraerErrorApi(err, 'No se pudo cargar el historial de pasos.'))
        }
      } finally {
        if (activo) setCargando(false)
      }
    })()
    return () => {
      activo = false
    }
  }, [filtros, pagina, recargarSeq])

  const generarUuid = () => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0
      const v = c === 'x' ? r : (r & 0x3) | 0x8
      return v.toString(16)
    })
  }

  const probarCaseta = async (evento) => {
    const archivo = evento.target.files?.[0]
    evento.target.value = ''
    if (!archivo) return

    const casetaId = filtros.caseta || casetas[0]?.id
    if (!casetaId) {
      setError('No hay casetas activas para registrar el paso.')
      return
    }

    setError('')
    setProcesandoCaseta(true)
    try {
      const formData = new FormData()
      formData.append('file', archivo)
      formData.append('captura_id', generarUuid())
      formData.append('caseta_id', String(casetaId))

      const res = await api.post('pasos/frame', formData)
      setRecargarSeq((n) => n + 1)

      const pasoCreado = res.data?.paso || (res.data?.id ? res.data : null)
      if (pasoCreado) {
        setPasoActivo(pasoCreado)
      }
    } catch (err) {
      setError(
        extraerErrorApi(
          err,
          'No se pudo procesar la captura en Modo Caseta.'
        )
      )
    } finally {
      setProcesandoCaseta(false)
    }
  }

  const actualizarFiltro = (campo, valor) => {
    setCargando(true)
    setFiltros((prev) => ({ ...prev, [campo]: valor }))
    setPagina(1)
  }

  const limpiarFiltros = () => {
    setCargando(true)
    setPlacaInput('')
    setFiltros({ placa: '', estado: '', caseta: '', fecha: '' })
    setPagina(1)
  }

  const hayFiltros = Boolean(
    placaInput || filtros.estado || filtros.caseta || filtros.fecha
  )

  return (
    <div className="page-stack">
      <div className="panel-card">
        <div className="filters-grid">
          <div className="field">
            <label htmlFor="filtro-placa">Placa</label>
            <div className="input-with-icon">
              <Search size={16} />
              <input
                id="filtro-placa"
                type="text"
                placeholder="Buscar placa (ej. 1234ABC)"
                value={placaInput}
                onChange={(e) => setPlacaInput(e.target.value.toUpperCase())}
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor="filtro-estado">Estado</label>
            <select
              id="filtro-estado"
              value={filtros.estado}
              onChange={(e) => actualizarFiltro('estado', e.target.value)}
            >
              <option value="">Todos los estados</option>
              {ESTADOS_PASO.map((est) => (
                <option key={est.value} value={est.value}>
                  {est.label}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="filtro-caseta">Caseta</label>
            <select
              id="filtro-caseta"
              value={filtros.caseta}
              onChange={(e) => actualizarFiltro('caseta', e.target.value)}
            >
              <option value="">Todas las casetas</option>
              {casetas.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nombre}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="filtro-fecha">Fecha</label>
            <input
              id="filtro-fecha"
              type="date"
              value={filtros.fecha}
              onChange={(e) => actualizarFiltro('fecha', e.target.value)}
            />
          </div>

          {hayFiltros && (
            <div className="field field-end">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={limpiarFiltros}
              >
                <X size={16} />
                Limpiar
              </button>
            </div>
          )}

          <div className="field field-end">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*,video/mp4,video/quicktime"
              style={{ display: 'none' }}
              onChange={probarCaseta}
            />
            <button
              type="button"
              className="btn btn-primary"
              disabled={procesandoCaseta || casetas.length === 0}
              onClick={() => fileInputRef.current?.click()}
            >
              {procesandoCaseta ? (
                <>
                  <Loader2 size={16} className="spin" />
                  Analizando...
                </>
              ) : (
                <>
                  <Camera size={16} />
                  Probar caseta
                </>
              )}
            </button>
          </div>
        </div>
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
                <th>Placa</th>
                <th>Categoría</th>
                <th>Ejes</th>
                <th>Pasajeros</th>
                <th>Caseta</th>
                <th>Monto</th>
                <th>Estado</th>
                <th>Fecha y hora</th>
                <th className="text-right">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {cargando ? (
                <tr>
                  <td colSpan={10} className="table-empty">
                    Cargando pasos...
                  </td>
                </tr>
              ) : datos.results.length === 0 ? (
                <tr>
                  <td colSpan={10} className="table-empty">
                    No se encontraron pasos con los filtros seleccionados.
                  </td>
                </tr>
              ) : (
                datos.results.map((p) => (
                  <tr
                    key={p.id}
                    className="clickable-row"
                    onClick={() => setPasoActivo(p)}
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
                      <div className="plate-cell">
                        <strong className="mono-plate">
                          {p.placa_normalizada || p.placa_leida || '—'}
                        </strong>
                        {p.placa_leida &&
                          p.placa_normalizada &&
                          p.placa_leida !== p.placa_normalizada && (
                            <span className="text-xs muted">
                              OCR: {p.placa_leida}
                            </span>
                          )}
                      </div>
                    </td>
                    <td>{etiquetaCategoria(p.categoria_detectada)}</td>
                    <td>{p.ejes_detectados ?? '—'}</td>
                    <td>
                      {p.pasajeros !== null && p.pasajeros !== undefined
                        ? p.pasajeros
                        : 'N/D'}
                    </td>
                    <td>{p.caseta_nombre || '—'}</td>
                    <td>{formatBs(p.monto)}</td>
                    <td>
                      <EstadoBadge estado={p.estado} />
                    </td>
                    <td className="mono text-sm">
                      {formatFechaHora(p.created_at)}
                    </td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={(e) => {
                          e.stopPropagation()
                          setPasoActivo(p)
                        }}
                      >
                        <Eye size={15} />
                        Ver
                      </button>
                    </td>
                  </tr>
                ))
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
        paso={pasoActivo}
        onCerrar={() => setPasoActivo(null)}
      />
    </div>
  )
}
