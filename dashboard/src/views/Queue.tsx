import { useState, useEffect } from 'react';
import type { Claim, Credentials, Stats } from '../types';
import { getClaims, getStats } from '../api';
import ClaimCard from '../components/ClaimCard';

interface Props {
  creds: Credentials;
  onStatsChange: (stats: Stats) => void;
}

export default function Queue({ creds, onStatsChange }: Props) {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getClaims({ status: 'unreviewed', page_size: 100 }, creds)
      .then((res) => {
        const sorted = [...res.items].sort(
          (a, b) =>
            (b.urgency_signals ? 1 : 0) - (a.urgency_signals ? 1 : 0) ||
            b.checkworthy_score - a.checkworthy_score,
        );
        setClaims(sorted);
      })
      .finally(() => setLoading(false));
  }, [creds]);

  async function handleUpdate(updated: Claim) {
    if (updated.status !== 'unreviewed') {
      setClaims((prev) => prev.filter((c) => c.id !== updated.id));
    }
    try {
      onStatsChange(await getStats(creds));
    } catch { /* ignore */ }
  }

  if (loading) {
    return (
      <div style={{ color: 'var(--muted)', paddingTop: '40px', textAlign: 'center' }}>
        Loading…
      </div>
    );
  }
  if (claims.length === 0) {
    return (
      <div style={{ color: 'var(--muted)', paddingTop: '40px', textAlign: 'center' }}>
        Queue is empty
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '800px' }}>
      <p style={{ fontSize: '12px', color: 'var(--muted)', marginBottom: '4px' }}>
        {claims.length} unreviewed claims
      </p>
      {claims.map((c) => (
        <ClaimCard key={c.id} claim={c} creds={creds} onUpdate={handleUpdate} />
      ))}
    </div>
  );
}
