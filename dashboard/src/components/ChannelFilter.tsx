import type { CSSProperties } from 'react';

interface Props {
  channels: string[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}

function chipStyle(active: boolean): CSSProperties {
  return {
    fontSize: '11px',
    padding: '3px 10px',
    borderRadius: '12px',
    border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
    background: active
      ? 'color-mix(in srgb, var(--accent) 15%, transparent)'
      : 'var(--surface)',
    color: active ? 'var(--accent)' : 'var(--muted)',
    cursor: 'pointer',
    fontFamily: 'inherit',
    transition: 'color 0.1s, border-color 0.1s, background 0.1s',
  };
}

export default function ChannelFilter({ channels, selected, onChange }: Props) {
  if (channels.length < 2) return null;

  function toggle(ch: string) {
    const next = new Set(selected);
    if (next.has(ch)) next.delete(ch);
    else next.add(ch);
    onChange(next);
  }

  const allActive = selected.size === 0;

  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: '6px',
      marginBottom: '12px',
      alignItems: 'center',
    }}>
      <span style={{ fontSize: '11px', color: 'var(--muted)', marginRight: '2px' }}>
        Channel:
      </span>
      <button style={chipStyle(allActive)} onClick={() => onChange(new Set())}>
        All
      </button>
      {channels.map((ch) => (
        <button key={ch} style={chipStyle(selected.has(ch))} onClick={() => toggle(ch)}>
          {ch}
        </button>
      ))}
    </div>
  );
}
