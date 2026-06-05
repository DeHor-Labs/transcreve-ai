import { useState, useCallback, useRef } from 'react';
import { probeSource } from '../api/sources';
import type { SourceProbeResponse } from '../api/types';
import { isApiError } from '../api/client';

function buildProbeError(error: unknown, fallback: string): string {
  if (isApiError(error)) {
    const body = error.body as { message?: string; error?: string };
    return body?.message ?? body?.error ?? `Falha no probe da fonte (HTTP ${error.status}).`;
  }

  if (error instanceof Error) return error.message;
  return fallback;
}

export function useSourceProbe() {
  const [result, setResult] = useState<SourceProbeResponse | null>(null);
  const [isProbing, setIsProbing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestCounter = useRef(0);

  const probe = useCallback(async (source: string) => {
    const requestId = ++requestCounter.current;
    if (!source.trim()) {
      setResult(null);
      setError(null);
      setIsProbing(false);
      return;
    }

    setError(null);
    setIsProbing(true);

    try {
      const response = await probeSource({ source });
      if (requestId === requestCounter.current) {
        setResult(response);
      }
      return response;
    } catch (err: unknown) {
      if (requestId === requestCounter.current) {
        setResult(null);
        setError(buildProbeError(err, 'Nao foi possivel validar a fonte antes do envio. Tentaremos o processamento normalmente.'));
      }
      return null;
    } finally {
      if (requestId === requestCounter.current) {
        setIsProbing(false);
      }
    }
  }, []);

  const clear = useCallback(() => {
    setResult(null);
    setError(null);
    setIsProbing(false);
    requestCounter.current += 1;
  }, []);

  return { result, isProbing, error, probe, clear };
}
