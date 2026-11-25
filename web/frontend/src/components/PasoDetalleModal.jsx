import { useState } from 'react'
import { ImageOff } from 'lucide-react'
import {
  esVehiculoPesado,
  etiquetaCategoria,
  explicarEstadoCobro,
  formatBs,
  formatFechaHora,
} from '../utils/format'
import EstadoBadge from './EstadoBadge'
import Modal from './Modal'

function VisorImagen({ src, alt }) {
  const [errorCarga, setErrorCarga] = useState(false)

  if (!src || errorCarga) {
    return (
      <div className="evidence-empty">
        <ImageOff size={32} />
        <span>
          {src
            ? 'La imagen de evidencia no pudo cargarse o el enlace firmado expiró.'
            : 'Este paso no cuenta con imagen de evidencia.'}
        </span>
      </div>
    )
  }

  return (
    <div className="evidence-frame">
      <img src={src} alt={alt} onError={() => setErrorCarga(true)} />
    </div>
  )
}

export default function PasoDetalleModal({ paso, onCerrar }) {
  return (
    <Modal
      abierto={Boolean(paso)}
      onCerrar={onCerrar}
      titulo={paso ? `Detalle de paso #${paso.id}` : 'Detalle de paso'}
      ancho="lg"
      pie={
        <button type="button" className="btn btn-secondary" onClick={onCerrar}>
          Cerrar
        </button>
      }
    >
      {paso && (
        <div className="paso-detail-grid">
          <div className="paso-detail-image">
            <VisorImagen
              key={paso.imagen || paso.id}
              src={paso.imagen}
              alt={`Evidencia de paso ${paso.placa_normalizada || paso.placa_leida || paso.id}`}
            />
            <p className="text-xs muted" style={{ marginTop: '0.5rem' }}>
              Capas visibles: máscara vehículo (M2) · ejes/llantas en amarillo (M3) ·
              ocupantes M4 con máscaras opacas sin rostros (cian = conductor probable, ámbar = pasajero).
            </p>
          </div>

          <div className="paso-detail-meta">
            <div className="detail-row">
              <span>Estado</span>
              <EstadoBadge estado={paso.estado} />
            </div>
            <div className="detail-row">
              <span>Placa normalizada</span>
              <strong className="mono-plate">
                {paso.placa_normalizada || '—'}
              </strong>
            </div>
            <div className="detail-row">
              <span>Placa leída (OCR)</span>
              <span className="mono">{paso.placa_leida || '—'}</span>
            </div>
            <div className="detail-row">
              <span>Confianza OCR</span>
              <span>
                {paso.confianza_ocr !== null && paso.confianza_ocr !== undefined
                  ? `${(Number(paso.confianza_ocr) * 100).toFixed(1)}%`
                  : 'N/D'}
              </span>
            </div>
            <div className="detail-row">
              <span>Categoría detectada</span>
              <span>{etiquetaCategoria(paso.categoria_detectada)}</span>
            </div>
            <div className="detail-row">
              <span>Ejes detectados</span>
              <span>{paso.ejes_detectados ?? '—'}</span>
            </div>
            <div className="detail-row">
              <span>Pasajeros visibles (M4)</span>
              <span>
                {paso.pasajeros !== null && paso.pasajeros !== undefined
                  ? paso.pasajeros === 0
                    ? '0 observados'
                    : `${paso.pasajeros} visible${paso.pasajeros === 1 ? '' : 's'}`
                  : 'No determinable (null)'}
              </span>
            </div>
            <div className="detail-row">
              <span>Monto</span>
              <strong>{formatBs(paso.monto)}</strong>
            </div>
            <div
              className="text-xs"
              style={{
                padding: '0.6rem 0.75rem',
                borderRadius: '8px',
                background: 'rgba(15, 23, 42, 0.55)',
                border: '1px solid rgba(148, 163, 184, 0.18)',
                lineHeight: 1.5,
              }}
            >
              <div>
                <strong>Criterio tarifario:</strong>{' '}
                {esVehiculoPesado(paso.categoria_detectada)
                  ? `${etiquetaCategoria(paso.categoria_detectada)} (${paso.ejes_detectados || '—'} ejes · tarifa por categoría + ejes)`
                  : `${etiquetaCategoria(paso.categoria_detectada)} (tarifa base por categoría)`}
                {' · Pasajeros (M4): informativo (Bs 0.00).'}
              </div>
              <div className="muted" style={{ marginTop: '0.2rem' }}>
                {explicarEstadoCobro(paso.estado, paso.monto)}
              </div>
            </div>
            <div className="detail-row">
              <span>Caseta</span>
              <span>
                {paso.caseta_nombre || '—'}
                {paso.caseta ? ` (#${paso.caseta})` : ''}
              </span>
            </div>
            <div className="detail-row">
              <span>Operador</span>
              <span>{paso.usuario_email || '—'}</span>
            </div>
            <div className="detail-row">
              <span>Latencia IA</span>
              <span>
                {paso.latencia_ms !== null && paso.latencia_ms !== undefined
                  ? `${paso.latencia_ms} ms`
                  : '—'}
              </span>
            </div>
            <div className="detail-row">
              <span>Fecha y hora</span>
              <span>{formatFechaHora(paso.created_at)}</span>
            </div>
            <div className="detail-row">
              <span>Captura UUID</span>
              <span className="mono text-xs">{paso.captura_id || '—'}</span>
            </div>
          </div>
        </div>
      )}
    </Modal>
  )
}
