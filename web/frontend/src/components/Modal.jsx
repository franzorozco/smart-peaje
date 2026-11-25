import { useEffect } from 'react'
import { X } from 'lucide-react'

export default function Modal({
  abierto,
  onCerrar,
  titulo,
  children,
  pie,
  ancho = 'md',
}) {
  useEffect(() => {
    if (!abierto) return undefined
    const handleKey = (e) => {
      if (e.key === 'Escape') {
        onCerrar?.()
      }
    }
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleKey)
    return () => {
      document.body.style.overflow = prevOverflow
      window.removeEventListener('keydown', handleKey)
    }
  }, [abierto, onCerrar])

  if (!abierto) return null

  return (
    <div
      className="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onCerrar?.()
        }
      }}
      role="dialog"
      aria-modal="true"
      aria-label={titulo || 'Ventana modal'}
    >
      <div className={`modal-card modal-${ancho}`}>
        <div className="modal-header">
          <h3>{titulo}</h3>
          <button
            type="button"
            className="btn-icon"
            onClick={onCerrar}
            aria-label="Cerrar"
          >
            <X size={18} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {pie && <div className="modal-footer">{pie}</div>}
      </div>
    </div>
  )
}
