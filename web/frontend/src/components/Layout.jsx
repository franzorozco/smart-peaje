import { useEffect, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  Bot,
  Car,
  CircleDot,
  LayoutDashboard,
  ListChecks,
  LogOut,
  MapPin,
  Menu,
  Receipt,
  ScanLine,
  Shapes,
  ShieldCheck,
  UserCheck,
  Users,
  X,
} from 'lucide-react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/authContext'
import { escuchar, realtimeConfigurado } from '../realtime'
import EstadoBadge from './EstadoBadge'

const ENLACES_PRINCIPALES = [
  { to: '/', label: 'Panel', icon: LayoutDashboard, end: true },
  { to: '/pasos', label: 'Pasos', icon: ListChecks },
  { to: '/alertas', label: 'Alertas', icon: AlertTriangle },
  { to: '/vehiculos', label: 'Vehículos', icon: Car },
  { to: '/chat', label: 'Asistente IA', icon: Bot },
  { to: '/estado', label: 'Estado', icon: Activity },
]

const ENLACES_PRUEBAS_IA = [
  { to: '/pruebas/m1', label: 'M1 · Placas OCR', icon: ScanLine },
  { to: '/pruebas/m2', label: 'M2 · Vehículos', icon: Shapes },
  { to: '/pruebas/m3', label: 'M3 · Ejes/Llantas', icon: CircleDot },
  { to: '/pruebas/m4', label: 'M4 · Pasajeros', icon: UserCheck },
]

const ENLACES_ADMIN = [
  { to: '/tarifas', label: 'Tarifas', icon: Receipt },
  { to: '/casetas', label: 'Casetas', icon: MapPin },
  { to: '/usuarios', label: 'Usuarios', icon: Users },
]

const TITULOS_RUTA = {
  '/': 'Panel de monitoreo',
  '/pasos': 'Historial de pasos',
  '/alertas': 'Alertas operativas',
  '/vehiculos': 'Parque vehicular',
  '/chat': 'Asistente inteligente',
  '/estado': 'Estado de servicios',
  '/pruebas/m1': 'Prueba M1 · Placas y OCR',
  '/pruebas/m2': 'Prueba M2 · Segmentación vehicular',
  '/pruebas/m3': 'Prueba M3 · Ejes y llantas',
  '/pruebas/m4': 'Prueba M4 · Pasajeros',
  '/tarifas': 'Tarifas de peaje',
  '/casetas': 'Casetas de cobro',
  '/usuarios': 'Lista blanca de usuarios',
}

function infoEstadoConexion(estado) {
  switch (estado) {
    case 'connected':
      return { clase: 'dot-green', texto: 'Tiempo real conectado' }
    case 'connecting':
    case 'initialized':
      return { clase: 'dot-amber', texto: 'Conectando...' }
    case 'no configurado':
      return { clase: 'dot-gray', texto: 'Pusher no configurado' }
    default:
      return { clase: 'dot-red', texto: `Desconectado (${estado || 'offline'})` }
  }
}

export default function Layout() {
  const { usuario, rol, esAdmin, cerrarSesion } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [menuAbierto, setMenuAbierto] = useState(false)
  const [estadoConexion, setEstadoConexion] = useState(() =>
    realtimeConfigurado() ? 'connecting' : 'no configurado'
  )

  useEffect(() => {
    const desuscribir = escuchar({
      onEstadoConexion: (estado) => setEstadoConexion(estado),
    })
    return desuscribir
  }, [])

  const tituloPagina = TITULOS_RUTA[location.pathname] || 'Smart Peaje'
  const infoConn = infoEstadoConexion(estadoConexion)

  const handleSalir = () => {
    cerrarSesion()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell">
      {menuAbierto && (
        <div
          className="sidebar-backdrop"
          onClick={() => setMenuAbierto(false)}
          aria-hidden="true"
        />
      )}

      <aside className={`sidebar ${menuAbierto ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <div className="brand-logo">
            <ShieldCheck size={20} />
          </div>
          <div className="brand-text">
            <strong>Smart Peaje</strong>
            <span>Control vehicular IA</span>
          </div>
          <button
            type="button"
            className="btn-icon sidebar-close-btn"
            onClick={() => setMenuAbierto(false)}
            aria-label="Cerrar menú"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="Navegación principal">
          <div className="nav-section-label">Operación</div>
          {ENLACES_PRINCIPALES.map((item) => {
            const Icono = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => setMenuAbierto(false)}
                className={({ isActive }) =>
                  `nav-link ${isActive ? 'active' : ''}`
                }
              >
                <Icono size={18} />
                <span>{item.label}</span>
              </NavLink>
            )
          })}

          <div className="nav-section-label">Pruebas IA</div>
          {ENLACES_PRUEBAS_IA.map((item) => {
            const Icono = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setMenuAbierto(false)}
                className={({ isActive }) =>
                  `nav-link ${isActive ? 'active' : ''}`
                }
              >
                <Icono size={18} />
                <span>{item.label}</span>
              </NavLink>
            )
          })}

          {esAdmin && (
            <>
              <div className="nav-section-label">Administración</div>
              {ENLACES_ADMIN.map((item) => {
                const Icono = item.icon
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    onClick={() => setMenuAbierto(false)}
                    className={({ isActive }) =>
                      `nav-link ${isActive ? 'active' : ''}`
                    }
                  >
                    <Icono size={18} />
                    <span>{item.label}</span>
                  </NavLink>
                )
              })}
            </>
          )}
        </nav>

        <div className="sidebar-footer">
          <div className="conn-pill" title={`Estado Pusher: ${estadoConexion}`}>
            <span className={`conn-dot ${infoConn.clase}`} />
            <span>{infoConn.texto}</span>
          </div>
        </div>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="btn-icon menu-toggle-btn"
              onClick={() => setMenuAbierto(true)}
              aria-label="Abrir menú"
            >
              <Menu size={20} />
            </button>
            <h1 className="topbar-title">{tituloPagina}</h1>
          </div>

          <div className="topbar-right">
            <div className="conn-chip" title={`Tiempo real: ${estadoConexion}`}>
              <span className={`conn-dot ${infoConn.clase}`} />
              <span className="conn-chip-label">{infoConn.texto}</span>
            </div>

            <div className="user-chip">
              <div className="user-meta">
                <span className="user-name">
                  {usuario?.nombre || usuario?.email || 'Usuario'}
                </span>
                <span className="user-email">{usuario?.email}</span>
              </div>
              <EstadoBadge estado={rol || usuario?.rol} />
            </div>

            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleSalir}
              title="Cerrar sesión"
            >
              <LogOut size={16} />
              <span className="hide-sm">Salir</span>
            </button>
          </div>
        </header>

        <main className="page-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
