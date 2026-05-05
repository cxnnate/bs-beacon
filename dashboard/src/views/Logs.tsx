import { useState, useEffect, useRef } from 'react';
import type { Credentials } from '../types';
import { getLogs } from '../api';

interface Props {
  service: 'scraper' | 'processor';
  creds: Credentials;
}

export default function Logs({ service, creds }: Props) {
  const [text, setText] = useState('');
  const [healthy, setHealthy] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;

    async function poll() {
      try {
        const logs = await getLogs(service, creds);
        if (active) {
          setText(logs);
          setHealthy(true);
        }
      } catch {
        if (active) setHealthy(false);
      }
    }

    void poll();
    const id = setInterval(() => void poll(), 10_000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [service, creds]);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [text]);

  return (
    <div>
      <div style={{ marginBottom: '8px', fontSize: '12px', color: 'var(--muted)' }}>
        bsbeacon-{service} — last 30 lines{' '}
        <span style={{ color: healthy ? '#22c55e' : 'var(--urgent)' }}>
          {healthy ? '●' : '● error'}
        </span>
      </div>
      <div
        ref={containerRef}
        style={{
          background: '#0d1117',
          border: '1px solid var(--border)',
          borderRadius: '4px',
          padding: '12px',
          fontFamily: 'var(--font-mono)',
          fontSize: '12px',
          color: '#7ee787',
          lineHeight: 1.7,
          height: 'calc(100vh - 80px)',
          overflowY: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
        }}
      >
        {text || 'No logs yet…'}
      </div>
    </div>
  );
}
