import { ShieldAlert } from 'lucide-react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/authContext'

export default function ProtectedRoute({ adminOnly = false, children }) {
  const { usuario, esAdmin, cargando } = useAuth()
  const location = useLocation()

  if (cargando) {
    return (
      <div className="full-center">
        <div className="spinner" />
        <p className="muted">Verificando sesión...</p>
      </div>
    )
  }

  if (!usuario) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (adminOnly && !esAdmin) {
    return (
      <div className="panel-card empty-state" style={{ marginTop: '2rem' }}>
        <ShieldAlert size={40} className="text-amber" />
        <h2>Acceso restringido</h2>
        <p className="muted">
          Esta sección es exclusiva para usuarios con rol de administrador.
        </p>
        <Link to="/" className="btn btn-primary">
          Volver al panel
        </Link>
      </div>
    )
  }

  return children
}
