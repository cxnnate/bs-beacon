import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide,
  type SimulationNodeDatum,
} from 'd3-force';
import type { Credentials, NetworkData, NetworkNode } from '../types';
import { getNetwork, patchClaim } from '../api';

interface Props {
  creds: Credentials;
}

const COLORS: Record<string, string> = {
  military: '#ef4444',
  politics: '#f97316',
  health: '#22c55e',
  finance: '#eab308',
  technology: '#3b82f6',
  environment: '#10b981',
  science: '#8b5cf6',
  crime: '#ec4899',
  other: '#6b7280',
};

interface LayoutNode extends SimulationNodeDatum {
  id: number;
  node: NetworkNode;
  x: number;
  y: number;
}

interface LayoutEdge {
  source: LayoutNode;
  target: LayoutNode;
  relation: 'paraphrase' | 'contradicts';
}

const WIDTH = 1200;
const HEIGHT = 800;

function radius(occurrenceCount: number): number {
  return Math.min(8 + Math.sqrt(occurrenceCount - 1) * 5, 28);
}

function runLayout(data: NetworkData): { nodes: LayoutNode[]; edges: LayoutEdge[] } {
  const nodes: LayoutNode[] = data.nodes.map((n) => ({
    id: n.id, node: n, x: WIDTH / 2, y: HEIGHT / 2,
  }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const links = data.edges
    .filter((e) => byId.has(e.source) && byId.has(e.target))
    .map((e) => ({ source: e.source, target: e.target, relation: e.relation }));

  const sim = forceSimulation(nodes)
    .force('link', forceLink(links.map((l) => ({ ...l }))).id((d) => (d as LayoutNode).id).distance(90))
    .force('charge', forceManyBody().strength(-220))
    .force('center', forceCenter(WIDTH / 2, HEIGHT / 2))
    .force('collide', forceCollide().radius((d) => radius((d as LayoutNode).node.occurrence_count) + 14))
    .stop();
  for (let i = 0; i < 300; i++) sim.tick();

  const edges: LayoutEdge[] = links.map((l) => ({
    source: byId.get(l.source)!,
    target: byId.get(l.target)!,
    relation: l.relation,
  }));
  return { nodes, edges };
}

export default function Network({ creds }: Props) {
  const [data, setData] = useState<NetworkData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState<number | null>(30);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
  const dragging = useRef<{ startX: number; startY: number; baseX: number; baseY: number } | null>(null);

  useEffect(() => {
    setLoading(true);
    getNetwork(days, creds)
      .then((res) => { setData(res); setError(null); })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [creds, days]);

  const layout = useMemo(() => (data ? runLayout(data) : null), [data]);

  const selected = useMemo(
    () => layout?.nodes.find((n) => n.id === selectedId)?.node ?? null,
    [layout, selectedId],
  );

  const contradictionsOfSelected = useMemo(() => {
    if (!layout || selectedId == null) return [];
    return layout.edges
      .filter((e) => e.relation === 'contradicts' && (e.source.id === selectedId || e.target.id === selectedId))
      .map((e) => (e.source.id === selectedId ? e.target.node : e.source.node));
  }, [layout, selectedId]);

  const onWheel = useCallback((e: React.WheelEvent) => {
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    setTransform((t) => ({ ...t, k: Math.max(0.2, Math.min(5, t.k * factor)) }));
  }, []);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    dragging.current = { startX: e.clientX, startY: e.clientY, baseX: transform.x, baseY: transform.y };
  }, [transform]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current) return;
    const d = dragging.current;
    setTransform((t) => ({ ...t, x: d.baseX + (e.clientX - d.startX), y: d.baseY + (e.clientY - d.startY) }));
  }, []);

  const onPointerUp = useCallback(() => { dragging.current = null; }, []);

  async function handleVerdict(status: 'verified' | 'debunked' | 'needs_info') {
    if (!selected || !data) return;
    const prev = data;
    setData({
      ...data,
      nodes: data.nodes.map((n) => (n.id === selected.id ? { ...n, status } : n)),
    });
    try {
      await patchClaim(selected.id, status, creds);
    } catch {
      setData(prev);
    }
  }

  if (loading) {
    return <div style={{ color: 'var(--muted)', paddingTop: '40px', textAlign: 'center' }}>Loading…</div>;
  }
  if (error) {
    return (
      <div style={{ color: 'var(--urgent)', paddingTop: '40px', textAlign: 'center', fontSize: '13px' }}>
        Failed to load network: {error}
      </div>
    );
  }
  if (!layout || layout.nodes.length === 0) {
    return (
      <div style={{ color: 'var(--muted)', paddingTop: '40px', textAlign: 'center' }}>
        No claim relations yet — the network appears as the pipeline links related claims
      </div>
    );
  }

  const topicsPresent = [...new Set(layout.nodes.map((n) => n.node.topic))].sort();

  return (
    <div style={{ display: 'flex', height: '100%', gap: '12px' }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
          <span style={{ fontSize: '11px', color: 'var(--muted)' }}>Window:</span>
          {([['7d', 7], ['30d', 30], ['all', null]] as const).map(([label, value]) => (
            <button
              key={label}
              onClick={() => setDays(value)}
              style={days === value ? { color: 'var(--accent)', borderColor: 'var(--accent)' } : {}}
            >
              {label}
            </button>
          ))}
          <span style={{ marginLeft: 'auto', fontSize: '11px', color: 'var(--muted)' }}>
            {layout.nodes.length} claims · {layout.edges.length} relations
          </span>
        </div>

        <div style={{
          flex: 1, border: '1px solid var(--border)', borderRadius: '4px',
          background: 'var(--surface)', position: 'relative', overflow: 'hidden',
        }}>
          <svg
            width="100%"
            height="100%"
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            style={{ cursor: dragging.current ? 'grabbing' : 'grab', display: 'block' }}
            onWheel={onWheel}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={onPointerUp}
          >
            <g transform={`translate(${transform.x},${transform.y}) scale(${transform.k})`}>
              {layout.edges.map((e, i) => (
                <line
                  key={i}
                  x1={e.source.x} y1={e.source.y} x2={e.target.x} y2={e.target.y}
                  stroke={e.relation === 'contradicts' ? 'var(--urgent)' : '#6b7280'}
                  strokeWidth={1.5}
                  strokeDasharray={e.relation === 'contradicts' ? '6 4' : undefined}
                  opacity={0.7}
                />
              ))}
              {layout.nodes.map((n) => {
                const r = radius(n.node.occurrence_count);
                const isSelected = n.id === selectedId;
                const ring =
                  isSelected ? 'var(--accent)'
                  : n.node.status === 'verified' ? '#22c55e'
                  : n.node.status === 'debunked' ? 'var(--urgent)'
                  : 'var(--bg)';
                return (
                  <g key={n.id} onClick={() => setSelectedId(n.id)} style={{ cursor: 'pointer' }}>
                    <circle
                      cx={n.x} cy={n.y} r={r}
                      fill={COLORS[n.node.topic] ?? COLORS.other}
                      stroke={ring}
                      strokeWidth={isSelected ? 3 : 2}
                    >
                      <title>{n.node.claim_text}</title>
                    </circle>
                    {n.node.occurrence_count > 1 && (
                      <text
                        x={n.x} y={n.y + 3.5}
                        fontSize="9" fontWeight="700" fill="#0d1117" textAnchor="middle"
                        style={{ pointerEvents: 'none' }}
                      >
                        ×{n.node.occurrence_count}
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          </svg>

          <div style={{
            position: 'absolute', bottom: '10px', left: '10px',
            display: 'flex', gap: '14px', alignItems: 'center', flexWrap: 'wrap',
            fontSize: '11px', color: 'var(--muted)',
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: '4px', padding: '6px 10px',
          }}>
            <span>
              <span style={{ display: 'inline-block', width: '16px', borderTop: '2px dashed var(--urgent)', verticalAlign: 'middle', marginRight: '4px' }} />
              contradicts
            </span>
            <span>
              <span style={{ display: 'inline-block', width: '16px', borderTop: '2px solid #6b7280', verticalAlign: 'middle', marginRight: '4px' }} />
              paraphrase
            </span>
            {topicsPresent.map((t) => (
              <span key={t}>
                <span style={{
                  display: 'inline-block', width: '9px', height: '9px', borderRadius: '50%',
                  background: COLORS[t] ?? COLORS.other, verticalAlign: 'middle', marginRight: '4px',
                }} />
                {t}
              </span>
            ))}
            <span>size = times seen</span>
          </div>
        </div>
      </div>

      <div style={{
        width: '300px', flexShrink: 0, background: 'var(--surface)',
        border: '1px solid var(--border)', borderRadius: '4px', padding: '14px',
        display: 'flex', flexDirection: 'column', gap: '10px', alignSelf: 'flex-start',
      }}>
        {!selected ? (
          <p style={{ fontSize: '12px', color: 'var(--muted)' }}>
            Click a node to inspect the claim. Drag to pan, scroll to zoom.
          </p>
        ) : (
          <>
            <div style={{ fontSize: '11px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '1px' }}>
              Claim #{selected.id}
            </div>
            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
              <span style={{
                fontSize: '10px', background: 'var(--border)', color: 'var(--muted)',
                padding: '1px 6px', borderRadius: '3px',
              }}>{selected.topic}</span>
              <span style={{
                fontSize: '10px', color: 'var(--muted)', border: '1px solid var(--border)',
                padding: '1px 6px', borderRadius: '3px',
              }}>{selected.status}</span>
              {selected.occurrence_count > 1 && (
                <span style={{
                  fontSize: '10px', color: 'var(--accent)', border: '1px solid var(--accent)',
                  padding: '1px 6px', borderRadius: '3px', fontWeight: 600,
                }}>seen ×{selected.occurrence_count}</span>
              )}
            </div>
            <p style={{ fontSize: '13px', lineHeight: 1.45 }}>{selected.claim_text}</p>
            {contradictionsOfSelected.length > 0 && (
              <div style={{
                border: '1px solid #7f1d1d', borderLeft: '3px solid var(--urgent)',
                borderRadius: '4px', padding: '8px 10px', fontSize: '12px',
                background: 'rgba(239,68,68,0.06)',
              }}>
                <div style={{ fontSize: '10px', color: 'var(--urgent)', fontWeight: 600, letterSpacing: '0.5px', marginBottom: '4px' }}>
                  ⚠ CONTRADICTED BY {contradictionsOfSelected.length} CLAIM{contradictionsOfSelected.length > 1 ? 'S' : ''}
                </div>
                {contradictionsOfSelected.map((c) => (
                  <div
                    key={c.id}
                    onClick={() => setSelectedId(c.id)}
                    style={{ cursor: 'pointer', marginBottom: '3px' }}
                  >
                    #{c.id} — {c.claim_text}
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: 'flex', gap: '6px' }}>
              <button onClick={() => void handleVerdict('verified')}>✓ Verified</button>
              <button onClick={() => void handleVerdict('debunked')}>✕ Debunked</button>
              <button onClick={() => void handleVerdict('needs_info')}>?</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
