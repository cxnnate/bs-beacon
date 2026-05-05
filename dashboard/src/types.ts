export interface Claim {
  id: number;
  claim_text: string;
  category: string;
  temporal: string;
  checkworthy_score: number;
  source_attribution: string | null;
  urgency_signals: boolean;
  occurrence_count: number;
  status: 'unreviewed' | 'reviewed' | 'dismissed';
  first_seen_at: string;
  last_seen_at: string;
  channels: string[];
}

export interface Stats {
  total_claims: number;
  unreviewed: number;
  urgent_unreviewed: number;
  messages_today: number;
  claims_today: number;
}

export interface Credentials {
  username: string;
  password: string;
}
