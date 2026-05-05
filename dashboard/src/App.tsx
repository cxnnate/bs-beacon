import { useState, useEffect } from 'react';
import type { Credentials, Stats } from './types';
import { getStats } from './api';
import Login from './components/Login';
import Sidebar, { type View } from './components/Sidebar';
import LiveFeed from './views/LiveFeed';
import Trending from './views/Trending';
import Analysis from './views/Analysis';
import Queue from './views/Queue';
import Logs from './views/Logs';

export default function App() {
  const [creds, setCreds] = useState<Credentials | null>(null);
  const [view, setView] = useState<View>('live');
  const [stats, setStats] = useState<Stats | null>(null);
  const [loginError, setLoginError] = useState(false);

  async function handleLogin(c: Credentials) {
    try {
      const s = await getStats(c);
      setCreds(c);
      setStats(s);
      setLoginError(false);
    } catch {
      setLoginError(true);
    }
  }

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
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar view={view} onNavigate={setView} stats={stats} />
      <main style={{ flex: 1, overflow: 'auto', padding: '16px' }}>
        {view === 'live' && <LiveFeed creds={creds} />}
        {view === 'trending' && <Trending creds={creds} />}
        {view === 'analysis' && <Analysis creds={creds} />}
        {view === 'queue' && <Queue creds={creds} onStatsChange={setStats} />}
        {view === 'scraper' && <Logs service="scraper" creds={creds} />}
        {view === 'processor' && <Logs service="processor" creds={creds} />}
      </main>
    </div>
  );
}
