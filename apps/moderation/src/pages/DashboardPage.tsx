import React, { useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '../lib/apiClient';
import { ModeratorDashboardStats, IntegrityIssue } from '@evalnexa/types';
import { getSocket } from '../lib/socket';

export function DashboardPage() {
  const queryClient = useQueryClient();

  const { data: stats, isLoading: isLoadingStats } = useQuery<ModeratorDashboardStats>({
    queryKey: ['moderation-stats'],
    queryFn: async () => {
      const { data } = await apiClient.get('/moderation/stats');
      return data.data;
    },
    refetchInterval: 15000,
  });

  const { data: integrityIssues = [], isLoading: isLoadingIntegrity } = useQuery<IntegrityIssue[]>({
    queryKey: ['moderation-integrity'],
    queryFn: async () => {
      const { data } = await apiClient.get('/moderation/integrity-checks');
      return data.data;
    },
    refetchInterval: 15000,
  });

  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;
    const handler = () => {
      queryClient.invalidateQueries({ queryKey: ['moderation-stats'] });
      queryClient.invalidateQueries({ queryKey: ['moderation-integrity'] });
    };
    socket.on('evaluation.submitted', handler);
    socket.on('moderation.approved', handler);
    socket.on('moderation.returned', handler);
    return () => {
      socket.off('evaluation.submitted', handler);
      socket.off('moderation.approved', handler);
      socket.off('moderation.returned', handler);
    };
  }, [queryClient]);

  const pendingReview = (stats?.submitted ?? 0) + (stats?.underReview ?? 0);
  const returned = stats?.returned ?? 0;
  const approved = stats?.approved ?? 0;
  const integrityFlags = integrityIssues.length;

  return (
    <div>
      <div className="page-header" style={{ marginBottom: 'var(--space-6)' }}>
        <div>
          <div className="page-header__eyebrow">Moderation & Quality Center · Institutional Governance</div>
          <h1 className="page-header__title">Moderation & Quality Center</h1>
          <p className="page-header__subtitle">
            Review flagged evaluations, marking discrepancies and examination integrity signals.
          </p>
        </div>
        <div className="page-header__actions" style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <Link to="/queue" className="btn btn-primary">
            Open Review Queue ({pendingReview})
          </Link>
          <Link to="/integrity" className="btn btn-secondary">
            Integrity Center ({integrityFlags})
          </Link>
        </div>
      </div>

      {/* TOP METRICS (Required: Pending Review, Returned, Approved, Integrity Flags) */}
      <div className="stat-grid" style={{ marginBottom: 'var(--space-8)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow">PENDING REVIEW</div>
          <div className="stat-card__value" style={{ color: pendingReview > 0 ? 'var(--status-review-text)' : 'inherit' }}>
            {isLoadingStats ? '—' : pendingReview}
          </div>
          <div className="stat-card__sub">Awaiting moderator sign-off</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">RETURNED</div>
          <div className="stat-card__value" style={{ color: returned > 0 ? 'var(--status-returned-text)' : 'inherit' }}>
            {isLoadingStats ? '—' : returned}
          </div>
          <div className="stat-card__sub">Remanded to examiner for revision</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">APPROVED</div>
          <div className="stat-card__value" style={{ color: 'var(--status-approved-text)' }}>
            {isLoadingStats ? '—' : approved}
          </div>
          <div className="stat-card__sub">Certified marks released</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">INTEGRITY FLAGS</div>
          <div className="stat-card__value" style={{ color: integrityFlags > 0 ? 'var(--status-returned-text)' : 'inherit' }}>
            {isLoadingIntegrity ? '—' : integrityFlags}
          </div>
          <div className="stat-card__sub">{integrityFlags === 0 ? 'No integrity discrepancies' : 'Deterministic anomalies found'}</div>
        </div>
      </div>

      {/* QUICK WORKSPACE TILES */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 'var(--space-4)' }}>
        <div className="folio-card">
          <div className="folio-card__header">
            <span className="folio-card__title">Moderation Queue</span>
          </div>
          <div className="folio-card__body">
            <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
              Inspect question-level examiner marks, review examiner commentary, and record binding approval or return decisions.
            </p>
            <Link to="/queue" className="btn btn-secondary btn-sm" style={{ width: '100%', justifyContent: 'center' }}>
              Inspect Queue ({pendingReview})
            </Link>
          </div>
        </div>

        <div className="folio-card">
          <div className="folio-card__header">
            <span className="folio-card__title">Integrity Center</span>
          </div>
          <div className="folio-card__body">
            <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
              Deterministic checks for unchecked questions, arithmetic mismatches, duplicate dockets, and marks exceeding exam maximums.
            </p>
            <Link to="/integrity" className="btn btn-secondary btn-sm" style={{ width: '100%', justifyContent: 'center' }}>
              View Integrity Signals ({integrityFlags})
            </Link>
          </div>
        </div>

        <div className="folio-card">
          <div className="folio-card__header">
            <span className="folio-card__title">Examiner Analytics</span>
          </div>
          <div className="folio-card__body">
            <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
              Monitor operational marking velocity, average scoring curves, and return frequency across the institutional examiner roster.
            </p>
            <Link to="/examiner-analytics" className="btn btn-secondary btn-sm" style={{ width: '100%', justifyContent: 'center' }}>
              View Examiner Roster
            </Link>
          </div>
        </div>

        <div className="folio-card">
          <div className="folio-card__header">
            <span className="folio-card__title">Permanent Audit Ledger</span>
          </div>
          <div className="folio-card__body">
            <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
              Cryptographically timestamped audit trail of all state transitions, mark updates, assignments, and approvals.
            </p>
            <Link to="/audit" className="btn btn-secondary btn-sm" style={{ width: '100%', justifyContent: 'center' }}>
              Open Audit Ledger
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
