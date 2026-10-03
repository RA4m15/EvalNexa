import React, { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AdminDashboardStats } from '@evalnexa/types';
import { useSocketEvents } from '../hooks/useSocketEvents';

export function DashboardPage() {
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery<AdminDashboardStats>({
    queryKey: ['admin-dashboard'],
    queryFn: async () => {
      const { data } = await apiClient.get('/exams/stats/dashboard');
      return data.data;
    },
    refetchInterval: 15000,
  });

  const handlers = useCallback(() => ({
    'exam.created': () => queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] }),
    'exam.updated': () => queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] }),
    'answerbook.created': () => queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] }),
    'answerbook.assigned': () => queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] }),
    'answerbook.status.changed': () => queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] }),
    'evaluation.started': () => queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] }),
    'evaluation.submitted': () => queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] }),
    'moderation.approved': () => queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] }),
    'moderation.returned': () => queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] }),
  }), [queryClient]);
  useSocketEvents(handlers());

  const activeExams = data?.totalExams ?? 0;
  const digitalScripts = data?.totalAnswerBooks ?? 0;
  const inEvaluation = (data?.byStatus.inProgress ?? 0) + (data?.byStatus.assigned ?? 0);
  const pendingReview = (data?.byStatus.submitted ?? 0) + (data?.byStatus.underReview ?? 0);
  const approvedResults = data?.byStatus.approved ?? 0;

  return (
    <div>
      {/* Top Small Institutional Product Header */}
      <div style={{ marginBottom: 'var(--space-2)' }}>
        <div style={{
          fontFamily: 'var(--font-classical)',
          fontSize: '9px',
          fontWeight: 700,
          letterSpacing: '0.24em',
          textTransform: 'uppercase',
          color: 'var(--parchment-gold)',
          lineHeight: 1.4,
        }}>
          EVALNEXA
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: 'var(--text-muted)',
        }}>
          DIGITAL EXAMINATION OPERATIONS
        </div>
      </div>

      {/* Page Heading & Right-side Actions */}
      <div className="page-header" style={{ marginBottom: 'var(--space-6)' }}>
        <div>
          <h1 className="page-header__title" style={{ margin: '4px 0 8px 0' }}>Examination Control Center</h1>
          <p className="page-header__subtitle">
            Monitor examination processing, evaluation progress, integrity and finalization.
          </p>
        </div>
        <div className="page-header__actions" style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <Link to="/exams" className="btn btn-primary">
            + Create Examination
          </Link>
          <Link to="/answer-books" className="btn btn-secondary">
            Register Answer Books
          </Link>
          <Link to="/monitoring" className="btn btn-ghost" style={{ border: '1px solid var(--parchment-border)' }}>
            Open Monitoring →
          </Link>
        </div>
      </div>

      {isError ? (
        <div className="state-container">
          <div className="state-icon">⚠</div>
          <div className="state-title">Registry Telemetry Unavailable</div>
          <div className="state-body">Failed to retrieve examination statistics. Verify backend connectivity.</div>
          <div className="state-action">
            <button className="btn btn-secondary" onClick={() => queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] })}>
              Retry
            </button>
          </div>
        </div>
      ) : (
        <>
          {/* DASHBOARD METRICS: Refined Archival Metric Strip */}
          <div className="stat-grid" style={{ marginBottom: 'var(--space-8)' }}>
            <div className="stat-card">
              <div className="stat-card__eyebrow">ACTIVE EXAMINATIONS</div>
              <div className="stat-card__value">{isLoading ? '—' : activeExams}</div>
              <div className="stat-card__sub">{activeExams === 1 ? '1 examination on record' : `${activeExams} examinations on record`}</div>
            </div>
            <div className="stat-card">
              <div className="stat-card__eyebrow">DIGITAL SCRIPTS</div>
              <div className="stat-card__value">{isLoading ? '—' : digitalScripts}</div>
              <div className="stat-card__sub">Ingested into custody</div>
            </div>
            <div className="stat-card">
              <div className="stat-card__eyebrow">IN EVALUATION</div>
              <div className="stat-card__value" style={{ color: inEvaluation > 0 ? 'var(--status-review-text)' : 'inherit' }}>
                {isLoading ? '—' : inEvaluation}
              </div>
              <div className="stat-card__sub">{data?.byStatus.inProgress ?? 0} active on marking screens</div>
            </div>
            <div className="stat-card">
              <div className="stat-card__eyebrow">PENDING REVIEW</div>
              <div className="stat-card__value" style={{ color: pendingReview > 0 ? 'var(--status-returned-text)' : 'inherit' }}>
                {isLoading ? '—' : pendingReview}
              </div>
              <div className="stat-card__sub">Awaiting moderation clearance</div>
            </div>
          </div>

          {/* Operational Modules Quick Navigation */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 'var(--space-4)' }}>
            <div className="folio-card">
              <div className="folio-card__header">
                <span className="folio-card__title">Examinations & Rubrics</span>
              </div>
              <div className="folio-card__body">
                <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
                  Configure course question papers, define question-by-question scoring rubrics, and toggle evaluation windows.
                </p>
                <Link to="/exams" className="btn btn-secondary btn-sm" style={{ width: '100%', justifyContent: 'center' }}>
                  Manage Examinations ({activeExams})
                </Link>
              </div>
            </div>

            <div className="folio-card">
              <div className="folio-card__header">
                <span className="folio-card__title">Scan & Quality Ingestion</span>
              </div>
              <div className="folio-card__body">
                <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
                  Ingest complete answer book PDFs, run quality integrity checks, and prepare digital booklets for marking.
                </p>
                <Link to="/scan-center" className="btn btn-secondary btn-sm" style={{ width: '100%', justifyContent: 'center' }}>
                  Open Scan & Quality Center
                </Link>
              </div>
            </div>

            <div className="folio-card">
              <div className="folio-card__header">
                <span className="folio-card__title">Examiner Assignment Docket</span>
              </div>
              <div className="folio-card__body">
                <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
                  Distribute digital script stacks to verified examiners and balance marking workloads across departments.
                </p>
                <Link to="/assignments" className="btn btn-secondary btn-sm" style={{ width: '100%', justifyContent: 'center' }}>
                  Assign Script Batches
                </Link>
              </div>
            </div>

            <div className="folio-card">
              <div className="folio-card__header">
                <span className="folio-card__title">Certified Results & Export</span>
              </div>
              <div className="folio-card__body">
                <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
                  Review certified examiner marks post-moderation, compile final institutional rosters, and export registers.
                </p>
                <Link to="/results" className="btn btn-secondary btn-sm" style={{ width: '100%', justifyContent: 'center' }}>
                  Review Results ({approvedResults} Certified)
                </Link>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
