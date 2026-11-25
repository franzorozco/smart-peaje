import { useState } from 'react'
import { GoogleLogin } from '@react-oauth/google'
import { AlertTriangle, ShieldCheck } from 'lucide-react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/authContext'
import { extraerErrorApi } from '../utils/format'

export default function Login() {
  const { usuario, cargando, iniciarSesionGoogle } = useAuth()
  const [error, setError] = useState('')
  const [autenticando, setAutenticando] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID?.trim() || ''
  const googleConfigurado =
    Boolean(clientId) &&
    clientId !== 'TU_CLIENT_ID_WEB' &&
    clientId !== 'placeholder-client-id'

  if (cargando) {
    return (
      <div className="full-center">
        <div className="spinner" />
        <p className="muted">Cargando sesión...</p>
      </div>
    )
  }

  if (usuario) {
    const destino = location.state?.from?.pathname || '/'
    return <Navigate to={destino} replace />
  }

  const handleSuccess = async (credentialResponse) => {
    if (!credentialResponse?.credential) {
      setError('No se recibió una credencial válida de Google.')
      return
    }
    setError('')
    setAutenticando(true)
    try {
      await iniciarSesionGoogle(credentialResponse.credential)
      const destino = location.state?.from?.pathname || '/'
      navigate(destino, { replace: true })
    } catch (err) {
      const status = err?.response?.status
      if (status === 403) {
        setError('Acceso denegado: tu cuenta de Google no está autorizada')
      } else if (status === 401) {
        setError(err?.response?.data?.error || 'Token de Google inválido')
      } else {
        setError(extraerErrorApi(err, 'No se pudo iniciar sesión con Google.'))
      }
    } finally {
      setAutenticando(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <div className="brand-logo brand-logo-lg">
            <ShieldCheck size={28} />
          </div>
          <h1>Smart Peaje</h1>
          <p className="muted">
            Panel de monitoreo, gestión tarifaria e inspección asistida por IA
          </p>
        </div>

        {!googleConfigurado && (
          <div className="alert-banner alert-warning">
            <AlertTriangle size={18} />
            <div>
              <strong>Google OAuth no configurado.</strong>
              <p>
                Define <code>VITE_GOOGLE_CLIENT_ID</code> en tu archivo{' '}
                <code>.env</code> para habilitar el acceso institucional.
              </p>
            </div>
          </div>
        )}

        {error && (
          <div className="alert-banner alert-danger" role="alert">
            <AlertTriangle size={18} />
            <span>{error}</span>
          </div>
        )}

        <div className="login-action-box">
          {autenticando ? (
            <div className="login-loading">
              <div className="spinner spinner-sm" />
              <span>Verificando cuenta autorizada...</span>
            </div>
          ) : (
            <div className="google-btn-wrap">
              <GoogleLogin
                onSuccess={handleSuccess}
                onError={() =>
                  setError('No se pudo completar la autenticación con Google.')
                }
                theme="filled_black"
                size="large"
                text="signin_with"
                shape="rectangular"
                locale="es"
              />
            </div>
          )}
        </div>

        <p className="login-footnote">
          El acceso está restringido a cuentas registradas en la lista blanca
          del sistema (Administradores y Operadores).
        </p>
      </div>
    </div>
  )
}
