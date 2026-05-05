import type { Claim, Stats, Credentials } from './types';

function authHeader(creds: Credentials): string {
  return 'Basic ' + btoa(`${creds.username}:${creds.password}`);
}

export interface ClaimsParams {
  status?: string;
  category?: string;
  urgent?: boolean;
  search?: string;
  page?: number;
  page_size?: number;
}

export interface ClaimsResponse {
  items: Claim[];
  total: number;
  page: number;
  page_size: number;
}

async function request<T>(url: string, creds: Credentials, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: authHeader(creds),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) throw new Error(String(res.status));
  return res.json() as Promise<T>;
}

export function getClaims(params: ClaimsParams, creds: Credentials): Promise<ClaimsResponse> {
  const qs = new URLSearchParams();
  if (params.status) qs.set('status', params.status);
  if (params.category) qs.set('category', params.category);
  if (params.urgent !== undefined) qs.set('urgent', String(params.urgent));
  if (params.search) qs.set('search', params.search);
  if (params.page) qs.set('page', String(params.page));
  if (params.page_size) qs.set('page_size', String(params.page_size));
  return request<ClaimsResponse>(`/api/claims?${qs}`, creds);
}

export function patchClaim(
  id: number,
  status: 'reviewed' | 'dismissed',
  creds: Credentials,
): Promise<Claim> {
  return request<Claim>(`/api/claims/${id}`, creds, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

export function getStats(creds: Credentials): Promise<Stats> {
  return request<Stats>('/api/stats', creds);
}

export async function getLogs(service: string, creds: Credentials): Promise<string> {
  const res = await fetch(`/api/logs/${service}`, {
    headers: { Authorization: authHeader(creds) },
  });
  if (!res.ok) throw new Error(String(res.status));
  return res.text();
}
