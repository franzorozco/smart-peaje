import axios from 'axios'

const RAW_API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
export const API_BASE_URL = RAW_API_URL.replace(/\/+$/, '')

const REFRESH_STORAGE_KEY = 'smart_peaje_refresh_token'

let accessToken = null
let refreshPromise = null
let onAuthFailureCallback = null

export function getToken() {
  return accessToken
}

export function getRefreshToken() {
  try {
    return sessionStorage.getItem(REFRESH_STORAGE_KEY)
  } catch {
    return null
  }
}

export function setTokens({ access, refresh }) {
  if (access !== undefined) {
    accessToken = access || null
  }
  if (refresh !== undefined) {
    try {
      if (refresh) {
        sessionStorage.setItem(REFRESH_STORAGE_KEY, refresh)
      } else {
        sessionStorage.removeItem(REFRESH_STORAGE_KEY)
      }
    } catch {
      // sessionStorage no disponible
    }
  }
}

export function clearTokens() {
  accessToken = null
  try {
    sessionStorage.removeItem(REFRESH_STORAGE_KEY)
  } catch {
    // sessionStorage no disponible
  }
}

export function setOnAuthFailure(callback) {
  onAuthFailureCallback = callback
}

export async function refreshSession() {
  const refresh = getRefreshToken()
  if (!refresh) {
    throw new Error('No hay token de actualización')
  }
  if (!refreshPromise) {
    refreshPromise = axios
      .post(`${API_BASE_URL}/auth/refresh`, { refresh })
      .then((res) => {
        const { access, refresh: nuevoRefresh } = res.data || {}
        if (!access) {
          throw new Error('Respuesta de renovación inválida')
        }
        setTokens({
          access,
          refresh: nuevoRefresh || refresh,
        })
        return access
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

const api = axios.create({
  baseURL: API_BASE_URL,
})

api.interceptors.request.use((config) => {
  const url = config.url || ''
  const esEndpointPublico = url.includes('auth/google') || url.includes('auth/refresh')
  if (!esEndpointPublico && accessToken) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error?.config
    const status = error?.response?.status
    const url = originalRequest?.url || ''

    if (
      status !== 401 ||
      !originalRequest ||
      originalRequest._retry ||
      url.includes('auth/refresh') ||
      url.includes('auth/google')
    ) {
      return Promise.reject(error)
    }

    if (!getRefreshToken()) {
      clearTokens()
      onAuthFailureCallback?.()
      return Promise.reject(error)
    }

    originalRequest._retry = true
    try {
      const nuevoAccess = await refreshSession()
      originalRequest.headers = originalRequest.headers || {}
      originalRequest.headers.Authorization = `Bearer ${nuevoAccess}`
      return api(originalRequest)
    } catch (refreshError) {
      clearTokens()
      onAuthFailureCallback?.()
      return Promise.reject(refreshError)
    }
  }
)

export async function loginGoogle(credential) {
  const res = await api.post('auth/google', { id_token: credential })
  const data = res.data
  setTokens({ access: data.access, refresh: data.refresh })
  return data
}

export default api
