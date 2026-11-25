import Ionicons from '@expo/vector-icons/Ionicons';
import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { Fonts, Palette } from '@/constants/theme';
import { useAuth } from '@/lib/auth-context';
import { API_URL } from '@/lib/config';
import { useCasetas } from '@/lib/use-casetas';

export default function AjustesScreen() {
  const { user, signOut } = useAuth();
  const {
    casetas,
    selectedCasetaId,
    selectCaseta,
    loading: loadingCasetas,
    error: casetasError,
    reload: reloadCasetas,
  } = useCasetas();

  const [signingOut, setSigningOut] = useState(false);

  const handleLogout = async () => {
    setSigningOut(true);
    try {
      await signOut();
    } finally {
      setSigningOut(false);
    }
  };

  const rolLabel = user?.rol === 'administrador' ? 'Administrador' : 'Operador';

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      {/* Cuenta */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Sesión activa</Text>
        <View style={styles.userRow}>
          <View style={styles.avatar}>
            <Ionicons name="person" size={24} color={Palette.primary} />
          </View>
          <View style={styles.userInfo}>
            <Text style={styles.userName}>{user?.nombre || 'Usuario'}</Text>
            <Text style={styles.userEmail}>{user?.email || '—'}</Text>
          </View>
          <View style={styles.roleBadge}>
            <Text style={styles.roleText}>{rolLabel}</Text>
          </View>
        </View>
      </View>

      {/* Selección de Caseta */}
      <View style={styles.card}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Caseta asignada</Text>
          <Pressable style={styles.refreshBtn} onPress={reloadCasetas} disabled={loadingCasetas}>
            <Ionicons name="refresh" size={16} color={Palette.primary} />
            <Text style={styles.refreshText}>Actualizar</Text>
          </Pressable>
        </View>

        {loadingCasetas ? (
          <View style={styles.loadingBox}>
            <ActivityIndicator size="small" color={Palette.primary} />
            <Text style={styles.mutedText}>Cargando casetas...</Text>
          </View>
        ) : casetasError ? (
          <Text style={styles.errorText}>{casetasError}</Text>
        ) : casetas.length === 0 ? (
          <Text style={styles.mutedText}>No hay casetas registradas.</Text>
        ) : (
          <View style={styles.casetasList}>
            {casetas.map((caseta) => {
              const active = caseta.id === selectedCasetaId;
              return (
                <Pressable
                  key={caseta.id}
                  style={[styles.casetaItem, active && styles.casetaItemActive]}
                  onPress={() => selectCaseta(caseta.id)}>
                  <View style={styles.casetaItemText}>
                    <Text style={styles.casetaName}>{caseta.nombre}</Text>
                    <Text style={styles.casetaUbicacion}>{caseta.ubicacion}</Text>
                  </View>
                  <Ionicons
                    name={active ? 'radio-button-on' : 'radio-button-off'}
                    size={20}
                    color={active ? Palette.primary : Palette.textMuted}
                  />
                </Pressable>
              );
            })}
          </View>
        )}
      </View>

      {/* Configuración del servidor */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Servidor API</Text>
        <View style={styles.apiBox}>
          <Text style={styles.apiUrl} selectable>
            {API_URL}
          </Text>
        </View>
      </View>

      {/* Cerrar sesión */}
      <Pressable
        style={({ pressed }) => [
          styles.logoutButton,
          signingOut && styles.disabled,
          pressed && styles.pressed,
        ]}
        disabled={signingOut}
        onPress={handleLogout}>
        {signingOut ? (
          <ActivityIndicator size="small" color="#FFFFFF" />
        ) : (
          <Ionicons name="log-out-outline" size={20} color="#FFFFFF" />
        )}
        <Text style={styles.logoutText}>{signingOut ? 'Cerrando sesión...' : 'Cerrar sesión'}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: Palette.background,
  },
  content: {
    padding: 16,
    gap: 14,
    paddingBottom: 32,
  },
  card: {
    backgroundColor: Palette.surface,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: Palette.border,
    padding: 16,
    gap: 12,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: Palette.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  userRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  avatar: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: Palette.primaryLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  userInfo: {
    flex: 1,
    gap: 2,
  },
  userName: {
    fontSize: 16,
    fontWeight: '700',
    color: Palette.text,
  },
  userEmail: {
    fontSize: 13,
    color: Palette.textSecondary,
  },
  roleBadge: {
    backgroundColor: Palette.infoBg,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  roleText: {
    fontSize: 12,
    fontWeight: '700',
    color: Palette.infoText,
  },
  refreshBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  refreshText: {
    fontSize: 13,
    fontWeight: '700',
    color: Palette.primary,
  },
  loadingBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  mutedText: {
    fontSize: 14,
    color: Palette.textSecondary,
  },
  errorText: {
    fontSize: 14,
    color: Palette.dangerText,
  },
  casetasList: {
    gap: 8,
  },
  casetaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: Palette.border,
  },
  casetaItemActive: {
    borderColor: Palette.primary,
    backgroundColor: Palette.primaryLight,
  },
  casetaItemText: {
    flex: 1,
    gap: 2,
  },
  casetaName: {
    fontSize: 15,
    fontWeight: '700',
    color: Palette.text,
  },
  casetaUbicacion: {
    fontSize: 13,
    color: Palette.textSecondary,
  },
  apiBox: {
    backgroundColor: Palette.surfaceMuted,
    borderRadius: 10,
    padding: 12,
  },
  apiUrl: {
    fontSize: 13,
    fontFamily: Fonts?.mono,
    color: Palette.text,
  },
  logoutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: Palette.danger,
    paddingVertical: 15,
    borderRadius: 14,
    marginTop: 4,
  },
  logoutText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
  },
  disabled: {
    opacity: 0.6,
  },
  pressed: {
    opacity: 0.85,
  },
});
