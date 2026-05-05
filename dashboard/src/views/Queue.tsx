import { useState, useEffect, useMemo } from 'react';
import type { Claim, Credentials, Stats } from '../types';
import { getClaims, getStats } from '../api';
import ClaimCard from '../components/ClaimCard';
import ChannelFilter from '../components/ChannelFilter';

interface Props {
  creds: Credentials;
  onStatsChange: (stats: Stats) => void;
}

export default function Queue({ creds, onStatsChange }: Props) {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedChannels, setSelectedChannels] = useState<Set<string>>(new Set());

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

  const allChannels = useMemo(() => {
    const seen = new Set<string>();
    for (const c of claims) {
      for (const ch of c.channels) seen.add(ch);
    }
    return Array.from(seen).sort();
  }, [claims]);

  const visibleClaims = useMemo(() =>
    selectedChannels.size === 0
      ? claims
      : claims.filter((c) => c.channels.some((ch) => selectedChannels.has(ch))),
    [claims, selectedChannels],
  );

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
    <div style={{ maxWidth: '800px' }}>
      <ChannelFilter
        channels={allChannels}
        selected={selectedChannels}
        onChange={setSelectedChannels}
      />
      <p style={{ fontSize: '12px', color: 'var(--muted)', marginBottom: '8px' }}>
        {visibleClaims.length === claims.length
          ? `${claims.length} unreviewed claims`
          : `${visibleClaims.length} of ${claims.length} unreviewed claims`}
      </p>
      {visibleClaims.length === 0 ? (
        <div style={{ color: 'var(--muted)', paddingTop: '24px', textAlign: 'center' }}>
          No unreviewed claims from selected channels
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {visibleClaims.map((c) => (
            <ClaimCard key={c.id} claim={c} creds={creds} onUpdate={handleUpdate} />
          ))}
        </div>
      )}
    </div>
  );
}
