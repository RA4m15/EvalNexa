import React, { useState, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { Evaluation, Exam, AnswerBook, User, Result } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';
import { useSocketEvents } from '../hooks/useSocketEvents';

export function ResultsPage() {
  const queryClient = useQueryClient();
  const [selectedExamId, setSelectedExamId] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('FINALIZED'); // Default to certified finalized records
  const [actionError, setActionError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // 1. Fetch real Certified Results from MongoDB /api/results
  const { data: results = [], isLoading: isLoadingResults } = useQuery<Result[]>({
    queryKey: ['results-records', selectedExamId],
    queryFn: async () => {
      const { data } = await apiClient.get('/results', {
        params: selectedExamId ? { examId: selectedExamId } : undefined,
      });
      return data.data;
    },
  });

  // 2. Fetch real Answer Books for accurate total script counts & pipeline tracking
  const { data: answerBooks = [], isLoading: isLoadingBooks } = useQuery<AnswerBook[]>({
    queryKey: ['results-answerbooks'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books');
      return data.data;
    },
  });

  // 3. Fetch real Evaluations from MongoDB
  const { data: evaluations = [], isLoading: isLoadingEvals } = useQuery<Evaluation[]>({
    queryKey: ['results-evaluations'],
    queryFn: async () => {
      const { data } = await apiClient.get('/evaluations');
      return data.data;
    },
  });

  // 4. Fetch real Exams
  const { data: exams = [] } = useQuery<Exam[]>({
    queryKey: ['results-exams'],
    queryFn: async () => {
      const { data } = await apiClient.get('/exams');
      return data.data;
    },
  });

  // Live Socket.IO invalidation
  const handlers = useCallback(() => ({
    'result.finalized': () => {
      queryClient.invalidateQueries({ queryKey: ['results-records'] });
      queryClient.invalidateQueries({ queryKey: ['results-evaluations'] });
      queryClient.invalidateQueries({ queryKey: ['results-answerbooks'] });
    },
    'result.updated': () => {
      queryClient.invalidateQueries({ queryKey: ['results-records'] });
      queryClient.invalidateQueries({ queryKey: ['results-evaluations'] });
      queryClient.invalidateQueries({ queryKey: ['results-answerbooks'] });
    },
    'evaluation.submitted': () => {
      queryClient.invalidateQueries({ queryKey: ['results-evaluations'] });
      queryClient.invalidateQueries({ queryKey: ['results-answerbooks'] });
    },
    'moderation.approved': () => {
      queryClient.invalidateQueries({ queryKey: ['results-records'] });
      queryClient.invalidateQueries({ queryKey: ['results-evaluations'] });
      queryClient.invalidateQueries({ queryKey: ['results-answerbooks'] });
    },
    'moderation.returned': () => {
      queryClient.invalidateQueries({ queryKey: ['results-evaluations'] });
      queryClient.invalidateQueries({ queryKey: ['results-answerbooks'] });
    },
    'answerbook.status.changed': () => {
      queryClient.invalidateQueries({ queryKey: ['results-answerbooks'] });
      queryClient.invalidateQueries({ queryKey: ['results-evaluations'] });
      queryClient.invalidateQueries({ queryKey: ['results-records'] });
    },
  }), [queryClient]);
  useSocketEvents(handlers());

  // Filter answer books by selected exam
  const examScopedBooks = useMemo(() => {
    return selectedExamId
      ? answerBooks.filter((b) => {
          const eid = typeof b.examId === 'object' ? (b.examId as any)?._id : b.examId;
          return eid === selectedExamId;
        })
      : answerBooks;
  }, [answerBooks, selectedExamId]);

  // Filter evaluations by selected exam
  const examScopedEvals = useMemo(() => {
    return selectedExamId
      ? evaluations.filter((ev) => {
          const ab = ev.answerBookId as unknown as AnswerBook;
          const eid = typeof ab?.examId === 'object' ? (ab.examId as any)?._id : ab?.examId;
          return eid === selectedExamId;
        })
      : evaluations;
  }, [evaluations, selectedExamId]);

  // Filter certified results by selected exam
  const examScopedResults = useMemo(() => {
    return selectedExamId
      ? results.filter((r) => {
          const eid = typeof r.examId === 'object' ? (r.examId as any)?._id : r.examId;
          return eid === selectedExamId;
        })
      : results;
  }, [results, selectedExamId]);

  // Finalization Mutation: POST /api/results/:evaluationId/finalize
  const finalizeMutation = useMutation({
    mutationFn: async (evaluationId: string) => {
      const { data } = await apiClient.post(`/results/${evaluationId}/finalize`);
      return data.data;
    },
    onSuccess: () => {
      setSuccessMsg('Result successfully verified and certified into official institutional register.');
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ['results-records'] });
      queryClient.invalidateQueries({ queryKey: ['results-evaluations'] });
      queryClient.invalidateQueries({ queryKey: ['results-answerbooks'] });
    },
    onError: (err: any) => {
      const msg = err.response?.data?.message || 'Failed to finalize examination result.';
      setActionError(msg);
      setSuccessMsg(null);
    },
  });

  // FINAL RESULT PIPELINE (Evaluated, Pending Moderation, Approved, Finalized)
  const evaluatedCount = examScopedBooks.filter((b) =>
    ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'FINALIZED'].includes(b.status)
  ).length;
  const pendingModerationCount = examScopedBooks.filter((b) =>
    ['SUBMITTED', 'UNDER_REVIEW'].includes(b.status)
  ).length;
  const approvedCount = examScopedBooks.filter((b) => b.status === 'APPROVED').length;
  const finalizedCount = examScopedResults.length > 0 
    ? examScopedResults.length 
    : examScopedBooks.filter((b) => b.status === 'FINALIZED').length;

  // Evaluations that are approved by moderation but awaiting result finalization
  const approvedAwaitingFinalization = useMemo(() => {
    return examScopedEvals.filter((ev) => {
      const ab = ev.answerBookId as unknown as AnswerBook;
      return ev.status === 'APPROVED' && ab?.status !== 'FINALIZED';
    });
  }, [examScopedEvals]);

  // Real Export CSV
  const handleExportCSV = () => {
    if (examScopedResults.length === 0) {
      alert('No finalized result records available for export.');
      return;
    }

    const headers = [
      'Student Code',
      'Script Code',
      'Subject Code',
      'Examination Title',
      'Accredited Examiner',
      'Marks',
      'Maximum Marks',
      'Percentage',
      'Status',
      'Finalized At',
      'Finalized By',
    ];

    const rows = examScopedResults.map((r) => {
      const ab = typeof r.answerBookId === 'object' ? (r.answerBookId as AnswerBook) : null;
      const exam = typeof r.examId === 'object' ? (r.examId as Exam) : null;
      const examiner = typeof r.examinerId === 'object' ? (r.examinerId as User) : null;
      const certifier = typeof r.finalizedBy === 'object' ? (r.finalizedBy as User) : null;

      return [
        `"${ab?.studentCode || '—'}"`,
        `"${ab?.answerBookCode || '—'}"`,
        `"${exam?.subjectCode || '—'}"`,
        `"${exam?.title || '—'}"`,
        `"${examiner?.name || '—'}"`,
        r.totalMarks,
        r.maximumMarks,
        `"${r.percentage}%"`,
        r.status,
        `"${r.finalizedAt ? new Date(r.finalizedAt).toLocaleString() : '—'}"`,
        `"${certifier?.name || 'Examination Board'}"`,
      ].join(',');
    });

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `evalnexa-results-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Real Export JSON
  const handleExportJSON = () => {
    if (examScopedResults.length === 0) {
      alert('No finalized result records available for export.');
      return;
    }

    const payload = examScopedResults.map((r) => {
      const ab = typeof r.answerBookId === 'object' ? (r.answerBookId as AnswerBook) : null;
      const exam = typeof r.examId === 'object' ? (r.examId as Exam) : null;
      const examiner = typeof r.examinerId === 'object' ? (r.examinerId as User) : null;
      const certifier = typeof r.finalizedBy === 'object' ? (r.finalizedBy as User) : null;

      return {
        id: r._id,
        studentCode: ab?.studentCode || null,
        scriptCode: ab?.answerBookCode || null,
        subjectCode: exam?.subjectCode || null,
        examination: exam?.title || null,
        examiner: examiner?.name || null,
        marks: r.totalMarks,
        maximumMarks: r.maximumMarks,
        percentage: r.percentage,
        status: r.status,
        finalizedAt: r.finalizedAt || null,
        finalizedBy: certifier?.name || 'Examination Board',
      };
    });

    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(payload, null, 2));
    const link = document.createElement('a');
    link.setAttribute('href', dataStr);
    link.setAttribute('download', `evalnexa-results-${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const isLoading = isLoadingResults || isLoadingBooks || isLoadingEvals;

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Control Center · Certification & Publishing</div>
          <h1 className="page-header__title">Results & Certification</h1>
          <p className="page-header__subtitle">
            Authoritative certified examination results finalized from the moderation lifecycle. Updates in real time without page reload.
          </p>
        </div>
        <div className="page-header__actions" style={{ display: 'flex', gap: 'var(--space-3)' }}>
          <select
            className="form-select"
            style={{ width: 240, fontSize: 'var(--text-body)' }}
            value={selectedExamId}
            onChange={(e) => setSelectedExamId(e.target.value)}
          >
            <option value="">All Institutional Examinations</option>
            {exams.map((ex) => (
              <option key={ex._id} value={ex._id}>
                {ex.title} ({ex.subjectCode})
              </option>
            ))}
          </select>
          <button className="btn btn-secondary" onClick={handleExportCSV}>
            ↓ Export CSV
          </button>
          <button className="btn btn-secondary" onClick={handleExportJSON}>
            ↓ Export JSON
          </button>
        </div>
      </div>

      {/* Action / Error Alerts */}
      {actionError && (
        <div className="badge-flag" style={{ padding: 'var(--space-3) var(--space-4)', marginBottom: 'var(--space-4)', display: 'flex', justifyContent: 'space-between' }}>
          <span><strong>Finalization Notice:</strong> {actionError}</span>
          <button style={{ background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700 }} onClick={() => setActionError(null)}>✕</button>
        </div>
      )}
      {successMsg && (
        <div style={{ background: '#dcfce7', border: '1px solid #86efac', color: '#166534', borderRadius: 'var(--radius-sm)', padding: 'var(--space-3) var(--space-4)', marginBottom: 'var(--space-4)', display: 'flex', justifyContent: 'space-between' }}>
          <span><strong>Success:</strong> {successMsg}</span>
          <button style={{ background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700, color: '#166534' }} onClick={() => setSuccessMsg(null)}>✕</button>
        </div>
      )}

      {/* FINAL RESULT PIPELINE (Evaluated, Pending Moderation, Approved, Finalized) */}
      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', marginBottom: 'var(--space-6)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow">EVALUATED</div>
          <div className="stat-card__value">{evaluatedCount}</div>
          <div className="stat-card__sub">Marked by examiners</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow">PENDING MODERATION</div>
          <div className="stat-card__value" style={{ color: 'var(--status-review-text)' }}>
            {pendingModerationCount}
          </div>
          <div className="stat-card__sub">Under moderator inspection</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow">APPROVED</div>
          <div className="stat-card__value" style={{ color: 'var(--status-approved-text)' }}>
            {approvedCount}
          </div>
          <div className="stat-card__sub">Moderator cleared</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow">FINALIZED</div>
          <div className="stat-card__value" style={{ color: 'var(--parchment-navy)' }}>
            {finalizedCount}
          </div>
          <div className="stat-card__sub">Certified result register</div>
        </div>
      </div>

      {/* RESULT REGISTER CARD */}
      <div className="folio-card">
        <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="folio-card__title">
              {statusFilter === 'FINALIZED'
                ? `Certified Result Register (${examScopedResults.length})`
                : statusFilter === 'AWAITING_FINALIZATION'
                ? `Approved Scripts Awaiting Finalization (${approvedAwaitingFinalization.length})`
                : `Lifecycle Register`}
            </span>
            <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
              {statusFilter === 'FINALIZED'
                ? 'Official results computed, verified, and sealed by the backend certification service'
                : 'Audited records moving through the institutional examination pipeline'}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
            <span className="label-caps" style={{ fontSize: 'var(--text-metadata)' }}>Filter:</span>
            <select
              className="form-select"
              style={{ fontSize: 'var(--text-metadata)', padding: '5px 10px', minWidth: 240 }}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="FINALIZED">Finalized / Certified Results</option>
              <option value="AWAITING_FINALIZATION">Approved (Ready to Finalize)</option>
              <option value="PENDING_MODERATION">Pending Moderation Review</option>
              <option value="ALL">All Evaluated Records</option>
            </select>
          </div>
        </div>

        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoading ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : statusFilter === 'FINALIZED' ? (
            /* CERTIFIED RESULTS VIEW */
            examScopedResults.length === 0 ? (
              <div className="state-container" style={{ padding: 'var(--space-10)' }}>
                <div className="state-icon">🏛</div>
                <div className="state-title">No Certified Results Yet</div>
                <div className="state-body">
                  Official marks will appear here once approved evaluations are finalized into the university result register.
                  {approvedAwaitingFinalization.length > 0 && (
                    <div style={{ marginTop: 'var(--space-4)' }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => setStatusFilter('AWAITING_FINALIZATION')}
                      >
                        View {approvedAwaitingFinalization.length} Approved Script(s) Ready for Finalization →
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Student Code</th>
                      <th>Script</th>
                      <th>Exam</th>
                      <th>Marks</th>
                      <th>Maximum</th>
                      <th>Percentage</th>
                      <th>Status</th>
                      <th>Certified Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {examScopedResults.map((r) => {
                      const ab = typeof r.answerBookId === 'object' ? (r.answerBookId as AnswerBook) : null;
                      const exam = typeof r.examId === 'object' ? (r.examId as Exam) : null;

                      return (
                        <tr key={r._id}>
                          <td>
                            <span className="label-mono" style={{ fontSize: 'var(--text-table)', fontWeight: 600 }}>
                              {ab?.studentCode || '—'}
                            </span>
                          </td>
                          <td>
                            <span className="data-table__code">{ab?.answerBookCode || '—'}</span>
                          </td>
                          <td>
                            {exam ? (
                              <div>
                                <div style={{ fontWeight: 600, fontSize: 'var(--text-table)' }}>{exam.title}</div>
                                <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                                  {exam.subjectCode}
                                </div>
                              </div>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td>
                            <span style={{ fontSize: 'var(--text-body)', fontWeight: 700, color: 'var(--text-primary)' }}>
                              {r.totalMarks}
                            </span>
                          </td>
                          <td>
                            <span className="label-mono" style={{ fontSize: 'var(--text-table)', color: 'var(--text-muted)' }}>
                              {r.maximumMarks}
                            </span>
                          </td>
                          <td>
                            <span className="label-mono" style={{ fontSize: 'var(--text-table)', fontWeight: 600, color: 'var(--parchment-navy)' }}>
                              {r.percentage}%
                            </span>
                          </td>
                          <td>
                            <StatusBadge status={r.status} />
                          </td>
                          <td className="label-mono" style={{ fontSize: 'var(--text-metadata)' }}>
                            {r.finalizedAt ? new Date(r.finalizedAt).toLocaleString() : '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          ) : statusFilter === 'AWAITING_FINALIZATION' ? (
            /* APPROVED AWAITING FINALIZATION VIEW */
            approvedAwaitingFinalization.length === 0 ? (
              <div className="state-container" style={{ padding: 'var(--space-10)' }}>
                <div className="state-icon">✓</div>
                <div className="state-title">No Pending Finalizations</div>
                <div className="state-body">
                  All approved evaluation records have been processed and certified into results.
                </div>
              </div>
            ) : (
              <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Student Code</th>
                      <th>Script</th>
                      <th>Exam</th>
                      <th>Marks Awarded</th>
                      <th>Moderation Status</th>
                      <th>Approved At</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {approvedAwaitingFinalization.map((ev) => {
                      const ab = ev.answerBookId as unknown as AnswerBook;
                      const exam = typeof ab?.examId === 'object' ? (ab.examId as unknown as Exam) : null;

                      return (
                        <tr key={ev._id}>
                          <td>
                            <span className="label-mono" style={{ fontSize: 'var(--text-table)', fontWeight: 600 }}>
                              {ab?.studentCode || '—'}
                            </span>
                          </td>
                          <td>
                            <span className="data-table__code">{ab?.answerBookCode || '—'}</span>
                          </td>
                          <td>
                            {exam ? (
                              <div>
                                <div style={{ fontWeight: 600, fontSize: 'var(--text-table)' }}>{exam.title}</div>
                                <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                                  {exam.subjectCode}
                                </div>
                              </div>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td>
                            <span style={{ fontSize: 'var(--text-body)', fontWeight: 700, color: 'var(--text-primary)' }}>
                              {ev.totalMarks ?? 0} / {exam?.maximumMarks ?? 100}
                            </span>
                          </td>
                          <td>
                            <StatusBadge status="APPROVED" />
                          </td>
                          <td className="label-mono" style={{ fontSize: 'var(--text-metadata)' }}>
                            {ev.updatedAt ? new Date(ev.updatedAt).toLocaleString() : '—'}
                          </td>
                          <td>
                            <button
                              className="btn btn-primary btn-sm"
                              style={{ whiteSpace: 'nowrap' }}
                              onClick={() => finalizeMutation.mutate(ev._id)}
                              disabled={finalizeMutation.isPending}
                            >
                              {finalizeMutation.isPending ? 'Certifying...' : 'Finalize & Certify'}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          ) : (
            /* ALL / PENDING MODERATION VIEW */
            (() => {
              const rows = examScopedEvals.filter((ev) => {
                if (statusFilter === 'PENDING_MODERATION') {
                  return ev.status === 'SUBMITTED' || ev.status === 'UNDER_REVIEW';
                }
                return true;
              });

              if (rows.length === 0) {
                return (
                  <div className="state-container" style={{ padding: 'var(--space-10)' }}>
                    <div className="state-icon">📋</div>
                    <div className="state-title">No Records Found</div>
                    <div className="state-body">No evaluations match the selected filter.</div>
                  </div>
                );
              }

              return (
                <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Student Code</th>
                        <th>Script</th>
                        <th>Exam</th>
                        <th>Marks</th>
                        <th>Status</th>
                        <th>Last Updated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((ev) => {
                        const ab = ev.answerBookId as unknown as AnswerBook;
                        const exam = typeof ab?.examId === 'object' ? (ab.examId as unknown as Exam) : null;

                        return (
                          <tr key={ev._id}>
                            <td>
                              <span className="label-mono" style={{ fontSize: 'var(--text-table)', fontWeight: 600 }}>
                                {ab?.studentCode || '—'}
                              </span>
                            </td>
                            <td>
                              <span className="data-table__code">{ab?.answerBookCode || '—'}</span>
                            </td>
                            <td>
                              {exam ? (
                                <div>
                                  <div style={{ fontWeight: 600, fontSize: 'var(--text-table)' }}>{exam.title}</div>
                                  <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                                    {exam.subjectCode}
                                  </div>
                                </div>
                              ) : (
                                '—'
                              )}
                            </td>
                            <td>
                              <span style={{ fontSize: 'var(--text-body)', fontWeight: 700, color: 'var(--text-primary)' }}>
                                {ev.totalMarks ?? 0}
                              </span>
                            </td>
                            <td>
                              <StatusBadge status={ev.status} />
                            </td>
                            <td className="label-mono" style={{ fontSize: 'var(--text-metadata)' }}>
                              {ev.updatedAt ? new Date(ev.updatedAt).toLocaleString() : '—'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              );
            })()
          )}
        </div>
      </div>
    </div>
  );
}
