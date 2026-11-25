import { useCallback, useEffect, useRef, useState } from 'react';

import { listarCasetas, toApiError } from './api';
import { useAuth } from './auth-context';
import type { Caseta } from './types';

export function useCasetas() {
  const { selectedCasetaId, selectCaseta } = useAuth();
  const [casetas, setCasetas] = useState<Caseta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const selectedCasetaIdRef = useRef(selectedCasetaId);
  useEffect(() => {
    selectedCasetaIdRef.current = selectedCasetaId;
  }, [selectedCasetaId]);

  const applyCasetas = useCallback(
    async (list: Caseta[]) => {
      setCasetas(list);
      setError(null);
      const currentId = selectedCasetaIdRef.current;
      if (list.length > 0 && (currentId === null || !list.some((c) => c.id === currentId))) {
        await selectCaseta(list[0].id);
      }
    },
    [selectCaseta]
  );

  useEffect(() => {
    let active = true;

    const init = async () => {
      try {
        const list = await listarCasetas();
        if (!active) {
          return;
        }
        await applyCasetas(list);
      } catch (err) {
        if (active) {
          setError(toApiError(err, 'No se pudieron cargar las casetas').message);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void init();

    return () => {
      active = false;
    };
  }, [applyCasetas]);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await listarCasetas();
      await applyCasetas(list);
    } catch (err) {
      setError(toApiError(err, 'No se pudieron cargar las casetas').message);
    } finally {
      setLoading(false);
    }
  }, [applyCasetas]);

  const selectedCaseta = casetas.find((c) => c.id === selectedCasetaId) ?? null;

  return {
    casetas,
    selectedCasetaId,
    selectedCaseta,
    selectCaseta,
    loading,
    error,
    reload,
  };
}
