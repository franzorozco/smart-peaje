import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  Pencil,
  Plus,
  Search,
  Trash2,
} from 'lucide-react'
import api from '../api'
import { useAuth } from '../auth/authContext'
import EstadoBadge from '../components/EstadoBadge'
import Modal from '../components/Modal'
import { useToast } from '../components/toastContext'
import {
  CATEGORIAS,
  esVehiculoPesado,
  etiquetaCategoria,
  extraerErrorApi,
  formatBs,
  normalizarPlaca,
  validarPlaca,
} from '../utils/format'

const FORM_INICIAL = {
  placa: '',
  propietario: '',
  categoria: 'auto',
  ejes: 2,
  saldo: '0.00',
  activo: true,
}

export default function Vehiculos() {
  const { esAdmin } = useAuth()
  const { mostrarToast } = useToast()

  const [busquedaInput, setBusquedaInput] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const [vehiculos, setVehiculos] = useState([])
  const [tarifas, setTarifas] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')

  const [modalAbierto, setModalAbierto] = useState(false)
  const [editando, setEditando] = useState(null)
  const [form, setForm] = useState(FORM_INICIAL)
  const [errorForm, setErrorForm] = useState('')
  const [guardando, setGuardando] = useState(false)

  const [eliminando, setEliminando] = useState(null)
  const [procesandoEliminar, setProcesandoEliminar] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => {
      setBusqueda(busquedaInput.trim())
    }, 300)
    return () => clearTimeout(timer)
  }, [busquedaInput])

  useEffect(() => {
    let activo = true
    ;(async () => {
      try {
        const res = await api.get('tarifas/')
        if (activo && Array.isArray(res.data)) {
          setTarifas(res.data)
        }
      } catch {
        // Silencioso si no se pueden listar tarifas
      }
    })()
    return () => {
      activo = false
    }
  }, [])

  const obtenerTarifaVehiculo = (categoria, ejes) => {
    const exacta = tarifas.find(
      (t) => t.categoria === categoria && Number(t.ejes) === Number(ejes)
    )
    if (exacta) return exacta.monto
    if (!esVehiculoPesado(categoria)) {
      const base = tarifas.find((t) => t.categoria === categoria)
      if (base) return base.monto
    }
    return null
  }

  const cargarVehiculos = useCallback(async () => {
    const params = busqueda ? { search: busqueda } : {}
    const res = await api.get('vehiculos/', { params })
    setVehiculos(Array.isArray(res.data) ? res.data : [])
    setError('')
  }, [busqueda])

  useEffect(() => {
    let activo = true
    ;(async () => {
      try {
        await cargarVehiculos()
      } catch (err) {
        if (activo) {
          setError(extraerErrorApi(err, 'No se pudo cargar la lista de vehículos.'))
        }
      } finally {
        if (activo) setCargando(false)
      }
    })()
    return () => {
      activo = false
    }
  }, [cargarVehiculos])

  const abrirCrear = () => {
    setEditando(null)
    setForm(FORM_INICIAL)
    setErrorForm('')
    setModalAbierto(true)
  }

  const abrirEditar = (v) => {
    setEditando(v)
    setForm({
      placa: v.placa || '',
      propietario: v.propietario || '',
      categoria: v.categoria || 'auto',
      ejes: v.ejes ?? 2,
      saldo: v.saldo ?? '0.00',
      activo: Boolean(v.activo),
    })
    setErrorForm('')
    setModalAbierto(true)
  }

  const handleGuardar = async (e) => {
    e.preventDefault()
    const placaNorm = normalizarPlaca(form.placa)
    if (!validarPlaca(placaNorm)) {
      setErrorForm('La placa debe tener 3 o 4 dígitos seguidos de 3 letras (ej. 1234ABC).')
      return
    }
    if (!form.propietario.trim()) {
      setErrorForm('El nombre del propietario es obligatorio.')
      return
    }
    const ejesNum = Number(form.ejes)
    if (!Number.isInteger(ejesNum) || ejesNum < 2 || ejesNum > 7) {
      setErrorForm('Los ejes deben ser un número entero entre 2 y 7.')
      return
    }
    const saldoNum = Number(form.saldo)
    if (!Number.isFinite(saldoNum) || saldoNum < 0) {
      setErrorForm('El saldo debe ser mayor o igual a 0.')
      return
    }

    setErrorForm('')
    setGuardando(true)
    const payload = {
      placa: placaNorm,
      propietario: form.propietario.trim(),
      categoria: form.categoria,
      ejes: ejesNum,
      saldo: saldoNum.toFixed(2),
      activo: Boolean(form.activo),
    }

    try {
      if (editando) {
        await api.patch(`vehiculos/${editando.id}/`, payload)
        mostrarToast({
          tipo: 'success',
          titulo: 'Vehículo actualizado',
          mensaje: `Placa ${placaNorm} guardada correctamente.`,
        })
      } else {
        await api.post('vehiculos/', payload)
        mostrarToast({
          tipo: 'success',
          titulo: 'Vehículo registrado',
          mensaje: `Placa ${placaNorm} agregada al padrón.`,
        })
      }
      setModalAbierto(false)
      await cargarVehiculos()
    } catch (err) {
      setErrorForm(extraerErrorApi(err, 'No se pudo guardar el vehículo.'))
    } finally {
      setGuardando(false)
    }
  }

  const handleEliminar = async () => {
    if (!eliminando) return
    setProcesandoEliminar(true)
    try {
      await api.delete(`vehiculos/${eliminando.id}/`)
      mostrarToast({
        tipo: 'success',
        titulo: 'Vehículo eliminado',
        mensaje: `Se eliminó la placa ${eliminando.placa}.`,
      })
      setEliminando(null)
      await cargarVehiculos()
    } catch (err) {
      mostrarToast({
        tipo: 'error',
        titulo: 'Error al eliminar',
        mensaje: extraerErrorApi(err, 'No se pudo eliminar el vehículo.'),
      })
    } finally {
      setProcesandoEliminar(false)
    }
  }

  return (
    <div className="page-stack">
      <div className="toolbar-card">
        <div className="input-with-icon toolbar-search">
          <Search size={16} />
          <input
            type="text"
            placeholder="Buscar por placa o propietario..."
            value={busquedaInput}
            onChange={(e) => setBusquedaInput(e.target.value)}
          />
        </div>

        {esAdmin ? (
          <button type="button" className="btn btn-primary" onClick={abrirCrear}>
            <Plus size={16} />
            Nuevo vehículo
          </button>
        ) : (
          <span className="muted text-sm">
            Modo solo lectura (operador)
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
                <th>Placa</th>
                <th>Propietario</th>
                <th>Categoría</th>
                <th>Ejes</th>
                <th>Tarifa/paso</th>
                <th>Saldo</th>
                <th>Estado</th>
                {esAdmin && <th className="text-right">Acciones</th>}
              </tr>
            </thead>
            <tbody>
              {cargando ? (
                <tr>
                  <td colSpan={esAdmin ? 8 : 7} className="table-empty">
                    Cargando vehículos...
                  </td>
                </tr>
              ) : vehiculos.length === 0 ? (
                <tr>
                  <td colSpan={esAdmin ? 8 : 7} className="table-empty">
                    No se encontraron vehículos registrados.
                  </td>
                </tr>
              ) : (
                vehiculos.map((v) => {
                  const tarifaPaso = obtenerTarifaVehiculo(v.categoria, v.ejes)
                  return (
                  <tr key={v.id}>
                    <td>
                      <strong className="mono-plate">{v.placa}</strong>
                    </td>
                    <td>{v.propietario}</td>
                    <td>{etiquetaCategoria(v.categoria)}</td>
                    <td>{v.ejes}</td>
                    <td className="text-green">
                      {tarifaPaso !== null ? formatBs(tarifaPaso) : '—'}
                    </td>
                    <td>
                      <span className={Number(v.saldo) <= 0 ? 'text-amber' : ''}>
                        {formatBs(v.saldo)}
                      </span>
                    </td>
                    <td>
                      <EstadoBadge estado={v.activo} />
                    </td>
                    {esAdmin && (
                      <td className="text-right">
                        <div className="row-actions">
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => abrirEditar(v)}
                          >
                            <Pencil size={15} />
                            Editar
                          </button>
                          <button
                            type="button"
                            className="btn btn-danger-ghost btn-sm"
                            onClick={() => setEliminando(v)}
                          >
                            <Trash2 size={15} />
                            Eliminar
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Modal
        abierto={modalAbierto}
        onCerrar={() => setModalAbierto(false)}
        titulo={editando ? `Editar vehículo ${editando.placa}` : 'Registrar vehículo'}
        pie={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setModalAbierto(false)}
              disabled={guardando}
            >
              Cancelar
            </button>
            <button
              type="submit"
              form="vehiculo-form"
              className="btn btn-primary"
              disabled={guardando}
            >
              {guardando ? 'Guardando...' : 'Guardar'}
            </button>
          </>
        }
      >
        <form id="vehiculo-form" className="form-stack" onSubmit={handleGuardar}>
          {errorForm && (
            <div className="alert-banner alert-danger" role="alert">
              <AlertTriangle size={16} />
              <span>{errorForm}</span>
            </div>
          )}

          <div className="form-grid-2">
            <div className="field">
              <label htmlFor="veh-placa">Placa</label>
              <input
                id="veh-placa"
                type="text"
                placeholder="1234ABC"
                value={form.placa}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    placa: e.target.value.toUpperCase(),
                  }))
                }
                required
              />
              <span className="field-hint">Formato: 3 o 4 dígitos y 3 letras</span>
            </div>

            <div className="field">
              <label htmlFor="veh-saldo">Saldo (Bs)</label>
              <input
                id="veh-saldo"
                type="number"
                min="0"
                step="0.01"
                value={form.saldo}
                onChange={(e) =>
                  setForm((p) => ({ ...p, saldo: e.target.value }))
                }
                required
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor="veh-propietario">Propietario</label>
            <input
              id="veh-propietario"
              type="text"
              placeholder="Nombre completo o razón social"
              value={form.propietario}
              onChange={(e) =>
                setForm((p) => ({ ...p, propietario: e.target.value }))
              }
              required
            />
          </div>

          <div className="form-grid-2">
            <div className="field">
              <label htmlFor="veh-categoria">Categoría (M2)</label>
              <select
                id="veh-categoria"
                value={form.categoria}
                onChange={(e) => {
                  const nuevaCat = e.target.value
                  setForm((p) => ({
                    ...p,
                    categoria: nuevaCat,
                    ejes: esVehiculoPesado(nuevaCat) ? p.ejes : 2,
                  }))
                }}
              >
                {CATEGORIAS.map((cat) => (
                  <option key={cat.value} value={cat.value}>
                    {cat.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="veh-ejes">
                Ejes (M3){esVehiculoPesado(form.categoria) ? ' · 2 a 7' : ' · fijo 2'}
              </label>
              <input
                id="veh-ejes"
                type="number"
                min="2"
                max={esVehiculoPesado(form.categoria) ? '7' : '2'}
                step="1"
                value={form.ejes}
                onChange={(e) =>
                  setForm((p) => ({ ...p, ejes: e.target.value }))
                }
                required
              />
            </div>
          </div>

          {(() => {
            const montoEst = obtenerTarifaVehiculo(form.categoria, form.ejes)
            return (
              <div
                className="text-sm"
                style={{
                  padding: '0.65rem 0.85rem',
                  borderRadius: '8px',
                  background: 'rgba(34, 197, 94, 0.1)',
                  border: '1px solid rgba(34, 197, 94, 0.25)',
                }}
              >
                <strong>Tarifa por paso: </strong>
                {montoEst !== null ? (
                  <span className="text-green">
                    <strong>{formatBs(montoEst)}</strong>
                  </span>
                ) : (
                  <span className="text-amber">Sin tarifa configurada para esta combinación</span>
                )}
                <div className="text-xs muted" style={{ marginTop: '0.2rem' }}>
                  {esVehiculoPesado(form.categoria)
                    ? `Vehículo pesado: se cobra por categoría (${etiquetaCategoria(form.categoria)}) y ${form.ejes} ejes. Pasajeros: informativo (sin recargo).`
                    : `Vehículo liviano: tarifa fija por categoría (${etiquetaCategoria(form.categoria)}). Pasajeros: informativo (sin recargo).`}
                </div>
              </div>
            )
          })()}

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={form.activo}
              onChange={(e) =>
                setForm((p) => ({ ...p, activo: e.target.checked }))
              }
            />
            <span>Vehículo habilitado (activo)</span>
          </label>
        </form>
      </Modal>

      <Modal
        abierto={Boolean(eliminando)}
        onCerrar={() => setEliminando(null)}
        titulo="Confirmar eliminación"
        ancho="sm"
        pie={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setEliminando(null)}
              disabled={procesandoEliminar}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={handleEliminar}
              disabled={procesandoEliminar}
            >
              {procesandoEliminar ? 'Eliminando...' : 'Eliminar'}
            </button>
          </>
        }
      >
        <p>
          ¿Estás seguro de eliminar el vehículo{' '}
          <strong className="mono-plate">{eliminando?.placa}</strong> de{' '}
          <strong>{eliminando?.propietario}</strong>? Esta acción no se puede
          deshacer.
        </p>
      </Modal>
    </div>
  )
}
