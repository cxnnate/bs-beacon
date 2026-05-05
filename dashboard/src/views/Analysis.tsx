import { useState, useEffect } from 'react';
import {
  ScatterChart, Scatter, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import type { Claim, Credentials } from '../types';
import { getClaims } from '../api';

interface Props {
  creds: Credentials;
}

const COLORS: Record<string, string> = {
  military: '#ef4444',
  politics: '#f97316',
  health: '#22c55e',
  finance: '#eab308',
  technology: '#3b82f6',
  environment: '#10b981',
  science: '#8b5cf6',
  crime: '#ec4899',
  conspiracy: '#f43f5e',
  other: '#6b7280',
};

export default function Analysis({ creds }: Props) {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getClaims({ page_size: 200 }, creds)
      .then((res) => setClaims(res.items))
      .finally(() => setLoading(false));
  }, [creds]);

  if (loading) {
    return (
      <div style={{ color: 'var(--muted)', paddingTop: '40px', textAlign: 'center' }}>
        Loading…
      </div>
    );
  }

  const categories = [...new Set(claims.map((c) => c.category))];
  const byCategory = categories.map((cat) => ({
    name: cat,
    fill: COLORS[cat] ?? '#6b7280',
    data: claims
      .filter((c) => c.category === cat)
      .map((c) => ({ x: c.checkworthy_score, y: c.occurrence_count, text: c.claim_text })),
  }));

  return (
    <div style={{ maxWidth: '900px' }}>
      <h2 style={{ marginBottom: '16px', fontSize: '16px' }}>
        Checkworthiness vs Virality
      </h2>
      <ResponsiveContainer width="100%" height={440}>
        <ScatterChart margin={{ top: 8, right: 24, bottom: 24, left: 8 }}>
          <XAxis
            type="number"
            dataKey="x"
            name="Score"
            domain={[0, 1]}
            tick={{ fontSize: 11, fill: 'var(--muted)' }}
            label={{
              value: 'Checkworthy Score',
              position: 'insideBottom',
              offset: -12,
              fontSize: 11,
              fill: 'var(--muted)',
            }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Occurrences"
            tick={{ fontSize: 11, fill: 'var(--muted)' }}
          />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload as { x: number; y: number; text: string };
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
                    Score: {d.x.toFixed(2)} · ×{d.y}
                  </p>
                </div>
              );
            }}
          />
          <Legend wrapperStyle={{ fontSize: '11px' }} />
          {byCategory.map(({ name, fill, data }) => (
            <Scatter key={name} name={name} data={data} fill={fill} opacity={0.8} />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
