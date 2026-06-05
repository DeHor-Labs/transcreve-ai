import { useEffect, useRef, useState } from 'react';
import type { ProgressEvent } from '../api/types';

const STEP_ORDER = ['download', 'audio', 'frames', 'ocr', 'ai', 'persist', 'done'];

export function stepIndex(step: string): number {
  const idx = STEP_ORDER.indexOf(step === 'ai_frame' ? 'ai' : step);
  return idx === -1 ? 0 : idx;
}

export { STEP_ORDER };

interface UseJobEventsResult {
  events: ProgressEvent[];
  latest: ProgressEvent | null;
  done: boolean;
  failed: boolean;
}

export function useJobEvents(
  jobId: string,
  enabled: boolean,
): UseJobEventsResult {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [done, setDone] = useState(false);
  const [failed, setFailed] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const doneRef = useRef(false);
  const failedRef = useRef(false);

  function clearReconnectTimeout() {
    if (reconnectTimeoutRef.current !== null) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }

  function closeCurrentStream() {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }

  useEffect(() => {
    if (!enabled || !jobId) return;

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEvents([]);
    setDone(false);
    setFailed(false);
    doneRef.current = false;
    failedRef.current = false;

    function connect() {
      closeCurrentStream();

      const es = new EventSource(`/api/jobs/${jobId}/events`);
      esRef.current = es;

      es.onmessage = (evt) => {
        try {
          const event: ProgressEvent = JSON.parse(evt.data as string);
          setEvents((prev) => {
            if (prev.some((p) => p.ts === event.ts && p.step === event.step)) {
              return prev;
            }
            return [...prev, event];
          });

          if (event.step === 'done') {
            doneRef.current = true;
            setDone(true);
            clearReconnectTimeout();
            es.close();
          } else if (event.status === 'failed' || event.step === 'failed') {
            failedRef.current = true;
            setFailed(true);
            clearReconnectTimeout();
            es.close();
          }
        } catch (error) {
          if (import.meta.env.DEV) {
            console.warn('Falha ao processar evento SSE', error);
          }
        }
      };

      es.onerror = () => {
        if (doneRef.current || failedRef.current) return;
        clearReconnectTimeout();
        reconnectTimeoutRef.current = setTimeout(() => {
          if (esRef.current?.readyState === EventSource.CLOSED) {
            connect();
          }
        }, 2000);
      };
    }

    connect();

    return () => {
      clearReconnectTimeout();
      closeCurrentStream();
    };
  }, [jobId, enabled]);

  const latest = events.length > 0 ? events[events.length - 1] : null;

  return { events, latest, done, failed };
}
