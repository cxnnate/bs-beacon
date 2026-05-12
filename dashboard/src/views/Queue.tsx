import { useState, useEffect, useMemo } from 'react';
import type { Claim, Credentials, Stats } from '../types';
import { getClaims, getStats } from '../api';
import ClaimCard from '../components/ClaimCard';
import ChannelFilter from '../components/ChannelFilter';
import CollapsibleSection from '../components/CollapsibleSection';

interface Props {
  creds: Credentials;
  onStatsChange: (stats: Stats) => void;
}

const byScore = (a: Claim, b: Claim) =>
  (b.urgency_signals ? 1 : 0) - (a.urgency_signals ? 1 : 0) ||
  b.checkworthy_score - a.checkworthy_score;

export default function Queue({ creds, onStatsChange }: Props) {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedChannels, setSelectedChannels] = useState<Set<string>>(new Set());
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(new Set());

  useEffect(() => {
    getClaims({ page_size: 100 }, creds)
      .then((res) => {
        setClaims(res.items.filter((c) => c.status !== 'reviewed'));
      })
      .finally(() => setLoading(false));
  }, [creds]);

  async function handleUpdate(updated: Claim) {
    if (updated.status === 'reviewed') {
      setClaims((prev) => prev.filter((c) => c.id !== updated.id));
    } else {
      setClaims((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
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

  const allCategories = useMemo(() => {
    const seen = new Set<string>();
    for (const c of claims) seen.add(c.category);
    return Array.from(seen).sort();
  }, [claims]);

  const visibleClaims = useMemo(() => {
    let filtered = claims;
    if (selectedChannels.size > 0) {
      filtered = filtered.filter((c) => c.channels.some((ch) => selectedChannels.has(ch)));
    }
    if (selectedCategories.size > 0) {
      filtered = filtered.filter((c) => selectedCategories.has(c.category));
    }
    return filtered;
  }, [claims, selectedChannels, selectedCategories]);

  const unverified = useMemo(
    () => [...visibleClaims.filter((c) => c.status === 'unreviewed')].sort(byScore),
    [visibleClaims],
  );
  const dismissed = useMemo(
    () => [...visibleClaims.filter((c) => c.status === 'dismissed')].sort(byScore),
    [visibleClaims],
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

  const noResults = unverified.length === 0 && dismissed.length === 0;

  return (
    <div style={{ maxWidth: '800px' }}>
      <ChannelFilter
        channels={allChannels}
        selected={selectedChannels}
        onChange={setSelectedChannels}
      />
      <ChannelFilter
        channels={allCategories}
        selected={selectedCategories}
        onChange={setSelectedCategories}
        label="Category:"
      />
      <p style={{ fontSize: '12px', color: 'var(--muted)', marginBottom: '8px' }}>
        {visibleClaims.length === claims.length
          ? `${claims.length} claims`
          : `${visibleClaims.length} of ${claims.length} claims`}
      </p>
      {noResults ? (
        <div style={{ color: 'var(--muted)', paddingTop: '24px', textAlign: 'center' }}>
          No claims from selected filters
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {unverified.length > 0 && (
            <CollapsibleSection label="Unverified" count={unverified.length}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {unverified.map((c) => (
                  <ClaimCard key={c.id} claim={c} creds={creds} onUpdate={handleUpdate} />
                ))}
              </div>
            </CollapsibleSection>
          )}
          {dismissed.length > 0 && (
            <CollapsibleSection label="Dismissed" count={dismissed.length} defaultOpen={false}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {dismissed.map((c) => (
                  <ClaimCard key={c.id} claim={c} creds={creds} onUpdate={handleUpdate} />
                ))}
              </div>
            </CollapsibleSection>
          )}
        </div>
      )}
    </div>
  );
}
