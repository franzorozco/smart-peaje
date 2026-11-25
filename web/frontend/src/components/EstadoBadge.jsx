const MAPA_ESTADOS = {
  pagado: { clase: 'badge-green', etiqueta: 'Pagado' },
  sin_saldo: { clase: 'badge-amber', etiqueta: 'Sin saldo' },
  no_registrado: { clase: 'badge-red', etiqueta: 'No registrado' },
  inactivo: { clase: 'badge-gray', etiqueta: 'Inactivo' },
  revision: { clase: 'badge-violet', etiqueta: 'Revisión' },
  'Registrada y con paso': { clase: 'badge-green', etiqueta: 'Registrada y con paso' },
  'Registrada sin paso': { clase: 'badge-blue', etiqueta: 'Registrada sin paso' },
  'Identificada no registrada': { clase: 'badge-amber', etiqueta: 'Identificada no registrada' },
  'No existe': { clase: 'badge-red', etiqueta: 'No existe' },
  activo: { clase: 'badge-green', etiqueta: 'Activo' },
  pendiente: { clase: 'badge-amber', etiqueta: 'Pendiente' },
  atendida: { clase: 'badge-green', etiqueta: 'Atendida' },
  ok: { clase: 'badge-green', etiqueta: 'Operativo' },
  error: { clase: 'badge-red', etiqueta: 'Error' },
  administrador: { clase: 'badge-green', etiqueta: 'Administrador' },
  operador: { clase: 'badge-blue', etiqueta: 'Operador' },
}

export default function EstadoBadge({ estado, texto }) {
  if (estado === null || estado === undefined || estado === '') {
    return <span className="badge badge-gray">{texto || '—'}</span>
  }

  if (typeof estado === 'boolean') {
    const info = estado ? MAPA_ESTADOS.activo : MAPA_ESTADOS.inactivo
    return <span className={`badge ${info.clase}`}>{texto || info.etiqueta}</span>
  }

  const clave = String(estado)
  const info = MAPA_ESTADOS[clave] || {
    clase: 'badge-gray',
    etiqueta: clave,
  }

  return <span className={`badge ${info.clase}`}>{texto || info.etiqueta}</span>
}
