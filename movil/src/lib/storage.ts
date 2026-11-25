import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import type { Usuario } from './types';

const KEYS = {
  access: 'peaje_access_token',
  refresh: 'peaje_refresh_token',
  usuario: 'peaje_usuario',
  casetaId: 'peaje_caseta_id',
} as const;

async function getItem(key: string): Promise<string | null> {
  if (Platform.OS === 'web') {
    return typeof window !== 'undefined' ? window.localStorage.getItem(key) : null;
  }
  return SecureStore.getItemAsync(key);
}

async function setItem(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(key, value);
    }
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

async function deleteItem(key: string): Promise<void> {
  if (Platform.OS === 'web') {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(key);
    }
    return;
  }
  await SecureStore.deleteItemAsync(key);
}

export async function getAccessToken(): Promise<string | null> {
  return getItem(KEYS.access);
}

export async function getRefreshToken(): Promise<string | null> {
  return getItem(KEYS.refresh);
}

export async function setTokens(access: string, refresh: string): Promise<void> {
  await Promise.all([setItem(KEYS.access, access), setItem(KEYS.refresh, refresh)]);
}

export async function getStoredUsuario(): Promise<Usuario | null> {
  const raw = await getItem(KEYS.usuario);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as Usuario;
  } catch {
    return null;
  }
}

export async function setStoredUsuario(usuario: Usuario): Promise<void> {
  await setItem(KEYS.usuario, JSON.stringify(usuario));
}

export async function getStoredCasetaId(): Promise<number | null> {
  const raw = await getItem(KEYS.casetaId);
  if (!raw) {
    return null;
  }
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export async function setStoredCasetaId(casetaId: number | null): Promise<void> {
  if (casetaId === null) {
    await deleteItem(KEYS.casetaId);
    return;
  }
  await setItem(KEYS.casetaId, String(casetaId));
}

export async function clearAuthStorage(): Promise<void> {
  await Promise.all([
    deleteItem(KEYS.access),
    deleteItem(KEYS.refresh),
    deleteItem(KEYS.usuario),
  ]);
}
