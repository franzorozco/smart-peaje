import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';

import {
  AuthCancelledError,
  entrar,
  obtenerMe,
  salir,
  setOnSessionExpired,
  toApiError,
} from './api';
import {
  clearAuthStorage,
  getAccessToken,
  getRefreshToken,
  getStoredCasetaId,
  getStoredUsuario,
  setStoredCasetaId,
} from './storage';
import type { Usuario } from './types';

interface AuthContextValue {
  user: Usuario | null;
  isLoading: boolean;
  isSigningIn: boolean;
  selectedCasetaId: number | null;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  selectCaseta: (casetaId: number | null) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Usuario | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [selectedCasetaId, setSelectedCasetaIdState] = useState<number | null>(null);

  useEffect(() => {
    setOnSessionExpired(() => {
      setUser(null);
    });
    return () => {
      setOnSessionExpired(null);
    };
  }, []);

  useEffect(() => {
    let mounted = true;

    const bootstrap = async () => {
      try {
        const [access, refresh, cachedUser, savedCasetaId] = await Promise.all([
          getAccessToken(),
          getRefreshToken(),
          getStoredUsuario(),
          getStoredCasetaId(),
        ]);

        if (!mounted) {
          return;
        }

        if (savedCasetaId !== null) {
          setSelectedCasetaIdState(savedCasetaId);
        }

        if (access || refresh) {
          try {
            const me = await obtenerMe();
            if (mounted) {
              setUser(me);
            }
          } catch (error) {
            const apiError = toApiError(error);
            if (apiError.status === 0 && cachedUser) {
              if (mounted) {
                setUser(cachedUser);
              }
            } else {
              await clearAuthStorage();
              if (mounted) {
                setUser(null);
              }
            }
          }
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    };

    void bootstrap();

    return () => {
      mounted = false;
    };
  }, []);

  const signInWithGoogle = useCallback(async () => {
    setIsSigningIn(true);
    try {
      const usuario = await entrar();
      setUser(usuario);
    } catch (error) {
      if (error instanceof AuthCancelledError) {
        return;
      }
      throw error;
    } finally {
      setIsSigningIn(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    await salir();
    setUser(null);
  }, []);

  const selectCaseta = useCallback(async (casetaId: number | null) => {
    setSelectedCasetaIdState(casetaId);
    await setStoredCasetaId(casetaId);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isSigningIn,
        selectedCasetaId,
        signInWithGoogle,
        signOut,
        selectCaseta,
      }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth debe usarse dentro de AuthProvider');
  }
  return ctx;
}
