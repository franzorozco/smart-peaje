import { ChevronLeft, ChevronRight } from 'lucide-react'

export default function Paginacion({
  pagina,
  total,
  tamanioPagina = 25,
  onCambiarPagina,
}) {
  const totalPaginas = Math.max(1, Math.ceil((total || 0) / tamanioPagina))
  const desde = total === 0 ? 0 : (pagina - 1) * tamanioPagina + 1
  const hasta = Math.min(total || 0, pagina * tamanioPagina)

  if (!total && total !== 0) return null

  return (
    <div className="pagination-bar">
      <div className="pagination-info">
        Mostrando <strong>{desde}</strong>–<strong>{hasta}</strong> de{' '}
        <strong>{total}</strong> registros
      </div>
      <div className="pagination-controls">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={pagina <= 1}
          onClick={() => onCambiarPagina(pagina - 1)}
        >
          <ChevronLeft size={16} />
          Anterior
        </button>
        <span className="pagination-page">
          Página {pagina} de {totalPaginas}
        </span>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={pagina >= totalPaginas}
          onClick={() => onCambiarPagina(pagina + 1)}
        >
          Siguiente
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  )
}
