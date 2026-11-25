import { useCallback, useMemo, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react'
import { ToastContext } from './toastContext'

const ICONOS = {
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
  info: Info,
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)

  const cerrarToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const mostrarToast = useCallback(
    ({ tipo = 'info', titulo, mensaje, duracion = 4500 }) => {
      idRef.current += 1
      const id = idRef.current
      setToasts((prev) => [...prev.slice(-4), { id, tipo, titulo, mensaje }])
      if (duracion > 0) {
        setTimeout(() => {
          cerrarToast(id)
        }, duracion)
      }
      return id
    },
    [cerrarToast]
  )

  const value = useMemo(
    () => ({ toasts, mostrarToast, cerrarToast }),
    [toasts, mostrarToast, cerrarToast]
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-atomic="true">
        {toasts.map((toast) => {
          const Icono = ICONOS[toast.tipo] || Info
          return (
            <div key={toast.id} className={`toast-item toast-${toast.tipo}`} role="status">
              <div className="toast-icon">
                <Icono size={18} />
              </div>
              <div className="toast-body">
                {toast.titulo && <div className="toast-title">{toast.titulo}</div>}
                {toast.mensaje && <div className="toast-msg">{toast.mensaje}</div>}
              </div>
              <button
                type="button"
                className="toast-close"
                onClick={() => cerrarToast(toast.id)}
                aria-label="Cerrar notificación"
              >
                <X size={15} />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}
