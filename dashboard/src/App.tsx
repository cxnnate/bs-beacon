import { useState, useEffect, useCallback } from 'react';
import type { Credentials, Stats } from './types';
import { getStats } from './api';
import Login from './components/Login';
import Sidebar, { type View } from './components/Sidebar';
import LiveFeed from './views/LiveFeed';
import Trending from './views/Trending';
import Analysis from './views/Analysis';
import Queue from './views/Queue';
import Network from './views/Network';
import Logs from './views/Logs';

function BeaconIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="11" cy="11" r="3" fill="#58a6ff" />
      <circle cx="11" cy="11" r="6.5" stroke="#58a6ff" strokeWidth="1.5" opacity="0.55" />
      <circle cx="11" cy="11" r="10" stroke="#58a6ff" strokeWidth="1" opacity="0.22" />
    </svg>
  );
}

export default function App() {
  const [creds, setCreds] = useState<Credentials | null>(null);
  const [view, setView] = useState<View>('live');
  const [stats, setStats] = useState<Stats | null>(null);
  const [loginError, setLoginError] = useState(false);

  const handleLogin = useCallback(async (c: Credentials) => {
    try {
      const s = await getStats(c);
      setCreds(c);
      setStats(s);
      setLoginError(false);
    } catch {
      setLoginError(true);
    }
  }, []);

  useEffect(() => {
    if (!creds) return;
    const id = setInterval(async () => {
      try {
        setStats(await getStats(creds));
      } catch { /* ignore */ }
    }, 30_000);
    return () => clearInterval(id);
  }, [creds]);

  if (!creds) return <Login onLogin={handleLogin} error={loginError} />;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <header style={{
        height: '48px',
        background: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 16px',
        gap: '10px',
        flexShrink: 0,
      }}>
        <BeaconIcon />
        <span style={{ fontWeight: 700, fontSize: '15px', letterSpacing: '-0.01em' }}>
          BSBeacon
        </span>
      </header>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar view={view} onNavigate={setView} stats={stats} />
        <main style={{ flex: 1, overflow: 'auto', padding: '16px' }}>
          {view === 'live' && <LiveFeed creds={creds} />}
          {view === 'trending' && <Trending creds={creds} />}
          {view === 'analysis' && <Analysis creds={creds} />}
          {view === 'queue' && <Queue creds={creds} onStatsChange={setStats} />}
          {view === 'network' && <Network creds={creds} />}
          {view === 'scraper' && <Logs service="scraper" creds={creds} />}
          {view === 'processor' && <Logs service="processor" creds={creds} />}
        </main>
      </div>
    </div>
  );
}
