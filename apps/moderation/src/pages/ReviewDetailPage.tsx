import React, { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { Evaluation, AnswerBook, Exam, User, Question } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';

export function ReviewDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [returnReason, setReturnReason] = useState('');
  const [showReturnModal, setShowReturnModal] = useState(false);
  const [actionError, setActionError] = useState('');

  const { data: evaluation, isLoading, isError } = useQuery<Evaluation>({
    queryKey: ['moderation-detail', id],
    queryFn: async () => {
      const { data } = await apiClient.get(`/moderation/${id}`);
      return data.data;
    },
  });

  const ab = typeof evaluation?.answerBookId === 'object' ? (evaluation.answerBookId as unknown as AnswerBook) : null;
  const exam = ab && typeof ab.examId === 'object' ? (ab.examId as unknown as Exam) : null;
  const examiner = typeof evaluation?.examinerId === 'object' ? (evaluation.examinerId as unknown as User) : null;
  const examId = exam?._id || (typeof ab?.examId === 'string' ? ab.examId : '');

  // Fetch questions for reference
  const { data: questions = [] } = useQuery<Question[]>({
    queryKey: ['exam-questions', examId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/exams/${examId}/questions`);
      return data.data;
    },
    enabled: Boolean(examId),
  });

  const approveMutation = useMutation({
    mutationFn: async () => {
      await apiClient.post(`/moderation/${id}/approve`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['moderation-queue'] });
      queryClient.invalidateQueries({ queryKey: ['moderation-stats'] });
      navigate('/queue');
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || 'Approval failed';
      setActionError(msg);
    },
  });

  const returnMutation = useMutation({
    mutationFn: async (reason: string) => {
      await apiClient.post(`/moderation/${id}/return`, { reason });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['moderation-queue'] });
      queryClient.invalidateQueries({ queryKey: ['moderation-stats'] });
      setShowReturnModal(false);
      navigate('/queue');
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || 'Return failed';
      setActionError(msg);
    },
  });

  if (isLoading) return <div className="state-container"><div className="spinner" /></div>;
  if (isError || !evaluation) {
    return (
      <div className="state-container">
        <div className="state-title">Evaluation Not Found</div>
        <Link to="/queue" className="btn btn-secondary state-action">← Return to Queue</Link>
      </div>
    );
  }

  const canAct = ['SUBMITTED', 'UNDER_REVIEW'].includes(evaluation.status);

  return (
    <div>
      <div className="breadcrumbs">
        <Link to="/queue">Review Queue</Link>
        <span className="breadcrumbs__sep">›</span>
        <span>{ab?.answerBookCode || id}</span>
      </div>

      <div className="page-header" style={{ marginBottom: 'var(--space-6)' }}>
        <div>
          <div className="page-header__eyebrow">Moderation & Quality Center · Script Review</div>
          <h1 className="page-header__title">{exam?.title || 'Evaluation Review'}</h1>
          <p className="page-header__subtitle">
            {exam?.subjectCode} · {exam?.subjectName} · Academic Session: {exam?.academicSession}
          </p>
        </div>
        <div className="page-header__actions">
          <StatusBadge status={evaluation.status} />
        </div>
      </div>

      {actionError && (
        <div
          style={{
            padding: 'var(--space-3)',
            background: 'var(--status-returned-bg)',
            color: 'var(--status-returned-text)',
            borderRadius: 'var(--radius-sm)',
            marginBottom: 'var(--space-6)',
          }}
        >
          ⚠ {actionError}
        </div>
      )}

      {/* THREE-PART STRUCTURE: LEFT (Script Info), CENTER (Evaluation Comparison), RIGHT (Decision Docket) */}
      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr 300px', gap: 'var(--space-6)', alignItems: 'start' }}>
        {/* ============================================================ */}
        {/* LEFT: Script Information */}
        {/* ============================================================ */}
        <div className="folio-card">
          <div className="folio-card__header">
            <span className="folio-card__title">Script Information</span>
          </div>
          <div className="folio-card__body">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div>
                <div className="label-caps">Answer Book Code</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700 }}>
                  {ab?.answerBookCode}
                </div>
              </div>

              <div>
                <div className="label-caps">Student Reference</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{ab?.studentCode}</div>
              </div>

              <div>
                <div className="label-caps">Pages Ingested</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{ab?.pageCount} pages</div>
              </div>

              <div>
                <div className="label-caps">Quality Custody</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{ab?.qualityStatus || 'VERIFIED'}</div>
              </div>

              <div className="divider" style={{ margin: '4px 0' }} />

              <div>
                <div className="label-caps">Accredited Examiner</div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{examiner?.name || '—'}</div>
                <div className="label-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{examiner?.email}</div>
              </div>

              <div>
                <div className="label-caps">Submission Date</div>
                <div className="label-mono" style={{ fontSize: 11 }}>
                  {evaluation.submittedAt ? new Date(evaluation.submittedAt).toLocaleString() : '—'}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ============================================================ */}
        {/* CENTER: Evaluation Comparison */}
        {/* ============================================================ */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
          {/* Examiner Marks Overview */}
          <div className="folio-card">
            <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <span className="folio-card__title">Examiner Marks & Score Formulation</span>
                <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  Awarded by {examiner?.name}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <span className="label-caps" style={{ fontSize: 9 }}>Total Score Awarded</span>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, color: 'var(--parchment-navy)' }}>
                  {evaluation.totalMarks ?? 0}
                  {exam && <span style={{ fontSize: 13, color: 'var(--text-muted)' }}> / {exam.maximumMarks}</span>}
                </div>
              </div>
            </div>

            <div className="folio-card__body">
              {/* Question-level differences & marks */}
              <div className="label-caps" style={{ marginBottom: 8 }}>Question-Level Scoring Breakdown</div>
              {evaluation.questionMarks && evaluation.questionMarks.length > 0 ? (
                <div className="data-table-wrap" style={{ border: 'none', margin: '0 0 var(--space-4) 0' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Question</th>
                        <th>Marks Awarded</th>
                        <th>Marking Status</th>
                        <th>Examiner Comment</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evaluation.questionMarks.map((qm) => {
                        const matchingQ = questions.find((q) => q.questionNumber === qm.questionNumber);
                        return (
                          <tr key={qm.questionNumber}>
                            <td style={{ fontWeight: 600 }}>
                              Q{qm.questionNumber}
                              {matchingQ && <span className="label-mono" style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 4 }}>/{matchingQ.maximumMarks}m</span>}
                            </td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 13 }}>
                              {qm.marks}
                            </td>
                            <td>
                              <span
                                className="label-mono"
                                style={{
                                  fontSize: 10,
                                  padding: '2px 6px',
                                  borderRadius: 2,
                                  background:
                                    qm.status === 'MARKED'
                                      ? 'var(--status-approved-bg)'
                                      : qm.status === 'FLAGGED'
                                      ? 'var(--status-review-bg)'
                                      : 'var(--parchment-border)',
                                  color:
                                    qm.status === 'MARKED'
                                      ? 'var(--status-approved-text)'
                                      : qm.status === 'FLAGGED'
                                      ? 'var(--status-review-text)'
                                      : 'inherit',
                                }}
                              >
                                {qm.status}
                              </span>
                            </td>
                            <td style={{ fontSize: 12, color: qm.comment ? 'inherit' : 'var(--text-muted)' }}>
                              {qm.comment || '—'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="state-container" style={{ padding: 'var(--space-4)' }}>
                  <div className="state-body">No granular per-question marks recorded. Total score: {evaluation.totalMarks ?? 0} marks.</div>
                </div>
              )}

              {/* Examiner Comments */}
              <div style={{ marginTop: 'var(--space-3)' }}>
                <div className="label-caps" style={{ marginBottom: 4 }}>Examiner Concluding Remarks</div>
                <div
                  style={{
                    padding: 'var(--space-3)',
                    background: 'rgba(255,255,255,0.7)',
                    border: '1px solid var(--parchment-border)',
                    borderRadius: 'var(--radius-sm)',
                    fontFamily: 'var(--font-serif)',
                    fontSize: 13,
                    lineHeight: 1.6,
                  }}
                >
                  {evaluation.remarks || 'No general commentary recorded by examiner.'}
                </div>
              </div>
            </div>
          </div>

          {/* AI/Reference Evidence — Future Integration Slot (Strict prompt rule) */}
          <div className="folio-card" style={{ border: '1px dashed var(--parchment-border)', background: 'rgba(14,26,43,0.02)' }}>
            <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="folio-card__title" style={{ color: 'var(--parchment-gold)' }}>
                AI & Reference Evidence
              </span>
              <span className="label-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                INTEGRATION SLOT
              </span>
            </div>
            <div className="folio-card__body">
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>
                AI Analysis: Not yet available.
              </div>
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 12, color: 'var(--text-muted)' }}>
                When AI inference models are connected, this viewport provides machine reference scoring, concept coverage extraction, and anomaly confidence indicators alongside examiner marks.
              </div>
            </div>
          </div>
        </div>

        {/* ============================================================ */}
        {/* RIGHT: Moderator Decision Docket */}
        {/* ============================================================ */}
        <div className="folio-card">
          <div className="folio-card__header">
            <span className="folio-card__title">Moderator Decision</span>
          </div>
          <div className="folio-card__body">
            <div style={{ marginBottom: 'var(--space-4)' }}>
              <div className="label-caps" style={{ marginBottom: 4 }}>Current Review Status</div>
              <StatusBadge status={evaluation.status} />
            </div>

            {canAct ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                <div style={{ padding: 'var(--space-3)', background: 'rgba(14,26,43,0.04)', borderRadius: 'var(--radius-sm)', fontSize: 12 }}>
                  Verify scoring consistency against examination rubrics before committing binding approval.
                </div>

                <button
                  className="btn btn-primary"
                  style={{ width: '100%', justifyContent: 'center' }}
                  disabled={approveMutation.isPending}
                  onClick={() => approveMutation.mutate()}
                >
                  {approveMutation.isPending ? 'Certifying…' : '✓ Approve & Certify Marks'}
                </button>

                <button
                  className="btn btn-secondary"
                  style={{ width: '100%', justifyContent: 'center' }}
                  onClick={() => setShowReturnModal(true)}
                >
                  ↩ Return to Examiner for Revision
                </button>

                <div className="form-hint" style={{ fontSize: 10 }}>
                  Returning evaluation requires a documented justification reason and unlocks the script on the examiner marking workspace.
                </div>
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: 'var(--space-4) 0' }}>
                <div style={{ fontSize: 24, marginBottom: 8 }}>
                  {evaluation.status === 'APPROVED' ? '✓' : '↩'}
                </div>
                <div style={{ fontFamily: 'var(--font-serif)', fontSize: 15, fontWeight: 600 }}>
                  {evaluation.status === 'APPROVED' ? 'Evaluation Certified' : 'Evaluation Remanded'}
                </div>
                <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                  No further moderator action required.
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Return Reason Modal */}
      {showReturnModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowReturnModal(false)}>
          <div className="modal">
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow">Moderation Decision</div>
                <div className="modal__title">Return Evaluation to Examiner</div>
              </div>
              <button className="modal__close" onClick={() => setShowReturnModal(false)}>✕</button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!returnReason.trim()) return;
                returnMutation.mutate(returnReason);
              }}
            >
              <div className="modal__body">
                <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 'var(--space-3)' }}>
                  State the specific marking discrepancy, missing question coverage, or scoring adjustment required.
                </p>
                <div className="form-field">
                  <label className="form-label">Return Justification <span className="required">*</span></label>
                  <textarea
                    className="form-input"
                    rows={4}
                    required
                    placeholder="e.g., Re-examine Question 3 derivation marks; rubric requires demonstration of boundary conditions..."
                    value={returnReason}
                    onChange={(e) => setReturnReason(e.target.value)}
                  />
                </div>
              </div>
              <div className="modal__footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowReturnModal(false)}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!returnReason.trim() || returnMutation.isPending}
                >
                  {returnMutation.isPending ? 'Returning Docket…' : 'Confirm Return'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
