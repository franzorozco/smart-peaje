import Pusher from 'pusher-js'
import api from './api'

const PUSHER_KEY = import.meta.env.VITE_PUSHER_KEY?.trim() || ''
const PUSHER_CLUSTER = import.meta.env.VITE_PUSHER_CLUSTER?.trim() || ''

export function realtimeConfigurado() {
  if (!PUSHER_KEY || PUSHER_KEY === 'TU_PUSHER_KEY') return false
  if (!PUSHER_CLUSTER || PUSHER_CLUSTER === 'TU_CLUSTER') return false
  return true
}

let pusherInstancia = null
let canalInstancia = null
let estadoActual = 'disconnected'
const suscriptores = new Set()

function notificarEstado(estado) {
  estadoActual = estado
  for (const sub of suscriptores) {
    sub.onEstadoConexion?.(estado)
  }
}

function asegurarConexion() {
  if (pusherInstancia) return

  pusherInstancia = new Pusher(PUSHER_KEY, {
    cluster: PUSHER_CLUSTER,
    channelAuthorization: {
      customHandler: ({ socketId, channelName }, callback) => {
        const params = new URLSearchParams({
          socket_id: socketId,
          channel_name: channelName,
        })
        api
          .post('realtime/auth', params, {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          })
          .then((res) => callback(null, res.data))
          .catch((err) => {
            callback(
              err instanceof Error
                ? err
                : new Error('No se pudo autorizar el canal en tiempo real'),
              null
            )
          })
      },
    },
  })

  estadoActual = pusherInstancia.connection.state || 'initialized'

  pusherInstancia.connection.bind('state_change', ({ current }) => {
    notificarEstado(current)
  })

  canalInstancia = pusherInstancia.subscribe('private-peaje')

  canalInstancia.bind('nuevo-paso', (data) => {
    for (const sub of suscriptores) {
      sub.onPaso?.(data)
    }
  })

  canalInstancia.bind('nueva-alerta', (data) => {
    for (const sub of suscriptores) {
      sub.onAlerta?.(data, 'nueva-alerta')
    }
  })

  canalInstancia.bind('alerta-atendida', (data) => {
    for (const sub of suscriptores) {
      sub.onAlertaAtendida?.(data)
      sub.onAlerta?.(data, 'alerta-atendida')
    }
  })
}

function destruirConexionSiVacia() {
  if (suscriptores.size > 0 || !pusherInstancia) return
  if (canalInstancia) {
    canalInstancia.unbind_all()
    pusherInstancia.unsubscribe('private-peaje')
    canalInstancia = null
  }
  pusherInstancia.connection.unbind_all()
  pusherInstancia.disconnect()
  pusherInstancia = null
  estadoActual = 'disconnected'
}

export function escuchar({ onPaso, onAlerta, onAlertaAtendida, onEstadoConexion } = {}) {
  if (!realtimeConfigurado()) {
    queueMicrotask(() => {
      onEstadoConexion?.('no configurado')
    })
    return () => {}
  }

  const suscriptor = {
    onPaso,
    onAlerta,
    onAlertaAtendida,
    onEstadoConexion,
  }
  suscriptores.add(suscriptor)
  asegurarConexion()

  const estadoInicial = pusherInstancia?.connection?.state || estadoActual
  queueMicrotask(() => {
    if (suscriptores.has(suscriptor)) {
      onEstadoConexion?.(estadoInicial)
    }
  })

  return () => {
    suscriptores.delete(suscriptor)
    destruirConexionSiVacia()
  }
}
