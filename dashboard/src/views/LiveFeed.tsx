import { useState, useCallback } from 'react';
import type { Claim, Credentials } from '../types';
import { useWebSocket } from '../ws';
import ClaimCard from '../components/ClaimCard';

interface Props {
  creds: Credentials;
}

export default function LiveFeed({ creds }: Props) {
  const [claims, setClaims] = useState<Claim[]>([]);

  const onClaim = useCallback((claim: Claim) => {
    setClaims((prev) => [claim, ...prev].slice(0, 200));
  }, []);

  useWebSocket(onClaim, creds);

  function updateClaim(updated: Claim) {
    setClaims((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
  }

  if (claims.length === 0) {
    return (
      <div style={{ color: 'var(--muted)', paddingTop: '40px', textAlign: 'center' }}>
        Waiting for new claims…
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
