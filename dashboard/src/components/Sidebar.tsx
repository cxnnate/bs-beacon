import type { CSSProperties } from 'react';
import type { Stats } from '../types';

export type View = 'live' | 'trending' | 'analysis' | 'queue' | 'scraper' | 'processor';

interface Props {
  view: View;
  onNavigate: (v: View) => void;
  stats: Stats | null;
}

const NAV: { id: View; label: string }[] = [
  { id: 'live', label: '● Live Feed' },
  { id: 'trending', label: '📈 Trending' },
  { id: 'analysis', label: '🔬 Analysis' },
  { id: 'queue', label: '✅ Queue' },
];

function navStyle(active: boolean): CSSProperties {
  return {
    width: '100%',
    textAlign: 'left',
    padding: '6px 8px',
    borderRadius: '4px',
    border: 'none',
    fontWeight: active ? 700 : 400,
    color: active ? 'var(--accent)' : 'var(--muted)',
    background: active
      ? 'color-mix(in srgb, var(--accent) 10%, transparent)'
      : 'transparent',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    cursor: 'pointer',
  };
}

export default function Sidebar({ view, onNavigate, stats }: Props) {
  return (
    <nav style={{
      width: '180px',
      borderRight: '1px solid var(--border)',
      padding: '12px',
      display: 'flex',
      flexDirection: 'column',
      gap: '2px',
      flexShrink: 0,
      height: '100vh',
      overflow: 'auto',
    }}>
      {NAV.map(({ id, label }) => (
        <button key={id} style={navStyle(view === id)} onClick={() => onNavigate(id)}>
          {id === 'queue' ? (
            <>
              {label}
              {stats && stats.unreviewed > 0 && (
                <span style={{
                  background: 'var(--urgent)',
                  color: '#fff',
                  borderRadius: '9px',
                  padding: '1px 6px',
                  fontSize: '10px',
                }}>
                  {stats.unreviewed}
                </span>
              )}
            </>
          ) : label}
        </button>
      ))}

      <div style={{ borderTop: '1px solid var(--border)', margin: '8px 0' }} />
      <div style={{
        fontSize: '10px',
        color: 'var(--muted)',
        padding: '0 8px 4px',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
      }}>
        Pipeline
      </div>

      {(['scraper', 'processor'] as const).map((svc) => (
        <button
          key={svc}
          style={navStyle(view === svc)}
          onClick={() => onNavigate(svc)}
        >
          🟢 {svc.charAt(0).toUpperCase() + svc.slice(1)}
        </button>
      ))}

      <div style={{
        marginTop: 'auto',
        fontSize: '10px',
        color: 'var(--muted)',
        padding: '8px 8px 0',
      }}>
        {stats ? `${stats.total_claims.toLocaleString()} claims` : '—'}
      </div>
    </nav>
  );
}
