import React, { useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '../lib/apiClient';
import { ModeratorDashboardStats, Evaluation, AnswerBook, Exam, User } from '@evalnexa/types';
import { getSocket } from '../lib/socket';

interface RecentModerationItem {
  _id: string;
  status: 'UNDER_REVIEW' | 'APPROVED' | 'RETURNED';
  decision: 'APPROVE' | 'RETURN';
  reason?: string;
  createdAt: string;
  moderatorId?: { name: string; email: string };
  evaluationId?: {
    _id: string;
    totalMarks?: number;
    answerBookId?: {
      _id: string;
      answerBookCode: string;
      examId?: {
        title: string;
        subjectCode: string;
      };
    };
  };
}

export function DashboardPage() {
  const queryClient = useQueryClient();

  // 1. Primary Metrics from MongoDB
  const { data: stats, isLoading: isLoadingStats } = useQuery<ModeratorDashboardStats>({
    queryKey: ['moderation-stats'],
    queryFn: async () => {
      const { data } = await apiClient.get('/moderation/stats');
      return data.data;
    },
    refetchInterval: 15000,
  });

  // 2. Queue for Next Evaluation to Review
  const { data: queue = [], isLoading: isLoadingQueue } = useQuery<Evaluation[]>({
    queryKey: ['moderation-queue'],
    queryFn: async () => {
      const { data } = await apiClient.get('/moderation');
      return data.data;
    },
    refetchInterval: 15000,
  });

  // 3. Recent Moderation Decisions from MongoDB
  const { data: recentHistory = [], isLoading: isLoadingHistory } = useQuery<RecentModerationItem[]>({
    queryKey: ['moderator-recent-history'],
    queryFn: async () => {
      try {
        const { data } = await apiClient.get('/moderation/history');
        if (data && data.data) return data.data;
      } catch (err: any) {
        if (err?.response?.status === 404) {
          try {
            const [approvedRes, returnedRes] = await Promise.all([
              apiClient.get('/moderation?status=APPROVED'),
              apiClient.get('/moderation?status=RETURNED'),
            ]);
            const combined = [...(approvedRes.data.data || []), ...(returnedRes.data.data || [])];
            return combined.map((ev: any) => ({
              _id: ev._id,
              decision: ev.status === 'APPROVED' ? 'APPROVE' : 'RETURN',
              status: ev.status,
              createdAt: ev.updatedAt || ev.submittedAt,
              reason: ev.remarks,
              moderatorId: { name: 'Institutional Moderator', email: '' },
              evaluationId: ev,
            }));
          } catch {
            return [];
          }
        }
      }
      return [];
    },
    refetchInterval: 15000,
  });

  // Real-time synchronization via Socket.IO
  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;

    const handleUpdate = () => {
      queryClient.invalidateQueries({ queryKey: ['moderation-stats'] });
      queryClient.invalidateQueries({ queryKey: ['moderation-queue'] });
      queryClient.invalidateQueries({ queryKey: ['moderator-recent-history'] });
    };

    socket.on('evaluation.submitted', handleUpdate);
    socket.on('evaluation.updated', handleUpdate);
    socket.on('moderation.approved', handleUpdate);
    socket.on('moderation.returned', handleUpdate);
    socket.on('answerbook.status.changed', handleUpdate);

    return () => {
      socket.off('evaluation.submitted', handleUpdate);
      socket.off('evaluation.updated', handleUpdate);
      socket.off('moderation.approved', handleUpdate);
      socket.off('moderation.returned', handleUpdate);
      socket.off('answerbook.status.changed', handleUpdate);
    };
  }, [queryClient]);

  const pendingReview = stats?.submitted ?? 0;
  const inReview = stats?.underReview ?? 0;
  const returned = stats?.returned ?? 0;
  const approved = stats?.approved ?? 0;

  // Find the next evaluation to review (submitted or under review)
  const nextEvaluation = queue.find(
    (ev) => ev.status === 'SUBMITTED' || ev.status === 'UNDER_REVIEW'
  ) || queue[0];

  const nextAb = nextEvaluation && typeof nextEvaluation.answerBookId === 'object'
    ? (nextEvaluation.answerBookId as unknown as AnswerBook)
    : null;
  const nextExam = nextAb && typeof nextAb.examId === 'object'
    ? (nextAb.examId as unknown as Exam)
    : null;
  const nextExaminer = nextEvaluation && typeof nextEvaluation.examinerId === 'object'
    ? (nextEvaluation.examinerId as unknown as User)
    : null;

  const nextFlags = nextEvaluation?.questionMarks?.filter((q) => q.status === 'FLAGGED').length || 0;

  return (
    <div style={{ maxWidth: 1280, margin: '0 auto' }}>
      {/* ============================================================ */}
      {/* 1. HEADER */}
      {/* ============================================================ */}
      <div className="page-header" style={{ marginBottom: 'var(--space-6)' }}>
        <div>
          <div className="page-header__eyebrow" style={{ fontSize: 13, letterSpacing: '0.08em', color: 'var(--parchment-gold)' }}>
            EVALNEXA · EXAMINATION OPERATIONS · PANEL 3
          </div>
          <h1 className="page-header__title" style={{ fontSize: 42, fontWeight: 700, margin: '6px 0 8px 0', fontFamily: 'Cambria, serif' }}>
            Moderation & Quality Center
          </h1>
          <p className="page-header__subtitle" style={{ fontSize: 18, color: 'var(--text-muted)' }}>
            Review submitted evaluations, verify marking integrity, and approve or return scripts.
          </p>
        </div>
        <div className="page-header__actions" style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <Link to="/review" className="btn btn-primary" style={{ fontSize: 14 }}>
            Open Review Queue ({pendingReview + inReview})
          </Link>
          <Link to="/integrity" className="btn btn-secondary" style={{ fontSize: 14 }}>
            Integrity Checks
          </Link>
        </div>
      </div>

      {/* ============================================================ */}
      {/* 2. MODERATION WORKFLOW INDICATOR */}
      {/* ============================================================ */}
      <div
        className="folio-card"
        style={{
          marginBottom: 'var(--space-6)',
          background: 'rgba(255, 255, 255, 0.55)',
          padding: 'var(--space-3) var(--space-4)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="label-caps" style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--parchment-gold)' }}>
              MODERATION WORKFLOW:
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="label-mono" style={{ fontSize: 13, fontWeight: 700, color: 'var(--parchment-navy)' }}>1. SUBMITTED</span>
              <span style={{ color: 'var(--parchment-border)' }}>→</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="label-mono" style={{ fontSize: 13, fontWeight: 700, color: 'var(--parchment-navy)' }}>2. REVIEW</span>
              <span style={{ color: 'var(--parchment-border)' }}>→</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="label-mono" style={{ fontSize: 13, fontWeight: 700, color: 'var(--parchment-navy)' }}>3. VERIFY</span>
              <span style={{ color: 'var(--parchment-border)' }}>→</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="label-mono" style={{ fontSize: 13, fontWeight: 700, color: 'var(--parchment-navy)' }}>4. DECISION</span>
              <span style={{ color: 'var(--parchment-border)' }}>→</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span
                className="label-mono"
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  padding: '2px 8px',
                  borderRadius: 3,
                  background: 'var(--status-approved-bg)',
                  color: 'var(--status-approved-text)',
                  border: '1px solid rgba(46,125,50,0.3)',
                }}
              >
                APPROVED
              </span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>or</span>
              <span
                className="label-mono"
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  padding: '2px 8px',
                  borderRadius: 3,
                  background: 'var(--status-returned-bg)',
                  color: 'var(--status-returned-text)',
                  border: '1px solid rgba(180,40,40,0.3)',
                }}
              >
                RETURNED
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/* 3. PRIMARY METRICS (PENDING REVIEW, IN REVIEW, RETURNED, APPROVED) */}
      {/* ============================================================ */}
      <div className="stat-grid" style={{ marginBottom: 'var(--space-8)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow" style={{ fontSize: 12 }}>PENDING REVIEW</div>
          <div className="stat-card__value" style={{ fontSize: 36, fontFamily: 'Cambria, serif', color: pendingReview > 0 ? 'var(--status-review-text)' : 'inherit' }}>
            {isLoadingStats ? '—' : pendingReview}
          </div>
          <div className="stat-card__sub" style={{ fontSize: 13 }}>Submitted by examiner</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow" style={{ fontSize: 12 }}>IN REVIEW</div>
          <div className="stat-card__value" style={{ fontSize: 36, fontFamily: 'Cambria, serif', color: inReview > 0 ? 'var(--status-review-text)' : 'inherit' }}>
            {isLoadingStats ? '—' : inReview}
          </div>
          <div className="stat-card__sub" style={{ fontSize: 13 }}>Actively under moderation</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow" style={{ fontSize: 12 }}>RETURNED</div>
          <div className="stat-card__value" style={{ fontSize: 36, fontFamily: 'Cambria, serif', color: returned > 0 ? 'var(--status-returned-text)' : 'inherit' }}>
            {isLoadingStats ? '—' : returned}
          </div>
          <div className="stat-card__sub" style={{ fontSize: 13 }}>Remanded to examiner</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow" style={{ fontSize: 12 }}>APPROVED</div>
          <div className="stat-card__value" style={{ fontSize: 36, fontFamily: 'Cambria, serif', color: 'var(--status-approved-text)' }}>
            {isLoadingStats ? '—' : approved}
          </div>
          <div className="stat-card__sub" style={{ fontSize: 13 }}>Marks certified and final</div>
        </div>
      </div>

      {/* ============================================================ */}
      {/* 4. DOMINANT NEXT EVALUATION TO REVIEW SECTION */}
      {/* ============================================================ */}
      <div className="folio-card" style={{ marginBottom: 'var(--space-8)', border: '2px solid var(--parchment-border)' }}>
        <div
          className="folio-card__header"
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: 'rgba(14,26,43,0.03)',
            padding: 'var(--space-4) var(--space-5)',
          }}
        >
          <div>
            <span className="folio-card__title" style={{ fontSize: 22, fontFamily: 'Cambria, serif', fontWeight: 700 }}>
              NEXT EVALUATION TO REVIEW
            </span>
            <div className="label-mono" style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
              Priority queue docket awaiting moderator certification
            </div>
          </div>
          <span
            className="label-mono"
            style={{
              fontSize: 11,
              fontWeight: 700,
              padding: '4px 10px',
              borderRadius: 3,
              background: nextEvaluation ? 'var(--status-review-bg)' : 'var(--parchment-border)',
              color: nextEvaluation ? 'var(--status-review-text)' : 'var(--text-muted)',
              border: '1px solid var(--parchment-border)',
            }}
          >
            {nextEvaluation ? 'DOCKET READY' : 'QUEUE IDLE'}
          </span>
        </div>

        <div className="folio-card__body" style={{ padding: 'var(--space-6)' }}>
          {isLoadingQueue ? (
            <div className="state-container" style={{ padding: 'var(--space-6)' }}>
              <div className="spinner" />
              <div style={{ marginTop: 'var(--space-3)', fontSize: 14 }}>Loading next pending evaluation…</div>
            </div>
          ) : !nextEvaluation ? (
            <div className="state-container" style={{ padding: 'var(--space-6)' }}>
              <div className="state-icon" style={{ fontSize: 32 }}>✓</div>
              <div className="state-title" style={{ fontSize: 20, fontFamily: 'Cambria, serif' }}>
                No evaluations are currently waiting for moderation.
              </div>
              <div className="state-body" style={{ fontSize: 14, color: 'var(--text-muted)', maxWidth: 440, marginTop: 4 }}>
                When examiners complete and submit marking in their workspace, evaluations will appear here for verification.
              </div>
            </div>
          ) : (
            <div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                  gap: 'var(--space-5)',
                  marginBottom: 'var(--space-6)',
                  background: 'rgba(255,255,255,0.7)',
                  padding: 'var(--space-4)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--parchment-border)',
                }}
              >
                <div>
                  <div className="label-caps" style={{ fontSize: 11, color: 'var(--text-muted)' }}>Script Code</div>
                  <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'Cambria, serif', color: 'var(--parchment-navy)', marginTop: 2 }}>
                    {nextAb?.answerBookCode || '—'}
                  </div>
                  {nextAb?.studentCode && (
                    <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      Student Ref: {nextAb.studentCode}
                    </div>
                  )}
                </div>

                <div>
                  <div className="label-caps" style={{ fontSize: 11, color: 'var(--text-muted)' }}>Examination</div>
                  <div style={{ fontSize: 16, fontWeight: 600, fontFamily: 'Cambria, serif', marginTop: 2 }}>
                    {nextExam?.title || '—'}
                  </div>
                  <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    {nextExam?.subjectCode || '—'}
                  </div>
                </div>

                <div>
                  <div className="label-caps" style={{ fontSize: 11, color: 'var(--text-muted)' }}>Examiner</div>
                  <div style={{ fontSize: 16, fontWeight: 600, marginTop: 2 }}>
                    {nextExaminer?.name || 'Assigned Faculty'}
                  </div>
                  <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    {nextExaminer?.email || '—'}
                  </div>
                </div>

                <div>
                  <div className="label-caps" style={{ fontSize: 11, color: 'var(--text-muted)' }}>Awarded Marks</div>
                  <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'Cambria, serif', color: 'var(--parchment-navy)', marginTop: 2 }}>
                    {nextEvaluation.totalMarks ?? 0}
                    {nextExam?.maximumMarks !== undefined && (
                      <span style={{ fontSize: 14, color: 'var(--text-muted)', fontWeight: 400 }}> / {nextExam.maximumMarks}</span>
                    )}
                  </div>
                </div>

                <div>
                  <div className="label-caps" style={{ fontSize: 11, color: 'var(--text-muted)' }}>Submitted At</div>
                  <div className="label-mono" style={{ fontSize: 12, marginTop: 4 }}>
                    {nextEvaluation.submittedAt ? new Date(nextEvaluation.submittedAt).toLocaleString() : '—'}
                  </div>
                </div>

                <div>
                  <div className="label-caps" style={{ fontSize: 11, color: 'var(--text-muted)' }}>Flags / Status</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
                    <span
                      className="label-mono"
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        padding: '2px 6px',
                        borderRadius: 2,
                        background: nextFlags > 0 ? 'var(--status-returned-bg)' : 'var(--parchment-border)',
                        color: nextFlags > 0 ? 'var(--status-returned-text)' : 'var(--text-muted)',
                      }}
                    >
                      {nextFlags} {nextFlags === 1 ? 'FLAG' : 'FLAGS'}
                    </span>
                    <span
                      className="label-mono"
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        padding: '2px 6px',
                        borderRadius: 2,
                        background: 'var(--status-review-bg)',
                        color: 'var(--status-review-text)',
                      }}
                    >
                      {nextEvaluation.status}
                    </span>
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)' }}>
                <Link to="/review" className="btn btn-secondary" style={{ fontSize: 14, padding: '10px 18px' }}>
                  View Full Queue ({queue.length})
                </Link>
                <Link
                  to={`/review/${nextEvaluation._id}`}
                  className="btn btn-primary"
                  style={{ fontSize: 15, padding: '10px 24px', fontWeight: 700, fontFamily: 'Cambria, serif' }}
                >
                  OPEN REVIEW DESK →
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ============================================================ */}
      {/* 5. RECENT MODERATION (SMALL REAL LIST) */}
      {/* ============================================================ */}
      <div className="folio-card">
        <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="folio-card__title" style={{ fontSize: 18, fontFamily: 'Cambria, serif' }}>
              Recent Moderation Decisions
            </span>
            <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              Real-time audit records from institutional MongoDB
            </div>
          </div>
          <Link to="/history" className="btn btn-secondary btn-sm" style={{ fontSize: 12 }}>
            View Full History →
          </Link>
        </div>

        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoadingHistory ? (
            <div className="state-container" style={{ padding: 'var(--space-6)' }}>
              <div className="spinner" />
            </div>
          ) : recentHistory.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-6)' }}>
              <div className="state-body" style={{ fontSize: 14 }}>
                No completed moderation decisions recorded yet.
              </div>
            </div>
          ) : (
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table" style={{ width: '100%', fontSize: 14 }}>
                <thead>
                  <tr>
                    <th style={{ fontSize: 12 }}>Script</th>
                    <th style={{ fontSize: 12 }}>Decision</th>
                    <th style={{ fontSize: 12 }}>Moderator</th>
                    <th style={{ fontSize: 12 }}>Time</th>
                    <th style={{ fontSize: 12, textAlign: 'right' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {recentHistory.slice(0, 5).map((item) => {
                    const isApproved = item.decision === 'APPROVE';
                    const abCode = item.evaluationId?.answerBookId?.answerBookCode || '—';
                    const evalId = item.evaluationId?._id;

                    return (
                      <tr key={item._id}>
                        <td>
                          <span className="data-table__code" style={{ fontSize: 13, fontWeight: 700 }}>
                            {abCode}
                          </span>
                        </td>
                        <td>
                          <span
                            className="label-mono"
                            style={{
                              fontSize: 10,
                              fontWeight: 700,
                              padding: '2px 6px',
                              borderRadius: 2,
                              background: isApproved ? 'var(--status-approved-bg)' : 'var(--status-returned-bg)',
                              color: isApproved ? 'var(--status-approved-text)' : 'var(--status-returned-text)',
                            }}
                          >
                            {isApproved ? '✓ APPROVED' : '↩ RETURNED'}
                          </span>
                        </td>
                        <td style={{ fontSize: 13 }}>
                          {item.moderatorId?.name || 'Moderator'}
                        </td>
                        <td className="label-mono" style={{ fontSize: 12 }}>
                          {new Date(item.createdAt).toLocaleTimeString()} · {new Date(item.createdAt).toLocaleDateString()}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          {evalId ? (
                            <Link to={`/review/${evalId}`} className="btn btn-secondary btn-sm" style={{ fontSize: 12 }}>
                              Open Docket
                            </Link>
                          ) : (
                            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
