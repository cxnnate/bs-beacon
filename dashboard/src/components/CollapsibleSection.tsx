import { useState } from 'react';
import type { ReactNode } from 'react';

interface Props {
  label: string;
  count: number;
  children: ReactNode;
  defaultOpen?: boolean;
}

export default function CollapsibleSection({ label, count, children, defaultOpen = true }: Props) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          fontSize: '11px',
          color: 'var(--muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          padding: '4px 0',
          borderTop: 'none',
          borderLeft: 'none',
          borderRight: 'none',
          borderBottom: '1px solid var(--border)',
          marginBottom: '8px',
          background: 'none',
          cursor: 'pointer',
          fontFamily: 'inherit',
          textAlign: 'left',
        }}
      >
        <span style={{ fontSize: '9px', opacity: 0.7, lineHeight: 1 }}>
          {open ? '▾' : '▸'}
        </span>
        {label}{' '}
        <span style={{ opacity: 0.6 }}>({count})</span>
      </button>
      {open && children}
    </div>
  );
}
