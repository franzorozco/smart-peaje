import { StyleSheet, Text, View } from 'react-native';

import { Palette } from '@/constants/theme';

interface EstadoStyle {
  bg: string;
  text: string;
  label: string;
}

const ESTADO_MAP: Record<string, EstadoStyle> = {
  pagado: {
    bg: Palette.successBg,
    text: Palette.successText,
    label: 'Pagado',
  },
  sin_saldo: {
    bg: Palette.dangerBg,
    text: Palette.dangerText,
    label: 'Sin saldo',
  },
  no_registrado: {
    bg: Palette.orangeBg,
    text: Palette.orangeText,
    label: 'No registrado',
  },
  inactivo: {
    bg: Palette.neutralBg,
    text: Palette.neutralText,
    label: 'Inactivo',
  },
  revision: {
    bg: Palette.warningBg,
    text: Palette.warningText,
    label: 'Revisión',
  },
  'Registrada y con paso': {
    bg: Palette.successBg,
    text: Palette.successText,
    label: 'Registrada y con paso',
  },
  'Registrada sin paso': {
    bg: Palette.infoBg,
    text: Palette.infoText,
    label: 'Registrada sin paso',
  },
  'Identificada no registrada': {
    bg: Palette.orangeBg,
    text: Palette.orangeText,
    label: 'Identificada no registrada',
  },
  'No existe': {
    bg: Palette.dangerBg,
    text: Palette.dangerText,
    label: 'No existe',
  },
};

export function EstadoBadge({ estado }: { estado: string }) {
  const config = ESTADO_MAP[estado] ?? {
    bg: Palette.neutralBg,
    text: Palette.neutralText,
    label: estado,
  };

  return (
    <View style={[styles.badge, { backgroundColor: config.bg }]}>
      <Text style={[styles.text, { color: config.text }]}>{config.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  text: {
    fontSize: 12,
    fontWeight: '700',
  },
});
