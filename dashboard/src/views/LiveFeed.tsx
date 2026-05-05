import { useState, useCallback, useEffect } from 'react';
import type { Claim, Credentials } from '../types';
import { useWebSocket } from '../ws';
import { getClaims } from '../api';
import ClaimCard from '../components/ClaimCard';

interface Props {
  creds: Credentials;
}

export default function LiveFeed({ creds }: Props) {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getClaims({ page_size: 50 }, creds)
      .then((res) => setClaims(res.items))
      .catch(() => {})
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
        No claims yet
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '800px' }}>
      {claims.map((c) => (
        <ClaimCard key={c.id} claim={c} creds={creds} onUpdate={updateClaim} />
      ))}
    </div>
  );
}
