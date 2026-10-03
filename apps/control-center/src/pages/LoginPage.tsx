import React, { useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export function LoginPage() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  if (user) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      await login(email, password);
      navigate('/dashboard', { replace: true });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Login failed';
      setError(msg.includes('400') || msg.includes('401') ? 'Invalid credentials — verify your institutional email and passkey.' : msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-page">

      {/* LEFT — Editorial hero */}
      <div className="login-hero">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
          <div style={{
            fontFamily: '"Cambria"',
            fontSize: '8.5px',
            fontWeight: 700,
            letterSpacing: '0.2em',
            textTransform: 'uppercase',
            color: 'var(--gold)',
          }}>
            EvalNexa Archival Docket // Control Center
          </div>
          <h1 className="login-hero__headline">
            Digital Examination
            <br />
            Engineered for
            <em>Sovereign Accuracy.</em>
          </h1>
          <p className="login-hero__description">
            Orchestrate the complete examination lifecycle — from script
            registration and examiner assignment through on-screen evaluation,
            moderation, and result finalisation — within a single governed workflow.
          </p>
        </div>

        {/* Copperplate rule */}
        <div className="copperplate-rule" />

        <div className="login-hero__meta">
          <div className="login-hero__meta-item">
            <span className="login-hero__meta-label">Platform</span>
            <span className="login-hero__meta-value">EvalNexa v1.0</span>
          </div>
          <div className="login-hero__meta-item">
            <span className="login-hero__meta-label">Interface</span>
            <span className="login-hero__meta-value">Control Center</span>
          </div>
          <div className="login-hero__meta-item">
            <span className="login-hero__meta-label">Access</span>
            <span className="login-hero__meta-value">Administrators Only</span>
          </div>
        </div>
      </div>

      {/* RIGHT — Archival folio panel */}
      <div className="login-panel">
        <div className="login-panel__eyebrow">
          EvalNexa Archival Docket // Folio 01
        </div>
        <h2 className="login-panel__title">Administrative Access</h2>
        <p className="login-panel__subtitle">
          Authorised entry for accredited university administrators only.
        </p>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="form-field">
            <label className="form-label" htmlFor="cc-email">
              1. Institutional Email Address
            </label>
            <input
              id="cc-email"
              type="email"
              className="form-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@institution.edu"
              required
              autoComplete="email"
            />
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="cc-password">
              2. Security Passkey
            </label>
            <input
              id="cc-password"
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••••••"
              required
              autoComplete="current-password"
              style={{ fontFamily: '"Cambria"', letterSpacing: '0.12em', color: 'var(--burgundy)' }}
            />
          </div>

          {error && (
            <div style={{
              padding: '10px 14px',
              background: 'rgba(92,29,36,0.06)',
              border: '1px solid rgba(92,29,36,0.2)',
              fontFamily: '"Cambria"',
              fontSize: '9.5px',
              color: 'var(--burgundy)',
              letterSpacing: '0.04em',
            }}>
              ⚠ {error}
            </div>
          )}

          <button type="submit" className="login-submit" disabled={isLoading}>
            <span>{isLoading ? 'Authorising Syndicate Ledger…' : 'Authorise & Open Control Center'}</span>
            <span className="login-submit__bracket">[↵ ENTER]</span>
          </button>
        </form>
      </div>
    </div>
  );
}
