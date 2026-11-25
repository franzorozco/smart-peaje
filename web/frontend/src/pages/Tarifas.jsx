import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Pencil, Plus, Trash2 } from 'lucide-react'
import api from '../api'
import Modal from '../components/Modal'
import { useToast } from '../components/toastContext'
import {
  CATEGORIAS,
  etiquetaCategoria,
  extraerErrorApi,
  formatBs,
} from '../utils/format'

const FORM_INICIAL = {
  categoria: 'auto',
  ejes: 2,
  monto: '10.00',
}

export default function Tarifas() {
  const { mostrarToast } = useToast()

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

  const cargarTarifas = useCallback(async () => {
    const res = await api.get('tarifas/')
    setTarifas(Array.isArray(res.data) ? res.data : [])
    setError('')
  }, [])

  useEffect(() => {
    let activo = true
    ;(async () => {
      try {
        await cargarTarifas()
      } catch (err) {
        if (activo) {
          setError(extraerErrorApi(err, 'No se pudieron cargar las tarifas.'))
        }
      } finally {
        if (activo) setCargando(false)
      }
    })()
    return () => {
      activo = false
    }
  }, [cargarTarifas])

  const abrirCrear = () => {
    setEditando(null)
    setForm(FORM_INICIAL)
    setErrorForm('')
    setModalAbierto(true)
  }

  const abrirEditar = (t) => {
    setEditando(t)
    setForm({
      categoria: t.categoria || 'auto',
      ejes: t.ejes ?? 2,
      monto: t.monto ?? '0.00',
    })
    setErrorForm('')
    setModalAbierto(true)
  }

  const handleGuardar = async (e) => {
    e.preventDefault()
    const ejesNum = Number(form.ejes)
    if (!Number.isInteger(ejesNum) || ejesNum < 2 || ejesNum > 7) {
      setErrorForm('La cantidad de ejes debe estar entre 2 y 7.')
      return
    }
    const montoNum = Number(form.monto)
    if (!Number.isFinite(montoNum) || montoNum < 0) {
      setErrorForm('El monto debe ser mayor o igual a 0.')
      return
    }

    setErrorForm('')
    setGuardando(true)
    const payload = {
      categoria: form.categoria,
      ejes: ejesNum,
      monto: montoNum.toFixed(2),
    }

    try {
      if (editando) {
        await api.patch(`tarifas/${editando.id}/`, payload)
        mostrarToast({
          tipo: 'success',
          titulo: 'Tarifa actualizada',
          mensaje: `${etiquetaCategoria(payload.categoria)} (${payload.ejes} ejes): ${formatBs(payload.monto)}`,
        })
      } else {
        await api.post('tarifas/', payload)
        mostrarToast({
          tipo: 'success',
          titulo: 'Tarifa creada',
          mensaje: `${etiquetaCategoria(payload.categoria)} (${payload.ejes} ejes): ${formatBs(payload.monto)}`,
        })
      }
      setModalAbierto(false)
      await cargarTarifas()
    } catch (err) {
      setErrorForm(extraerErrorApi(err, 'No se pudo guardar la tarifa.'))
    } finally {
      setGuardando(false)
    }
  }

  const handleEliminar = async () => {
    if (!eliminando) return
    setProcesandoEliminar(true)
    try {
      await api.delete(`tarifas/${eliminando.id}/`)
      mostrarToast({
        tipo: 'success',
        titulo: 'Tarifa eliminada',
        mensaje: `Se eliminó la tarifa de ${etiquetaCategoria(eliminando.categoria)}.`,
      })
      setEliminando(null)
      await cargarTarifas()
    } catch (err) {
      mostrarToast({
        tipo: 'error',
        titulo: 'Error al eliminar',
        mensaje: extraerErrorApi(err, 'No se pudo eliminar la tarifa.'),
      })
    } finally {
      setProcesandoEliminar(false)
    }
  }

  return (
    <div className="page-stack">
      <div className="toolbar-card">
        <div className="muted text-sm">
          Configuración de tarifas vigentes por categoría y número de ejes
        </div>
        <button type="button" className="btn btn-primary" onClick={abrirCrear}>
          <Plus size={16} />
          Nueva tarifa
        </button>
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
                <th>ID</th>
                <th>Categoría</th>
                <th>Ejes</th>
                <th>Monto</th>
                <th className="text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {cargando ? (
                <tr>
                  <td colSpan={5} className="table-empty">
                    Cargando tarifas...
                  </td>
                </tr>
              ) : tarifas.length === 0 ? (
                <tr>
                  <td colSpan={5} className="table-empty">
                    No hay tarifas configuradas.
                  </td>
                </tr>
              ) : (
                tarifas.map((t) => (
                  <tr key={t.id}>
                    <td className="mono">#{t.id}</td>
                    <td>
                      <strong>{etiquetaCategoria(t.categoria)}</strong>
                    </td>
                    <td>{t.ejes} ejes</td>
                    <td>
                      <strong className="text-green">{formatBs(t.monto)}</strong>
                    </td>
                    <td className="text-right">
                      <div className="row-actions">
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => abrirEditar(t)}
                        >
                          <Pencil size={15} />
                          Editar
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger-ghost btn-sm"
                          onClick={() => setEliminando(t)}
                        >
                          <Trash2 size={15} />
                          Eliminar
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Modal
        abierto={modalAbierto}
        onCerrar={() => setModalAbierto(false)}
        titulo={editando ? 'Editar tarifa' : 'Nueva tarifa'}
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
              form="tarifa-form"
              className="btn btn-primary"
              disabled={guardando}
            >
              {guardando ? 'Guardando...' : 'Guardar'}
            </button>
          </>
        }
      >
        <form id="tarifa-form" className="form-stack" onSubmit={handleGuardar}>
          {errorForm && (
            <div className="alert-banner alert-danger" role="alert">
              <AlertTriangle size={16} />
              <span>{errorForm}</span>
            </div>
          )}

          <div className="field">
            <label htmlFor="tar-cat">Categoría</label>
            <select
              id="tar-cat"
              value={form.categoria}
              onChange={(e) =>
                setForm((p) => ({ ...p, categoria: e.target.value }))
              }
            >
              {CATEGORIAS.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          <div className="form-grid-2">
            <div className="field">
              <label htmlFor="tar-ejes">Ejes (2 a 7)</label>
              <input
                id="tar-ejes"
                type="number"
                min="2"
                max="7"
                step="1"
                value={form.ejes}
                onChange={(e) =>
                  setForm((p) => ({ ...p, ejes: e.target.value }))
                }
                required
              />
            </div>

            <div className="field">
              <label htmlFor="tar-monto">Monto (Bs)</label>
              <input
                id="tar-monto"
                type="number"
                min="0"
                step="0.01"
                value={form.monto}
                onChange={(e) =>
                  setForm((p) => ({ ...p, monto: e.target.value }))
                }
                required
              />
            </div>
          </div>
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
          ¿Eliminar la tarifa para{' '}
          <strong>{etiquetaCategoria(eliminando?.categoria)}</strong> (
          {eliminando?.ejes} ejes) de{' '}
          <strong>{formatBs(eliminando?.monto)}</strong>?
        </p>
      </Modal>
    </div>
  )
}
