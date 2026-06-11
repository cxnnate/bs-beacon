import { useState, useCallback, useEffect, useMemo } from 'react';
import type { Claim, Credentials } from '../types';
import { useWebSocket } from '../ws';
import { getClaims } from '../api';
import ClaimCard from '../components/ClaimCard';
import ChannelFilter from '../components/ChannelFilter';
import CollapsibleSection from '../components/CollapsibleSection';

interface Props {
  creds: Credentials;
}

export default function LiveFeed({ creds }: Props) {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedChannels, setSelectedChannels] = useState<Set<string>>(new Set());
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(new Set());

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

  const allTopics = useMemo(() => {
    const seen = new Set<string>();
    for (const c of claims) seen.add(c.topic);
    return Array.from(seen).sort();
  }, [claims]);

  const visibleClaims = useMemo(() => {
    let filtered = claims;
    if (selectedChannels.size > 0) {
      filtered = filtered.filter((c) => c.channels.some((ch) => selectedChannels.has(ch)));
    }
    if (selectedCategories.size > 0) {
      filtered = filtered.filter((c) => selectedCategories.has(c.topic));
    }
    return filtered;
  }, [claims, selectedChannels, selectedCategories]);

  const verified = useMemo(
    () => visibleClaims.filter((c) => c.status === 'verified'),
    [visibleClaims],
  );
  const unverified = useMemo(
    () => visibleClaims.filter((c) => c.status === 'unreviewed' || c.status === 'needs_info'),
    [visibleClaims],
  );
  const debunked = useMemo(
    () => visibleClaims.filter((c) => c.status === 'debunked'),
    [visibleClaims],
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

  const noResults = verified.length === 0 && unverified.length === 0 && debunked.length === 0;

  return (
    <div style={{ maxWidth: '800px' }}>
      <ChannelFilter
        channels={allChannels}
        selected={selectedChannels}
        onChange={setSelectedChannels}
      />
      <ChannelFilter
        channels={allTopics}
        selected={selectedCategories}
        onChange={setSelectedCategories}
        label="Topic:"
      />
      {noResults ? (
        <div style={{ color: 'var(--muted)', paddingTop: '24px', textAlign: 'center' }}>
          No claims from selected filters
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {verified.length > 0 && (
            <CollapsibleSection label="Verified" count={verified.length}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {verified.map((c) => (
                  <ClaimCard key={c.id} claim={c} creds={creds} onUpdate={updateClaim} showActions={false} />
                ))}
              </div>
            </CollapsibleSection>
          )}
          {unverified.length > 0 && (
            <CollapsibleSection label="Unreviewed" count={unverified.length}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {unverified.map((c) => (
                  <ClaimCard key={c.id} claim={c} creds={creds} onUpdate={updateClaim} showActions={false} />
                ))}
              </div>
            </CollapsibleSection>
          )}
          {debunked.length > 0 && (
            <CollapsibleSection label="Debunked" count={debunked.length} defaultOpen={false}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {debunked.map((c) => (
                  <ClaimCard key={c.id} claim={c} creds={creds} onUpdate={updateClaim} showActions={false} />
                ))}
              </div>
            </CollapsibleSection>
          )}
        </div>
      )}
    </div>
  );
}
