export const ZONA_HORARIA = 'America/La_Paz'

export const CATEGORIAS = [
  { value: 'moto', label: 'Moto' },
  { value: 'auto', label: 'Auto' },
  { value: 'minibus', label: 'Minibús' },
  { value: 'camion', label: 'Camión' },
  { value: 'bus', label: 'Bus' },
]

export function explicarEstadoCobro(estado, monto) {
  const m = formatBs(monto)
  switch (estado) {
    case 'pagado':
      return `Cobro automático de ${m} descontado del saldo del vehículo.`
    case 'sin_saldo':
      return `Saldo insuficiente para cobrar ${m}. Se generó alerta operativa.`
    case 'no_registrado':
      return `Placa no registrada en el padrón (tarifa ref. ${m}). Se generó alerta de posible evasión.`
    case 'inactivo':
      return `Vehículo inactivo en el padrón (tarifa ref. ${m}). Se generó alerta.`
    case 'revision':
      return 'Sin cobro automático (Bs 0.00): requiere validación del operador por discrepancia o ejes sin confirmar.'
    default:
      return ''
  }
}

export function esVehiculoPesado(categoria) {
  return categoria === 'camion' || categoria === 'bus'
}

export const ESTADOS_PASO = [
  { value: 'pagado', label: 'Pagado' },
  { value: 'sin_saldo', label: 'Sin saldo' },
  { value: 'no_registrado', label: 'No registrado' },
  { value: 'inactivo', label: 'Inactivo' },
  { value: 'revision', label: 'Revisión' },
]

export const ROLES = [
  { value: 'administrador', label: 'Administrador' },
  { value: 'operador', label: 'Operador' },
]

export const PLACA_REGEX = /^\d{3,4}[A-Z]{3}$/

export function formatBs(valor) {
  const num = Number(valor)
  if (!Number.isFinite(num)) return 'Bs 0.00'
  return `Bs ${num.toFixed(2)}`
}

export function formatFechaHora(iso) {
  if (!iso) return '—'
  const fecha = new Date(iso)
  if (Number.isNaN(fecha.getTime())) return String(iso)
  return new Intl.DateTimeFormat('es-BO', {
    timeZone: ZONA_HORARIA,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(fecha)
}

export function formatHora(iso) {
  if (!iso) return '—'
  const fecha = new Date(iso)
  if (Number.isNaN(fecha.getTime())) return String(iso)
  return new Intl.DateTimeFormat('es-BO', {
    timeZone: ZONA_HORARIA,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(fecha)
}

export function hoyFechaBolivia() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: ZONA_HORARIA,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

export function normalizarPlaca(valor) {
  return String(valor || '')
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, '')
}

export function validarPlaca(valor) {
  return PLACA_REGEX.test(normalizarPlaca(valor))
}

export function etiquetaCategoria(categoria) {
  const encontrada = CATEGORIAS.find((c) => c.value === categoria)
  return encontrada ? encontrada.label : categoria || '—'
}

export function etiquetaEstadoPaso(estado) {
  const encontrado = ESTADOS_PASO.find((e) => e.value === estado)
  return encontrado ? encontrado.label : estado || '—'
}

export function etiquetaRol(rol) {
  const encontrado = ROLES.find((r) => r.value === rol)
  return encontrado ? encontrado.label : rol || '—'
}

export function extraerErrorApi(error, fallback = 'Ocurrió un error al comunicarse con el servidor.') {
  const data = error?.response?.data
  if (!data) {
    if (error?.message === 'Network Error') {
      return 'No se pudo conectar con el servidor. Verifica que el backend esté en ejecución.'
    }
    return error?.message || fallback
  }
  if (typeof data === 'string') return data
  if (typeof data.error === 'string' && data.error.trim()) return data.error
  if (typeof data.detail === 'string' && data.detail.trim()) return data.detail

  const mensajes = []
  for (const [campo, valor] of Object.entries(data)) {
    if (Array.isArray(valor)) {
      mensajes.push(`${campo}: ${valor.join(', ')}`)
    } else if (typeof valor === 'string') {
      mensajes.push(`${campo}: ${valor}`)
    }
  }
  return mensajes.length > 0 ? mensajes.join(' · ') : fallback
}
