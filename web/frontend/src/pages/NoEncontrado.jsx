import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function NoEncontrado() {
  return (
    <div className="full-center">
      <div className="panel-card empty-state" style={{ maxWidth: 440 }}>
        <Compass size={42} className="text-green" />
        <h1>404 · Página no encontrada</h1>
        <p className="muted">
          La ruta solicitada no existe o fue movida dentro del panel de Smart
          Peaje.
        </p>
        <Link to="/" className="btn btn-primary">
          Volver al panel
        </Link>
      </div>
    </div>
  )
}
