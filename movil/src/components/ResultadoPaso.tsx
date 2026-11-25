import { Image } from 'expo-image';
import { StyleSheet, Text, View } from 'react-native';

import { Fonts, Palette } from '@/constants/theme';
import type { PasoFrameResponse } from '@/lib/types';

import { EstadoBadge } from './EstadoBadge';

function formatCategoria(cat: string): string {
  if (!cat) return '—';
  return cat.charAt(0).toUpperCase() + cat.slice(1);
}

function formatConfianza(confianza: number | null): string {
  if (confianza === null || confianza === undefined) {
    return '—';
  }
  const pct = confianza <= 1 ? Math.round(confianza * 100) : Math.round(confianza);
  return `${pct}%`;
}

function MetricItem({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

export function ResultadoPaso({ resultado }: { resultado: PasoFrameResponse }) {
  const { paso, saldo_restante, nuevo } = resultado;
  const placaPrincipal = paso.placa_normalizada || paso.placa_leida || 'SIN PLACA';

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.plateWrap}>
          <Text style={styles.plateLabel}>Placa detectada</Text>
          <Text style={styles.plateValue}>{placaPrincipal}</Text>
          {paso.placa_leida && paso.placa_leida !== placaPrincipal ? (
            <Text style={styles.rawPlate}>Lectura cruda: {paso.placa_leida}</Text>
          ) : null}
        </View>
        <View style={styles.badgesColumn}>
          <EstadoBadge estado={paso.estado} />
          {!nuevo ? <Text style={styles.duplicateTag}>Captura ya registrada</Text> : null}
        </View>
      </View>

      {paso.imagen ? (
        <View style={styles.evidenceWrap}>
          <Image
            source={{ uri: paso.imagen }}
            style={styles.evidenceImage}
            contentFit="contain"
          />
          <Text style={styles.evidenceLegend}>
            Capas IA: vehículo (M2) · ejes/llantas amarillo (M3) · ocupantes M4 sin rostros (cian/ámbar)
          </Text>
        </View>
      ) : null}

      <View style={styles.grid}>
        <MetricItem label="Categoría" value={formatCategoria(paso.categoria_detectada)} />
        <MetricItem label="Ejes" value={String(paso.ejes_detectados ?? '—')} />
        <MetricItem label="Tarifa" value={`Bs ${paso.monto}`} />
        <MetricItem
          label="Pasajeros (M4)"
          value={
            paso.pasajeros !== null && paso.pasajeros !== undefined
              ? paso.pasajeros === 0
                ? '0 observados'
                : `${paso.pasajeros} visible${paso.pasajeros === 1 ? '' : 's'}`
              : 'No determinable'
          }
        />
        <MetricItem label="Confianza OCR" value={formatConfianza(paso.confianza_ocr)} />
        <MetricItem
          label="Saldo restante"
          value={saldo_restante !== null && saldo_restante !== undefined ? `Bs ${saldo_restante}` : '—'}
        />
      </View>

      <View style={styles.footer}>
        <Text style={styles.footerText}>{paso.caseta_nombre}</Text>
        <Text style={styles.footerText}>{paso.latencia_ms} ms</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: Palette.surface,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: Palette.border,
    padding: 16,
    gap: 14,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  },
  plateWrap: {
    flex: 1,
  },
  plateLabel: {
    fontSize: 12,
    color: Palette.textMuted,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  plateValue: {
    fontSize: 26,
    fontWeight: '800',
    fontFamily: Fonts?.mono,
    color: Palette.text,
    marginTop: 2,
  },
  rawPlate: {
    fontSize: 12,
    color: Palette.textSecondary,
    marginTop: 2,
  },
  badgesColumn: {
    alignItems: 'flex-end',
    gap: 6,
  },
  duplicateTag: {
    fontSize: 11,
    color: Palette.textMuted,
    fontWeight: '600',
  },
  evidenceWrap: {
    gap: 6,
  },
  evidenceImage: {
    width: '100%',
    height: 210,
    borderRadius: 12,
    backgroundColor: '#0F172A',
  },
  evidenceLegend: {
    fontSize: 11,
    color: Palette.textMuted,
    lineHeight: 15,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  metric: {
    width: '47%',
    backgroundColor: Palette.surfaceMuted,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  metricLabel: {
    fontSize: 12,
    color: Palette.textMuted,
    fontWeight: '500',
  },
  metricValue: {
    fontSize: 15,
    fontWeight: '700',
    color: Palette.text,
    marginTop: 2,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: Palette.border,
    paddingTop: 10,
  },
  footerText: {
    fontSize: 12,
    color: Palette.textMuted,
  },
});
