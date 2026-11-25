import { useEffect, useRef, useState } from 'react'
import {
  Bot,
  ImagePlus,
  Send,
  Sparkles,
  User,
  X,
} from 'lucide-react'
import api from '../api'
import EstadoBadge from '../components/EstadoBadge'
import {
  etiquetaCategoria,
  extraerErrorApi,
  formatBs,
  formatFechaHora,
} from '../utils/format'

const MENSAJE_BIENVENIDA = {
  id: 'bienvenida',
  emisor: 'agente',
  respuesta:
    'Hola, soy el asistente de Smart Peaje. Puedes escribir una placa (ej. 1234ABC), pedir el historial de un vehículo o adjuntar una foto para consultar su estado.',
  tool: null,
  estado: null,
  datos: null,
  sugerencias: [],
  requiere: null,
}

export default function Chat() {
  const [mensajes, setMensajes] = useState([MENSAJE_BIENVENIDA])
  const [texto, setTexto] = useState('')
  const [archivo, setArchivo] = useState(null)
  const [previewArchivo, setPreviewArchivo] = useState('')
  const [enviando, setEnviando] = useState(false)

  const fileInputRef = useRef(null)
  const finChatRef = useRef(null)
  const urlsCreadasRef = useRef([])
  const msgIdRef = useRef(0)

  useEffect(() => {
    finChatRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [mensajes, enviando])

  useEffect(() => {
    return () => {
      for (const url of urlsCreadasRef.current) {
        URL.revokeObjectURL(url)
      }
      urlsCreadasRef.current = []
    }
  }, [])

  const seleccionarArchivo = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const url = URL.createObjectURL(file)
    urlsCreadasRef.current.push(url)
    setArchivo(file)
    setPreviewArchivo(url)
  }

  const limpiarArchivo = () => {
    setArchivo(null)
    setPreviewArchivo('')
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const enviarMensaje = async ({ textoDirecto } = {}) => {
    const contenidoTexto = (
      textoDirecto !== undefined ? textoDirecto : texto
    ).trim()
    const archivoAEnviar = textoDirecto !== undefined ? null : archivo

    if (!contenidoTexto && !archivoAEnviar) return
    if (enviando) return

    msgIdRef.current += 1
    const idUsuario = `user-${msgIdRef.current}`
    const imagenBubble = archivoAEnviar ? previewArchivo : ''

    setMensajes((prev) => [
      ...prev,
      {
        id: idUsuario,
        emisor: 'usuario',
        texto: contenidoTexto,
        imagenUrl: imagenBubble,
      },
    ])

    if (textoDirecto === undefined) {
      setTexto('')
      setArchivo(null)
      setPreviewArchivo('')
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }

    setEnviando(true)
    try {
      let res
      if (archivoAEnviar) {
        const formData = new FormData()
        formData.append('file', archivoAEnviar)
        if (contenidoTexto) {
          formData.append('mensaje', contenidoTexto)
        }
        res = await api.post('agente/chat', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      } else {
        res = await api.post('agente/chat', { mensaje: contenidoTexto })
      }

      const data = res.data || {}
      msgIdRef.current += 1
      setMensajes((prev) => [
        ...prev,
        {
          id: `agente-${msgIdRef.current}`,
          emisor: 'agente',
          respuesta: data.respuesta || 'Sin respuesta del asistente.',
          tool: data.tool || null,
          estado: data.estado ?? null,
          datos: data.datos ?? null,
          sugerencias: Array.isArray(data.sugerencias) ? data.sugerencias : [],
          requiere: data.requiere ?? null,
        },
      ])
    } catch (err) {
      msgIdRef.current += 1
      setMensajes((prev) => [
        ...prev,
        {
          id: `err-${msgIdRef.current}`,
          emisor: 'agente',
          esError: true,
          respuesta: extraerErrorApi(
            err,
            'No se pudo procesar la consulta en este momento.'
          ),
          sugerencias: [],
        },
      ])
    } finally {
      setEnviando(false)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    enviarMensaje()
  }

  return (
    <div className="chat-shell panel-card">
      <div className="chat-messages">
        {mensajes.map((msg) => {
          if (msg.emisor === 'usuario') {
            return (
              <div key={msg.id} className="chat-row chat-row-user">
                <div className="chat-bubble chat-bubble-user">
                  {msg.imagenUrl && (
                    <img
                      src={msg.imagenUrl}
                      alt="Imagen enviada"
                      className="chat-sent-img"
                    />
                  )}
                  {msg.texto && <p>{msg.texto}</p>}
                </div>
                <div className="chat-avatar chat-avatar-user">
                  <User size={16} />
                </div>
              </div>
            )
          }

          const datos = msg.datos
          const ultimoPaso = datos?.ultimo_paso
          const lectura = datos?.lectura
          const vehiculo = datos?.vehiculo
          const historialPasos =
            msg.tool === 'historial' && Array.isArray(datos?.pasos)
              ? datos.pasos
              : null

          return (
            <div key={msg.id} className="chat-row chat-row-agent">
              <div className="chat-avatar chat-avatar-agent">
                <Bot size={16} />
              </div>
              <div
                className={`chat-bubble chat-bubble-agent ${
                  msg.esError ? 'chat-bubble-error' : ''
                }`}
              >
                <div className="chat-meta-badges">
                  {msg.estado && <EstadoBadge estado={msg.estado} />}
                  {msg.requiere && (
                    <span className="badge badge-blue">
                      Requiere: {msg.requiere}
                    </span>
                  )}
                </div>

                <p className="chat-answer-text">{msg.respuesta}</p>

                {lectura && (
                  <div className="chat-subcard">
                    <div className="chat-subcard-title">Lectura OCR</div>
                    <div className="chat-subcard-grid">
                      <span>
                        Placa: <strong className="mono-plate">{lectura.placa || '—'}</strong>
                      </span>
                      <span>
                        Cruda: <span className="mono">{lectura.placa_cruda || '—'}</span>
                      </span>
                      <span>
                        Confianza:{' '}
                        {lectura.confianza !== undefined &&
                        lectura.confianza !== null
                          ? `${(Number(lectura.confianza) * 100).toFixed(1)}%`
                          : 'N/D'}
                      </span>
                    </div>
                  </div>
                )}

                {vehiculo && (
                  <div className="chat-subcard">
                    <div className="chat-subcard-title">Vehículo registrado</div>
                    <div className="chat-subcard-grid">
                      <span>
                        Placa: <strong className="mono-plate">{vehiculo.placa}</strong>
                      </span>
                      <span>
                        Categoría: {etiquetaCategoria(vehiculo.categoria)}
                      </span>
                      <span>Ejes: {vehiculo.ejes}</span>
                      <span>
                        <EstadoBadge estado={Boolean(vehiculo.activo)} />
                      </span>
                    </div>
                  </div>
                )}

                {ultimoPaso && (
                  <div className="chat-subcard">
                    <div className="chat-subcard-title">Último paso registrado</div>
                    <div className="chat-subcard-grid">
                      <span>
                        Fecha:{' '}
                        {formatFechaHora(ultimoPaso.fecha)}
                      </span>
                      <span>Caseta: {ultimoPaso.caseta || '—'}</span>
                      <span>
                        Categoría: {etiquetaCategoria(ultimoPaso.categoria)}
                      </span>
                      <span>Monto: {formatBs(ultimoPaso.monto)}</span>
                      <span>
                        <EstadoBadge estado={ultimoPaso.estado_pago} />
                      </span>
                    </div>
                  </div>
                )}

                {historialPasos && historialPasos.length > 0 && (
                  <div className="chat-subcard">
                    <div className="chat-subcard-title">
                      Historial reciente ({datos.total ?? historialPasos.length})
                    </div>
                    <ul className="chat-history-list">
                      {historialPasos.slice(0, 5).map((hp) => (
                        <li key={hp.id}>
                          <span className="mono text-xs">
                            {formatFechaHora(hp.created_at)}
                          </span>
                          <span>{hp.caseta_nombre || '—'}</span>
                          <span>{formatBs(hp.monto)}</span>
                          <EstadoBadge estado={hp.estado} />
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {Array.isArray(msg.sugerencias) && msg.sugerencias.length > 0 && (
                  <div className="chat-suggestions">
                    <span className="text-xs muted">
                      <Sparkles size={12} /> Sugerencias:
                    </span>
                    <div className="chip-row">
                      {msg.sugerencias.map((placa) => (
                        <button
                          key={placa}
                          type="button"
                          className="suggestion-chip"
                          disabled={enviando}
                          onClick={() => enviarMensaje({ textoDirecto: placa })}
                        >
                          {placa}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {enviando && (
          <div className="chat-row chat-row-agent">
            <div className="chat-avatar chat-avatar-agent">
              <Bot size={16} />
            </div>
            <div className="chat-bubble chat-bubble-agent">
              <span className="muted">Consultando asistente...</span>
            </div>
          </div>
        )}
        <div ref={finChatRef} />
      </div>

      <form className="chat-composer" onSubmit={handleSubmit}>
        {previewArchivo && (
          <div className="chat-attachment-preview">
            <img src={previewArchivo} alt="Vista previa" />
            <div className="chat-attachment-info">
              <span>{archivo?.name}</span>
              <button
                type="button"
                className="btn-icon"
                onClick={limpiarArchivo}
                aria-label="Quitar imagen"
              >
                <X size={16} />
              </button>
            </div>
          </div>
        )}

        <div className="chat-input-row">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="sr-only"
            onChange={seleccionarArchivo}
          />
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={enviando}
            title="Adjuntar imagen de vehículo o placa"
          >
            <ImagePlus size={18} />
            <span className="hide-sm">Imagen</span>
          </button>

          <input
            type="text"
            className="chat-text-input"
            placeholder="Escribe una placa (ej. 1234ABC) o consulta..."
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            disabled={enviando}
          />

          <button
            type="submit"
            className="btn btn-primary"
            disabled={enviando || (!texto.trim() && !archivo)}
          >
            <Send size={16} />
            <span className="hide-sm">Enviar</span>
          </button>
        </div>
      </form>
    </div>
  )
}
