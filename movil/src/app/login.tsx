import Ionicons from '@expo/vector-icons/Ionicons';
import { GoogleSigninButton } from '@react-native-google-signin/google-signin';
import { useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Palette } from '@/constants/theme';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

export default function LoginScreen() {
  const { signInWithGoogle, isSigningIn } = useAuth();
  const [errorTitle, setErrorTitle] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleGoogleLogin = async () => {
    setErrorTitle(null);
    setErrorMessage(null);
    try {
      await signInWithGoogle();
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setErrorTitle('Acceso denegado');
        setErrorMessage(error.message || 'Acceso denegado: cuenta no autorizada');
      } else if (error instanceof Error) {
        setErrorTitle('No se pudo iniciar sesión');
        setErrorMessage(error.message);
      } else {
        setErrorTitle('No se pudo iniciar sesión');
        setErrorMessage('Ocurrió un error inesperado al autenticar.');
      }
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.card}>
          <View style={styles.logoCircle}>
            <Ionicons name="shield-checkmark" size={40} color={Palette.primary} />
          </View>

          <Text style={styles.title}>Smart Peaje</Text>
          <Text style={styles.subtitle}>
            Control de cobro vehicular y consulta inteligente para operadores de caseta.
          </Text>

          {errorMessage ? (
            <View style={styles.errorBox}>
              <View style={styles.errorHeader}>
                <Ionicons name="alert-circle" size={18} color={Palette.dangerText} />
                <Text style={styles.errorTitle}>{errorTitle ?? 'Error'}</Text>
              </View>
              <Text style={styles.errorText}>{errorMessage}</Text>
            </View>
          ) : null}

          <View style={styles.buttonArea}>
            {Platform.OS === 'web' ? (
              <Pressable
                style={({ pressed }) => [
                  styles.webGoogleButton,
                  pressed && styles.pressed,
                  isSigningIn && styles.disabled,
                ]}
                disabled={isSigningIn}
                onPress={handleGoogleLogin}>
                <Ionicons name="logo-google" size={18} color="#FFFFFF" />
                <Text style={styles.webGoogleText}>Continuar con Google</Text>
              </Pressable>
            ) : (
              <GoogleSigninButton
                size={GoogleSigninButton.Size.Wide}
                color={GoogleSigninButton.Color.Dark}
                disabled={isSigningIn}
                onPress={handleGoogleLogin}
              />
            )}

            {isSigningIn ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator size="small" color={Palette.primary} />
                <Text style={styles.loadingText}>Validando cuenta autorizada...</Text>
              </View>
            ) : null}
          </View>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: Palette.background,
  },
  container: {
    flex: 1,
    justifyContent: 'center',
    padding: 24,
  },
  card: {
    backgroundColor: Palette.surface,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: Palette.border,
    padding: 24,
    alignItems: 'center',
    gap: 14,
  },
  logoCircle: {
    width: 76,
    height: 76,
    borderRadius: 38,
    backgroundColor: Palette.primaryLight,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
  },
  title: {
    fontSize: 28,
    fontWeight: '800',
    color: Palette.text,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 15,
    color: Palette.textSecondary,
    textAlign: 'center',
    lineHeight: 22,
  },
  errorBox: {
    width: '100%',
    backgroundColor: Palette.dangerBg,
    borderRadius: 12,
    padding: 12,
    gap: 4,
  },
  errorHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  errorTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: Palette.dangerText,
  },
  errorText: {
    fontSize: 13,
    color: Palette.dangerText,
    lineHeight: 18,
  },
  buttonArea: {
    marginTop: 8,
    alignItems: 'center',
    gap: 12,
  },
  webGoogleButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    backgroundColor: Palette.primary,
    paddingHorizontal: 22,
    paddingVertical: 13,
    borderRadius: 10,
    minWidth: 260,
  },
  webGoogleText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
  },
  pressed: {
    opacity: 0.85,
  },
  disabled: {
    opacity: 0.6,
  },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  loadingText: {
    fontSize: 13,
    color: Palette.textSecondary,
  },
});
