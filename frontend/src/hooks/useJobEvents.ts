import { useCallback, useEffect, useRef, useState } from 'react';
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
  const reconnectRef = useRef<() => void>(() => undefined);

  const connect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
    }
    const es = new EventSource(`/api/jobs/${jobId}/events`);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const event: ProgressEvent = JSON.parse(e.data as string);
        setEvents((prev) => {
          // Evita duplicatas pelo ts
          if (prev.some((p) => p.ts === event.ts && p.step === event.step)) {
            return prev;
          }
          return [...prev, event];
        });
        if (event.step === 'done') {
          setDone(true);
          es.close();
        } else if (event.step === 'failed') {
          setFailed(true);
          es.close();
        }
      } catch {
        // ignora parse errors
      }
    };

    es.onerror = () => {
      // Reconecta apos 2s se nao terminou
      if (!done && !failed) {
        setTimeout(() => {
          if (esRef.current?.readyState === EventSource.CLOSED) {
            reconnectRef.current();
          }
        }, 2000);
      }
    };
  }, [jobId, done, failed]);

  useEffect(() => {
    reconnectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    if (!enabled) return;
    connect();
    return () => {
      esRef.current?.close();
    };
  }, [jobId, enabled, connect]);

  const latest = events.length > 0 ? events[events.length - 1] : null;

  return { events, latest, done, failed };
}
