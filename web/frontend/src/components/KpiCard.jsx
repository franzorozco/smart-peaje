export default function KpiCard({
  titulo,
  valor,
  subtitulo,
  icono: Icono,
  variante = 'default',
}) {
  return (
    <div className={`kpi-card kpi-${variante}`}>
      <div className="kpi-header">
        <span className="kpi-title">{titulo}</span>
        {Icono && (
          <span className="kpi-icon-wrap">
            <Icono size={18} />
          </span>
        )}
      </div>
      <div className="kpi-value">{valor}</div>
      {subtitulo && <div className="kpi-sub">{subtitulo}</div>}
    </div>
  )
}
