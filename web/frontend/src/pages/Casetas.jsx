import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Pencil, Plus, Trash2 } from 'lucide-react'
import api from '../api'
import Modal from '../components/Modal'
import { useToast } from '../components/toastContext'
import { extraerErrorApi } from '../utils/format'

const FORM_INICIAL = {
  nombre: '',
  ubicacion: '',
}

export default function Casetas() {
  const { mostrarToast } = useToast()

  const [casetas, setCasetas] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')

  const [modalAbierto, setModalAbierto] = useState(false)
  const [editando, setEditando] = useState(null)
  const [form, setForm] = useState(FORM_INICIAL)
  const [errorForm, setErrorForm] = useState('')
  const [guardando, setGuardando] = useState(false)

  const [eliminando, setEliminando] = useState(null)
  const [procesandoEliminar, setProcesandoEliminar] = useState(false)

  const cargarCasetas = useCallback(async () => {
    const res = await api.get('casetas/')
    setCasetas(Array.isArray(res.data) ? res.data : [])
    setError('')
  }, [])

  useEffect(() => {
    let activo = true
    ;(async () => {
      try {
        await cargarCasetas()
      } catch (err) {
        if (activo) {
          setError(extraerErrorApi(err, 'No se pudieron cargar las casetas.'))
        }
      } finally {
        if (activo) setCargando(false)
      }
    })()
    return () => {
      activo = false
    }
  }, [cargarCasetas])

  const abrirCrear = () => {
    setEditando(null)
    setForm(FORM_INICIAL)
    setErrorForm('')
    setModalAbierto(true)
  }

  const abrirEditar = (c) => {
    setEditando(c)
    setForm({
      nombre: c.nombre || '',
      ubicacion: c.ubicacion || '',
    })
    setErrorForm('')
    setModalAbierto(true)
  }

  const handleGuardar = async (e) => {
    e.preventDefault()
    if (!form.nombre.trim()) {
      setErrorForm('El nombre de la caseta es obligatorio.')
      return
    }
    if (!form.ubicacion.trim()) {
      setErrorForm('La ubicación es obligatoria.')
      return
    }

    setErrorForm('')
    setGuardando(true)
    const payload = {
      nombre: form.nombre.trim(),
      ubicacion: form.ubicacion.trim(),
    }

    try {
      if (editando) {
        await api.patch(`casetas/${editando.id}/`, payload)
        mostrarToast({
          tipo: 'success',
          titulo: 'Caseta actualizada',
          mensaje: `${payload.nombre} guardada correctamente.`,
        })
      } else {
        await api.post('casetas/', payload)
        mostrarToast({
          tipo: 'success',
          titulo: 'Caseta creada',
          mensaje: `${payload.nombre} agregada al sistema.`,
        })
      }
      setModalAbierto(false)
      await cargarCasetas()
    } catch (err) {
      setErrorForm(extraerErrorApi(err, 'No se pudo guardar la caseta.'))
    } finally {
      setGuardando(false)
    }
  }

  const handleEliminar = async () => {
    if (!eliminando) return
    setProcesandoEliminar(true)
    try {
      await api.delete(`casetas/${eliminando.id}/`)
      mostrarToast({
        tipo: 'success',
        titulo: 'Caseta eliminada',
        mensaje: `Se eliminó ${eliminando.nombre}.`,
      })
      setEliminando(null)
      await cargarCasetas()
    } catch (err) {
      mostrarToast({
        tipo: 'error',
        titulo: 'Error al eliminar',
        mensaje: extraerErrorApi(err, 'No se pudo eliminar la caseta.'),
      })
    } finally {
      setProcesandoEliminar(false)
    }
  }

  return (
    <div className="page-stack">
      <div className="toolbar-card">
        <div className="muted text-sm">
          Puntos de control y casetas de peaje registradas
        </div>
        <button type="button" className="btn btn-primary" onClick={abrirCrear}>
          <Plus size={16} />
          Nueva caseta
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
                <th>Nombre</th>
                <th>Ubicación</th>
                <th className="text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {cargando ? (
                <tr>
                  <td colSpan={4} className="table-empty">
                    Cargando casetas...
                  </td>
                </tr>
              ) : casetas.length === 0 ? (
                <tr>
                  <td colSpan={4} className="table-empty">
                    No hay casetas registradas.
                  </td>
                </tr>
              ) : (
                casetas.map((c) => (
                  <tr key={c.id}>
                    <td className="mono">#{c.id}</td>
                    <td>
                      <strong>{c.nombre}</strong>
                    </td>
                    <td>{c.ubicacion}</td>
                    <td className="text-right">
                      <div className="row-actions">
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => abrirEditar(c)}
                        >
                          <Pencil size={15} />
                          Editar
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger-ghost btn-sm"
                          onClick={() => setEliminando(c)}
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
        titulo={editando ? 'Editar caseta' : 'Nueva caseta'}
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
              form="caseta-form"
              className="btn btn-primary"
              disabled={guardando}
            >
              {guardando ? 'Guardando...' : 'Guardar'}
            </button>
          </>
        }
      >
        <form id="caseta-form" className="form-stack" onSubmit={handleGuardar}>
          {errorForm && (
            <div className="alert-banner alert-danger" role="alert">
              <AlertTriangle size={16} />
              <span>{errorForm}</span>
            </div>
          )}

          <div className="field">
            <label htmlFor="cas-nombre">Nombre</label>
            <input
              id="cas-nombre"
              type="text"
              placeholder="Ej. Caseta Autopista Norte - Carril 1"
              value={form.nombre}
              onChange={(e) =>
                setForm((p) => ({ ...p, nombre: e.target.value }))
              }
              required
            />
          </div>

          <div className="field">
            <label htmlFor="cas-ubicacion">Ubicación</label>
            <input
              id="cas-ubicacion"
              type="text"
              placeholder="Ej. Km 12 Carretera La Paz - El Alto"
              value={form.ubicacion}
              onChange={(e) =>
                setForm((p) => ({ ...p, ubicacion: e.target.value }))
              }
              required
            />
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
          ¿Estás seguro de eliminar la caseta{' '}
          <strong>{eliminando?.nombre}</strong>?
        </p>
      </Modal>
    </div>
  )
}
