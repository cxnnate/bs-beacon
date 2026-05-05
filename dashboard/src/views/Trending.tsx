import { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer,
} from 'recharts';
import type { Claim, Credentials } from '../types';
import { getClaims } from '../api';

interface Props {
  creds: Credentials;
}

export default function Trending({ creds }: Props) {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getClaims({ page_size: 200 }, creds)
      .then((res) => {
        const sorted = [...res.items]
          .sort((a, b) => b.occurrence_count - a.occurrence_count)
          .slice(0, 20);
        setClaims(sorted);
      })
      .finally(() => setLoading(false));
  }, [creds]);

  if (loading) {
    return (
      <div style={{ color: 'var(--muted)', paddingTop: '40px', textAlign: 'center' }}>
        Loading…
      </div>
    );
  }

  const data = claims.map((c, i) => ({
    name: `#${i + 1}`,
    occurrences: c.occurrence_count,
    text: c.claim_text,
    urgent: c.urgency_signals,
  }));

  return (
    <div style={{ maxWidth: '800px' }}>
      <h2 style={{ marginBottom: '16px', fontSize: '16px' }}>Top 20 — Most Seen Claims</h2>
      <ResponsiveContainer width="100%" height={360}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--muted)' }} />
          <YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }} />
          <Tooltip
            cursor={{ fill: 'rgba(255,255,255,0.04)' }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload as typeof data[0];
              return (
                <div style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: '4px',
                  padding: '8px',
                  maxWidth: '280px',
                  fontSize: '12px',
                }}>
                  <p>{d.text}</p>
                  <p style={{ color: 'var(--muted)', marginTop: '4px' }}>
                    Seen ×{d.occurrences}
                  </p>
                </div>
              );
            }}
          />
          <Bar dataKey="occurrences">
            {data.map((entry, i) => (
              <Cell
                key={i}
                fill={entry.urgent ? 'var(--urgent)' : 'var(--accent)'}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
