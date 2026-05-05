import { useState, useCallback, useEffect, useMemo } from 'react';
import type { Claim, Credentials } from '../types';
import { useWebSocket } from '../ws';
import { getClaims } from '../api';
import ClaimCard from '../components/ClaimCard';
import ChannelFilter from '../components/ChannelFilter';

interface Props {
  creds: Credentials;
}

export default function LiveFeed({ creds }: Props) {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedChannels, setSelectedChannels] = useState<Set<string>>(new Set());

  useEffect(() => {
    getClaims({ page_size: 50 }, creds)
      .then((res) => { setClaims(res.items); setError(null); })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [creds]);

  const onClaim = useCallback((claim: Claim) => {
    setClaims((prev) => {
      if (prev.some((c) => c.id === claim.id)) return prev;
      return [claim, ...prev].slice(0, 200);
    });
  }, []);

  useWebSocket(onClaim, creds);

  function updateClaim(updated: Claim) {
    setClaims((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
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

  if (error) {
    return (
      <div style={{ color: 'var(--urgent)', paddingTop: '40px', textAlign: 'center', fontSize: '13px' }}>
        Failed to load claims: {error}
      </div>
    );
  }

  if (claims.length === 0) {
    return (
      <div style={{ color: 'var(--muted)', paddingTop: '40px', textAlign: 'center' }}>
        No claims yet
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
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {visibleClaims.length === 0 ? (
          <div style={{ color: 'var(--muted)', paddingTop: '24px', textAlign: 'center' }}>
            No claims from selected channels
          </div>
        ) : (
          visibleClaims.map((c) => (
            <ClaimCard key={c.id} claim={c} creds={creds} onUpdate={updateClaim} />
          ))
        )}
      </div>
    </div>
  );
}
