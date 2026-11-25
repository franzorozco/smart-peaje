import { useCallback, useEffect, useMemo, useState } from 'react'
import api, {
  clearTokens,
  getRefreshToken,
  loginGoogle,
  refreshSession,
  setOnAuthFailure,
} from '../api'
import { AuthContext } from './authContext'

export function AuthProvider({ children }) {
  const [usuario, setUsuario] = useState(null)
  const [rol, setRol] = useState(null)
  const [cargando, setCargando] = useState(() => Boolean(getRefreshToken()))

  const cerrarSesion = useCallback(() => {
    clearTokens()
    setUsuario(null)
    setRol(null)
  }, [])

  useEffect(() => {
    setOnAuthFailure(() => {
      setUsuario(null)
      setRol(null)
    })
    return () => {
      setOnAuthFailure(null)
    }
  }, [])

  useEffect(() => {
    const tieneRefresh = Boolean(getRefreshToken())
    if (!tieneRefresh) {
      return undefined
    }

    let activo = true
    ;(async () => {
      try {
        await refreshSession()
        const res = await api.get('auth/me')
        if (!activo) return
        setUsuario(res.data)
        setRol(res.data?.rol || null)
      } catch {
        if (!activo) return
        clearTokens()
        setUsuario(null)
        setRol(null)
      } finally {
        if (activo) {
          setCargando(false)
        }
      }
    })()

    return () => {
      activo = false
    }
  }, [])

  const iniciarSesionGoogle = useCallback(async (credential) => {
    const data = await loginGoogle(credential)
    setUsuario(data.usuario || null)
    setRol(data.rol || data.usuario?.rol || null)
    return data
  }, [])

  const esAdmin = useMemo(
    () => (rol || usuario?.rol) === 'administrador',
    [rol, usuario]
  )

  const value = useMemo(
    () => ({
      usuario,
      rol,
      esAdmin,
      cargando,
      iniciarSesionGoogle,
      cerrarSesion,
    }),
    [usuario, rol, esAdmin, cargando, iniciarSesionGoogle, cerrarSesion]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
