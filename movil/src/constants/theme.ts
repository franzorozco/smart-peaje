import { Platform } from 'react-native';

export const Palette = {
  primary: '#1D4ED8',
  primaryDark: '#1E3A8A',
  primaryLight: '#EFF6FF',
  background: '#F8FAFC',
  surface: '#FFFFFF',
  surfaceMuted: '#F1F5F9',
  border: '#E2E8F0',
  text: '#0F172A',
  textSecondary: '#475569',
  textMuted: '#64748B',
  successBg: '#DCFCE7',
  successText: '#166534',
  infoBg: '#DBEAFE',
  infoText: '#1E40AF',
  warningBg: '#FEF3C7',
  warningText: '#92400E',
  orangeBg: '#FFEDD5',
  orangeText: '#9A3412',
  dangerBg: '#FEE2E2',
  dangerText: '#991B1B',
  danger: '#DC2626',
  neutralBg: '#E2E8F0',
  neutralText: '#334155',
} as const;

export const Fonts = Platform.select({
  ios: {
    sans: 'system-ui',
    mono: 'ui-monospace',
  },
  default: {
    sans: 'sans-serif',
    mono: 'monospace',
  },
  web: {
    sans: 'system-ui, -apple-system, sans-serif',
    mono: 'ui-monospace, SFMono-Regular, Menlo, monospace',
  },
});
