import { useState, type FormEvent, type CSSProperties } from 'react';
import type { Credentials } from '../types';

interface Props {
  onLogin: (creds: Credentials) => void;
  error: boolean;
}

const inputStyle: CSSProperties = {
  padding: '8px 12px',
  background: 'var(--bg)',
  border: '1px solid var(--border)',
  borderRadius: '4px',
  color: 'var(--text)',
  fontSize: '14px',
  width: '100%',
  outline: 'none',
};

export default function Login({ onLogin, error }: Props) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onLogin({ username, password });
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100vh',
    }}>
      <form
        onSubmit={handleSubmit}
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: '8px',
          padding: '32px',
          width: '320px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}
      >
        <h1 style={{ fontSize: '18px', fontWeight: 700 }}>BSBeacon</h1>
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          style={inputStyle}
          autoComplete="username"
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={inputStyle}
          autoComplete="current-password"
        />
        {error && (
          <p style={{ color: 'var(--urgent)', fontSize: '12px' }}>Invalid credentials</p>
        )}
        <button
          type="submit"
          style={{
            background: 'var(--accent)',
            color: '#fff',
            border: 'none',
            padding: '8px',
            borderRadius: '4px',
            fontSize: '14px',
          }}
        >
          Sign in
        </button>
      </form>
    </div>
  );
}
