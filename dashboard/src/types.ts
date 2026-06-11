export interface Claim {
  id: number;
  claim_text: string;
  topic: string;
  temporal: string;
  checkworthy_score: number;
  source_attribution: string | null;
  urgency_signals: boolean;
  occurrence_count: number;
  status: 'unreviewed' | 'verified' | 'debunked' | 'needs_info';
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

export interface NetworkNode {
  id: number;
  claim_text: string;
  topic: string;
  status: Claim['status'];
  occurrence_count: number;
  urgency_signals: boolean;
}

export interface NetworkEdge {
  source: number;
  target: number;
  relation: 'paraphrase' | 'contradicts';
}

export interface NetworkData {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
}
