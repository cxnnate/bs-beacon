import type { Claim, Credentials } from '../types';
import { patchClaim } from '../api';

interface Props {
  claim: Claim;
  creds: Credentials;
  onUpdate: (updated: Claim) => void;
}

function relativeTime(dateStr: string): string {
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function ClaimCard({ claim, creds, onUpdate }: Props) {
  const channel = claim.channels[0] ?? 'Unknown';

  async function handleAction(status: 'reviewed' | 'dismissed') {
    onUpdate({ ...claim, status });  // optimistic
    try {
      onUpdate(await patchClaim(claim.id, status, creds));
    } catch {
      onUpdate(claim);  // revert
    }
  }

  return (
    <div style={{
      padding: '12px',
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderLeft: claim.urgency_signals ? '3px solid var(--urgent)' : '1px solid var(--border)',
      borderRadius: '4px',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px',
      }}>
        {claim.urgency_signals ? (
          <span style={{
            fontSize: '10px', background: 'var(--urgent)', color: '#fff',
            padding: '1px 6px', borderRadius: '3px', fontWeight: 600,
          }}>URGENT</span>
        ) : (
          <span style={{
            fontSize: '10px', background: 'var(--border)', color: 'var(--muted)',
            padding: '1px 6px', borderRadius: '3px',
          }}>{claim.category}</span>
        )}
        <span style={{ fontSize: '11px', color: 'var(--muted)' }}>{claim.temporal}</span>
        <span style={{ marginLeft: 'auto', fontSize: '11px', color: 'var(--muted)' }}>
          📡 {channel} · {relativeTime(claim.last_seen_at)}
        </span>
      </div>

      <p style={{ fontSize: '13px', marginBottom: '8px', lineHeight: 1.4 }}>
        {claim.claim_text}
      </p>

      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
        <button onClick={() => void handleAction('reviewed')}>✓ Reviewed</button>
        <button onClick={() => void handleAction('dismissed')}>✕ Dismiss</button>
        <span style={{ marginLeft: 'auto', fontSize: '11px', color: 'var(--muted)' }}>
          score: {claim.checkworthy_score.toFixed(2)} · ×{claim.occurrence_count}
        </span>
      </div>
    </div>
  );
}
