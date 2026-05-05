import { useEffect, useRef } from 'react';
import type { Claim, Credentials } from './types';

export function useWebSocket(
  onClaim: (claim: Claim) => void,
  creds: Credentials | null,
): void {
  const onClaimRef = useRef(onClaim);
  onClaimRef.current = onClaim;

  useEffect(() => {
    if (!creds) return;
    let ws: WebSocket | null = null;
    let retryDelay = 1000;
    let cancelled = false;

    function connect(): void {
      if (cancelled) return;
      const token = btoa(`${creds!.username}:${creds!.password}`);
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${protocol}//${window.location.host}/ws?token=${token}`);

      ws.onmessage = (e) => {
        try {
          const claim = JSON.parse(e.data as string) as Claim;
          onClaimRef.current(claim);
        } catch {
          // ignore malformed frames
        }
      };

      ws.onopen = () => {
        retryDelay = 1000;
      };

      ws.onclose = () => {
        ws = null;
        if (!cancelled) {
          setTimeout(() => {
            retryDelay = Math.min(retryDelay * 2, 30000);
            connect();
          }, retryDelay);
        }
      };
    }

    connect();
    return () => {
      cancelled = true;
      ws?.close();
    };
  }, [creds]);
}
