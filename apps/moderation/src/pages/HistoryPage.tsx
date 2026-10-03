import React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '../lib/apiClient';

interface ModerationHistoryItem {
  _id: string;
  status: 'UNDER_REVIEW' | 'APPROVED' | 'RETURNED';
  decision: 'APPROVE' | 'RETURN';
  reason?: string;
  createdAt: string;
  evaluationId?: {
    _id: string;
    totalMarks?: number;
    answerBookId?: {
      _id: string;
      answerBookCode: string;
      studentCode?: string;
      examId?: {
        _id: string;
        title: string;
        subjectCode: string;
        maximumMarks?: number;
      };
    };
    examinerId?: {
      _id: string;
      name: string;
      email: string;
    };
  };
}

export function HistoryPage() {
  const queryClient = useQueryClient();

  const { data: history = [], isLoading, isError } = useQuery<ModerationHistoryItem[]>({
    queryKey: ['moderator-history'],
    queryFn: async () => {
      try {
        const { data } = await apiClient.get('/moderation/history');
        if (data && data.data) return data.data;
      } catch (err: any) {
        // Fallback if remote Render backend doesn't have /history deployed yet
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
              evaluationId: ev,
            }));
          } catch {
            return [];
          }
        }
        throw err;
      }
      return [];
    },
  });

  const totalDecisions = history.length;
  const approvals = history.filter((h) => h.decision === 'APPROVE').length;
  const returns = history.filter((h) => h.decision === 'RETURN').length;

  return (
    <div>
      <div className="page-header" style={{ marginBottom: 'var(--space-6)' }}>
        <div>
          <div className="page-header__eyebrow" style={{ fontSize: 13, letterSpacing: '0.08em', color: 'var(--parchment-gold)' }}>
            MODERATION & QUALITY CENTER · PERSONAL ARCHIVE
          </div>
          <h1 className="page-header__title" style={{ fontSize: 36, fontWeight: 700, margin: '4px 0 6px 0', fontFamily: 'Cambria, serif' }}>
            Moderation Decision History
          </h1>
          <p className="page-header__subtitle" style={{ fontSize: 16, color: 'var(--text-muted)' }}>
            Personal ledger of all binding examination evaluations approved or returned by you.
          </p>
        </div>
        <div className="page-header__actions">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['moderator-history'] })}
            style={{ fontSize: 13 }}
          >
            ↻ Refresh History
          </button>
        </div>
      </div>

      {/* Metric strip */}
      <div className="stat-grid" style={{ marginBottom: 'var(--space-8)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow" style={{ fontSize: 12 }}>TOTAL COMPLETED DECISIONS</div>
          <div className="stat-card__value" style={{ fontSize: 32, fontFamily: 'Cambria, serif' }}>
            {isLoading ? '—' : totalDecisions}
          </div>
          <div className="stat-card__sub" style={{ fontSize: 12 }}>Certified or remanded evaluations</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow" style={{ fontSize: 12 }}>CERTIFIED & APPROVED</div>
          <div className="stat-card__value" style={{ fontSize: 32, fontFamily: 'Cambria, serif', color: 'var(--status-approved-text)' }}>
            {isLoading ? '—' : approvals}
          </div>
          <div className="stat-card__sub" style={{ fontSize: 12 }}>Marks validated and finalized</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow" style={{ fontSize: 12 }}>RETURNED FOR REVISION</div>
          <div className="stat-card__value" style={{ fontSize: 32, fontFamily: 'Cambria, serif', color: returns > 0 ? 'var(--status-returned-text)' : 'inherit' }}>
            {isLoading ? '—' : returns}
          </div>
          <div className="stat-card__sub" style={{ fontSize: 12 }}>Remanded to examiner with reason</div>
        </div>
      </div>

      {/* History Ledger */}
      <div className="folio-card">
        <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="folio-card__title" style={{ fontSize: 18, fontFamily: 'Cambria, serif' }}>Personal Decisions Docket ({history.length})</span>
          <span className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>PERSISTED IN MONGODB</span>
        </div>
        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoading ? (
            <div className="state-container" style={{ padding: 'var(--space-10)' }}>
              <div className="spinner" />
              <div style={{ marginTop: 'var(--space-3)', fontSize: 14 }}>Loading moderation history…</div>
            </div>
          ) : isError ? (
            <div className="state-container" style={{ padding: 'var(--space-8)' }}>
              <div className="state-title" style={{ fontSize: 18 }}>Failed to load decision history</div>
              <button
                className="btn btn-secondary state-action"
                onClick={() => queryClient.invalidateQueries({ queryKey: ['moderator-history'] })}
                style={{ fontSize: 13, marginTop: 'var(--space-3)' }}
              >
                Retry
              </button>
            </div>
          ) : history.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-10)' }}>
              <div className="state-icon" style={{ fontSize: 32 }}>⚖️</div>
              <div className="state-title" style={{ fontSize: 20, fontFamily: 'Cambria, serif', marginTop: 8 }}>
                No moderation history yet.
              </div>
              <div className="state-body" style={{ fontSize: 14, color: 'var(--text-muted)', maxWidth: 440, marginTop: 4 }}>
                When you review and approve or return submitted examination scripts, your authenticated decisions will be permanently chronicled here.
              </div>
              <Link to="/review" className="btn btn-primary state-action" style={{ marginTop: 'var(--space-4)', fontSize: 13 }}>
                Go to Review Queue →
              </Link>
            </div>
          ) : (
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table" style={{ width: '100%', fontSize: 14 }}>
                <thead>
                  <tr>
                    <th style={{ fontSize: 12 }}>Script Code</th>
                    <th style={{ fontSize: 12 }}>Examination</th>
                    <th style={{ fontSize: 12 }}>Examiner</th>
                    <th style={{ fontSize: 12 }}>Decision</th>
                    <th style={{ fontSize: 12 }}>Decision Date</th>
                    <th style={{ fontSize: 12 }}>Reason / Note</th>
                    <th style={{ fontSize: 12, textAlign: 'right' }}>Docket Action</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((item) => {
                    const evalObj = item.evaluationId;
                    const ab = evalObj?.answerBookId;
                    const exam = ab?.examId;
                    const examiner = evalObj?.examinerId;
                    const isApproved = item.decision === 'APPROVE';

                    return (
                      <tr key={item._id}>
                        <td>
                          <span className="data-table__code" style={{ fontSize: 14, fontWeight: 700 }}>
                            {ab?.answerBookCode || '—'}
                          </span>
                          {ab?.studentCode && (
                            <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                              Ref: {ab.studentCode}
                            </div>
                          )}
                        </td>
                        <td>
                          {exam ? (
                            <div>
                              <div style={{ fontSize: 14, fontWeight: 600 }}>{exam.title}</div>
                              <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{exam.subjectCode}</div>
                            </div>
                          ) : '—'}
                        </td>
                        <td>
                          {examiner ? (
                            <div>
                              <div style={{ fontSize: 14 }}>{examiner.name}</div>
                              <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{examiner.email}</div>
                            </div>
                          ) : '—'}
                        </td>
                        <td>
                          <span
                            className="label-mono"
                            style={{
                              fontSize: 11,
                              fontWeight: 700,
                              padding: '3px 8px',
                              borderRadius: 3,
                              background: isApproved ? 'var(--status-approved-bg)' : 'var(--status-returned-bg)',
                              color: isApproved ? 'var(--status-approved-text)' : 'var(--status-returned-text)',
                              border: `1px solid ${isApproved ? 'rgba(46,125,50,0.3)' : 'rgba(180,40,40,0.3)'}`,
                            }}
                          >
                            {isApproved ? '✓ APPROVED' : '↩ RETURNED'}
                          </span>
                        </td>
                        <td className="label-mono" style={{ fontSize: 12 }}>
                          {new Date(item.createdAt).toLocaleString()}
                        </td>
                        <td style={{ fontSize: 13, maxWidth: 280, color: item.reason ? 'inherit' : 'var(--text-muted)' }}>
                          {item.reason || (isApproved ? 'Marks certified and approved' : 'Revision requested')}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          {evalObj?._id ? (
                            <Link to={`/review/${evalObj._id}`} className="btn btn-secondary btn-sm" style={{ fontSize: 12 }}>
                              View Docket
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
