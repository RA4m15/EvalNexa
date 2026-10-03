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

  if (user) { return <Navigate to="/dashboard" replace />; }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try { await login(email, password); navigate('/dashboard', { replace: true }); }
    catch { setError('Invalid credentials — verify your institutional email and passkey.'); }
    finally { setIsLoading(false); }
  };

  return (
    <div className="login-page">
      {/* LEFT — Editorial hero */}
      <div className="login-hero">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
          <div style={{ fontFamily: '"Cambria"', fontSize: '12px', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--gold)' }}>
            EvalNexa Archival Docket // Moderation Center
          </div>
          <h1 className="login-hero__headline">
            Evaluation Integrity,
            <br />
            <em>Immutably Verified.</em>
          </h1>
          <p className="login-hero__description">
            The Moderation Center ensures all submitted evaluations meet institutional
            quality standards before results are finalised. Review, approve, or return
            evaluations with full audit traceability.
          </p>
        </div>

        <div className="copperplate-rule" />

        <div className="login-hero__meta">
          <div className="login-hero__meta-item">
            <span className="login-hero__meta-label">Interface</span>
            <span className="login-hero__meta-value">Moderation Center</span>
          </div>
          <div className="login-hero__meta-item">
            <span className="login-hero__meta-label">Access</span>
            <span className="login-hero__meta-value">Moderators Only</span>
          </div>
        </div>
      </div>

      {/* RIGHT — Archival folio panel */}
      <div className="login-panel">
        <div className="login-panel__eyebrow">EvalNexa Archival Docket // Moderation Portal</div>
        <h2 className="login-panel__title">Moderation Access</h2>
        <p className="login-panel__subtitle">Authorised entry for accredited moderators only.</p>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="form-field">
            <label className="form-label" htmlFor="mod-email">1. Institutional Email</label>
            <input id="mod-email" type="email" className="form-input" value={email}
              onChange={(e) => setEmail(e.target.value)} placeholder="moderator@institution.edu" required />
          </div>
          <div className="form-field">
            <label className="form-label" htmlFor="mod-password">2. Security Passkey</label>
            <input id="mod-password" type="password" className="form-input" value={password}
              onChange={(e) => setPassword(e.target.value)} placeholder="••••••••••••••••" required
              style={{ fontFamily: '"Cambria"', letterSpacing: '0.12em', color: 'var(--burgundy)' }} />
          </div>
          {error && (
            <div style={{ padding: '10px 14px', background: 'rgba(92,29,36,0.06)', border: '1px solid rgba(92,29,36,0.2)', fontFamily: '"Cambria"', fontSize: '13px', color: 'var(--burgundy)' }}>
              ⚠ {error}
            </div>
          )}
          <button type="submit" className="login-submit" disabled={isLoading}>
            <span>{isLoading ? 'Authorising Moderation Folio…' : 'Authorise & Open Moderation Center'}</span>
            <span className="login-submit__bracket">[↵ ENTER]</span>
          </button>
        </form>
      </div>
    </div>
  );
}
