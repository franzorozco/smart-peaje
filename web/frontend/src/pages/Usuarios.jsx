import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Pencil, Plus, Trash2 } from 'lucide-react'
import api from '../api'
import { useAuth } from '../auth/authContext'
import EstadoBadge from '../components/EstadoBadge'
import Modal from '../components/Modal'
import { useToast } from '../components/toastContext'
import { ROLES, extraerErrorApi, formatFechaHora } from '../utils/format'

const FORM_INICIAL = {
  email: '',
  nombre: '',
  rol: 'operador',
  activo: true,
}

export default function Usuarios() {
  const { usuario: usuarioActual } = useAuth()
  const { mostrarToast } = useToast()

  const [usuarios, setUsuarios] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')

  const [modalAbierto, setModalAbierto] = useState(false)
  const [editando, setEditando] = useState(null)
  const [form, setForm] = useState(FORM_INICIAL)
  const [errorForm, setErrorForm] = useState('')
  const [guardando, setGuardando] = useState(false)

  const [eliminando, setEliminando] = useState(null)
  const [procesandoEliminar, setProcesandoEliminar] = useState(false)

  const cargarUsuarios = useCallback(async () => {
    const res = await api.get('usuarios/')
    setUsuarios(Array.isArray(res.data) ? res.data : [])
    setError('')
  }, [])

  useEffect(() => {
    let activo = true
    ;(async () => {
      try {
        await cargarUsuarios()
      } catch (err) {
        if (activo) {
          setError(extraerErrorApi(err, 'No se pudo cargar la lista blanca de usuarios.'))
        }
      } finally {
        if (activo) setCargando(false)
      }
    })()
    return () => {
      activo = false
    }
  }, [cargarUsuarios])

  const abrirCrear = () => {
    setEditando(null)
    setForm(FORM_INICIAL)
    setErrorForm('')
    setModalAbierto(true)
  }

  const abrirEditar = (u) => {
    setEditando(u)
    setForm({
      email: u.email || '',
      nombre: u.nombre || '',
      rol: u.rol || 'operador',
      activo: Boolean(u.activo),
    })
    setErrorForm('')
    setModalAbierto(true)
  }

  const handleGuardar = async (e) => {
    e.preventDefault()
    if (!form.email.trim()) {
      setErrorForm('El correo electrónico de Google es obligatorio.')
      return
    }
    if (!form.nombre.trim()) {
      setErrorForm('El nombre es obligatorio.')
      return
    }

    setErrorForm('')
    setGuardando(true)
    const payload = {
      email: form.email.trim().toLowerCase(),
      nombre: form.nombre.trim(),
      rol: form.rol,
      activo: Boolean(form.activo),
    }

    try {
      if (editando) {
        await api.patch(`usuarios/${editando.id}/`, payload)
        mostrarToast({
          tipo: 'success',
          titulo: 'Usuario actualizado',
          mensaje: `${payload.email} guardado correctamente.`,
        })
      } else {
        await api.post('usuarios/', payload)
        mostrarToast({
          tipo: 'success',
          titulo: 'Usuario autorizado',
          mensaje: `${payload.email} agregado a la lista blanca.`,
        })
      }
      setModalAbierto(false)
      await cargarUsuarios()
    } catch (err) {
      setErrorForm(extraerErrorApi(err, 'No se pudo guardar el usuario.'))
    } finally {
      setGuardando(false)
    }
  }

  const handleEliminar = async () => {
    if (!eliminando) return
    setProcesandoEliminar(true)
    try {
      await api.delete(`usuarios/${eliminando.id}/`)
      mostrarToast({
        tipo: 'success',
        titulo: 'Usuario eliminado',
        mensaje: `${eliminando.email} fue removido de la lista blanca.`,
      })
      setEliminando(null)
      await cargarUsuarios()
    } catch (err) {
      mostrarToast({
        tipo: 'error',
        titulo: 'Error al eliminar',
        mensaje: extraerErrorApi(err, 'No se pudo eliminar el usuario.'),
      })
    } finally {
      setProcesandoEliminar(false)
    }
  }

  return (
    <div className="page-stack">
      <div className="toolbar-card">
        <div className="muted text-sm">
          Lista blanca de cuentas Google autorizadas para acceder al sistema
        </div>
        <button type="button" className="btn btn-primary" onClick={abrirCrear}>
          <Plus size={16} />
          Autorizar usuario
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
                <th>Nombre</th>
                <th>Correo Google</th>
                <th>Rol</th>
                <th>Estado</th>
                <th>Último acceso</th>
                <th className="text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {cargando ? (
                <tr>
                  <td colSpan={6} className="table-empty">
                    Cargando usuarios...
                  </td>
                </tr>
              ) : usuarios.length === 0 ? (
                <tr>
                  <td colSpan={6} className="table-empty">
                    No hay usuarios registrados en la lista blanca.
                  </td>
                </tr>
              ) : (
                usuarios.map((u) => {
                  const esMismoUsuario = usuarioActual?.id === u.id
                  return (
                    <tr key={u.id}>
                      <td>
                        <strong>{u.nombre || '—'}</strong>
                        {esMismoUsuario && (
                          <span className="text-xs text-green" style={{ marginLeft: 8 }}>
                            (Tú)
                          </span>
                        )}
                      </td>
                      <td className="mono text-sm">{u.email}</td>
                      <td>
                        <EstadoBadge estado={u.rol} />
                      </td>
                      <td>
                        <EstadoBadge estado={Boolean(u.activo)} />
                      </td>
                      <td className="mono text-sm">
                        {u.last_login ? formatFechaHora(u.last_login) : 'Nunca'}
                      </td>
                      <td className="text-right">
                        <div className="row-actions">
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => abrirEditar(u)}
                          >
                            <Pencil size={15} />
                            Editar
                          </button>
                          <button
                            type="button"
                            className="btn btn-danger-ghost btn-sm"
                            disabled={esMismoUsuario}
                            title={
                              esMismoUsuario
                                ? 'No puedes eliminar tu propia cuenta activa'
                                : 'Eliminar usuario'
                            }
                            onClick={() => setEliminando(u)}
                          >
                            <Trash2 size={15} />
                            Eliminar
                          </button>
                        </div>
                      </td>
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
        titulo={editando ? 'Editar usuario autorizado' : 'Autorizar usuario'}
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
              form="usuario-form"
              className="btn btn-primary"
              disabled={guardando}
            >
              {guardando ? 'Guardando...' : 'Guardar'}
            </button>
          </>
        }
      >
        <form id="usuario-form" className="form-stack" onSubmit={handleGuardar}>
          {errorForm && (
            <div className="alert-banner alert-danger" role="alert">
              <AlertTriangle size={16} />
              <span>{errorForm}</span>
            </div>
          )}

          <div className="field">
            <label htmlFor="usr-email">Correo de Google</label>
            <input
              id="usr-email"
              type="email"
              placeholder="operador@gmail.com"
              value={form.email}
              onChange={(e) =>
                setForm((p) => ({ ...p, email: e.target.value }))
              }
              required
            />
          </div>

          <div className="field">
            <label htmlFor="usr-nombre">Nombre completo</label>
            <input
              id="usr-nombre"
              type="text"
              placeholder="Ej. Ana Pérez"
              value={form.nombre}
              onChange={(e) =>
                setForm((p) => ({ ...p, nombre: e.target.value }))
              }
              required
            />
          </div>

          <div className="field">
            <label htmlFor="usr-rol">Rol</label>
            <select
              id="usr-rol"
              value={form.rol}
              onChange={(e) =>
                setForm((p) => ({ ...p, rol: e.target.value }))
              }
            >
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={form.activo}
              onChange={(e) =>
                setForm((p) => ({ ...p, activo: e.target.checked }))
              }
            />
            <span>Cuenta habilitada para iniciar sesión</span>
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
          ¿Remover a <strong>{eliminando?.nombre || eliminando?.email}</strong> (
          <span className="mono">{eliminando?.email}</span>) de la lista blanca?
        </p>
      </Modal>
    </div>
  )
}
