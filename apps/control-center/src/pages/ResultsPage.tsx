import React, { useState, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { Evaluation, Exam, AnswerBook, User, Result } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';
import { useSocketEvents } from '../hooks/useSocketEvents';

function formatClassification(classification?: string): string {
  if (!classification) return '—';
  switch (classification) {
    case 'FIRST_CLASS_DISTINCTION':
      return 'First Class Distinction';
    case 'FIRST_CLASS':
      return 'First Class';
    case 'HIGHER_SECOND_CLASS':
      return 'Higher Second Class';
    case 'SECOND_CLASS':
      return 'Second Class';
    case 'PASS':
      return 'Pass Division';
    case 'FAIL':
      return 'Fail / Unsatisfactory';
    default:
      return classification.replace(/_/g, ' ');
  }
}

export function ResultsPage() {
  const queryClient = useQueryClient();
  const [selectedExamId, setSelectedExamId] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('CERTIFIED_ALL'); // Default to all certified records
  const [actionError, setActionError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Withholding modal state
  const [withholdModalResultId, setWithholdModalResultId] = useState<string | null>(null);
  const [withholdReasonInput, setWithholdReasonInput] = useState<string>('');

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
    'result.published': () => {
      queryClient.invalidateQueries({ queryKey: ['results-records'] });
      queryClient.invalidateQueries({ queryKey: ['results-evaluations'] });
      queryClient.invalidateQueries({ queryKey: ['results-answerbooks'] });
    },
    'result.withheld': () => {
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

  // Specific filtered result records based on statusFilter
  const displayResults = useMemo(() => {
    if (statusFilter === 'CERTIFIED_ALL') {
      return examScopedResults;
    }
    if (statusFilter === 'PUBLISHED') {
      return examScopedResults.filter((r) => r.status === 'PUBLISHED');
    }
    if (statusFilter === 'FINALIZED') {
      return examScopedResults.filter((r) => r.status === 'FINALIZED');
    }
    if (statusFilter === 'WITHHELD') {
      return examScopedResults.filter((r) => r.status === 'WITHHELD');
    }
    return examScopedResults;
  }, [examScopedResults, statusFilter]);

  // Mutations
  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['results-records'] });
    queryClient.invalidateQueries({ queryKey: ['results-evaluations'] });
    queryClient.invalidateQueries({ queryKey: ['results-answerbooks'] });
  };

  // 1. Single Finalization Mutation: POST /api/results/:evaluationId/finalize
  const finalizeMutation = useMutation({
    mutationFn: async (evaluationId: string) => {
      const { data } = await apiClient.post(`/results/${evaluationId}/finalize`);
      return data.data;
    },
    onSuccess: () => {
      setSuccessMsg('Result successfully verified and certified into official institutional register.');
      setActionError(null);
      invalidateAll();
    },
    onError: (err: any) => {
      const msg = err.response?.data?.message || 'Failed to finalize examination result.';
      setActionError(msg);
      setSuccessMsg(null);
    },
  });

  // 2. Publish Single Result Mutation: POST /api/results/:id/publish
  const publishMutation = useMutation({
    mutationFn: async (resultId: string) => {
      const { data } = await apiClient.post(`/results/${resultId}/publish`);
      return data.data;
    },
    onSuccess: () => {
      setSuccessMsg('Examination result published to official institutional ledger.');
      setActionError(null);
      invalidateAll();
    },
    onError: (err: any) => {
      const msg = err.response?.data?.message || 'Failed to publish examination result.';
      setActionError(msg);
      setSuccessMsg(null);
    },
  });

  // 3. Withhold Result Mutation: POST /api/results/:id/withhold
  const withholdMutation = useMutation({
    mutationFn: async ({ resultId, reason }: { resultId: string; reason: string }) => {
      const { data } = await apiClient.post(`/results/${resultId}/withhold`, { reason });
      return data.data;
    },
    onSuccess: () => {
      setSuccessMsg('Result successfully flagged as withheld in the governance register.');
      setActionError(null);
      setWithholdModalResultId(null);
      setWithholdReasonInput('');
      invalidateAll();
    },
    onError: (err: any) => {
      const msg = err.response?.data?.message || 'Failed to withhold examination result.';
      setActionError(msg);
      setSuccessMsg(null);
    },
  });

  // 4. Release Result Mutation: POST /api/results/:id/release
  const releaseMutation = useMutation({
    mutationFn: async (resultId: string) => {
      const { data } = await apiClient.post(`/results/${resultId}/release`);
      return data.data;
    },
    onSuccess: () => {
      setSuccessMsg('Withheld result released and restored to active certified status.');
      setActionError(null);
      invalidateAll();
    },
    onError: (err: any) => {
      const msg = err.response?.data?.message || 'Failed to release withheld result.';
      setActionError(msg);
      setSuccessMsg(null);
    },
  });

  // 5. Batch Publish Exam Mutation: POST /api/results/publish-exam
  const publishExamMutation = useMutation({
    mutationFn: async (examId: string) => {
      const { data } = await apiClient.post('/results/publish-exam', { examId });
      return data.data;
    },
    onSuccess: (data) => {
      setSuccessMsg(data?.message || 'Examination results batch published successfully.');
      setActionError(null);
      invalidateAll();
    },
    onError: (err: any) => {
      const msg = err.response?.data?.message || 'Failed to publish examination results.';
      setActionError(msg);
      setSuccessMsg(null);
    },
  });

  // 6. Batch Finalize Mutation: POST /api/results/batch-finalize
  const batchFinalizeMutation = useMutation({
    mutationFn: async (examId: string) => {
      const { data } = await apiClient.post('/results/batch-finalize', { examId });
      return data.data;
    },
    onSuccess: (data) => {
      setSuccessMsg(
        `Batch finalization complete: ${data?.finalizedCount ?? 0} approved script(s) certified.`
      );
      setActionError(null);
      invalidateAll();
    },
    onError: (err: any) => {
      const msg = err.response?.data?.message || 'Failed to batch finalize results.';
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

  const publishedCount = examScopedResults.filter((r) => r.status === 'PUBLISHED').length;
  const withheldCount = examScopedResults.filter((r) => r.status === 'WITHHELD').length;
  const finalizedUnpublishedCount = examScopedResults.filter((r) => r.status === 'FINALIZED').length;

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
      alert('No certified result records available for export.');
      return;
    }

    const headers = [
      'Student Code',
      'Script Code',
      'Subject Code',
      'Examination Title',
      'Accredited Examiner',
      'Marks Awarded',
      'Maximum Marks',
      'Percentage',
      'Grade',
      'Grade Points',
      'Classification',
      'Status',
      'Finalized At',
      'Finalized By',
      'Published At',
      'Published By',
      'Withheld Reason',
    ];

    const rows = examScopedResults.map((r) => {
      const ab = typeof r.answerBookId === 'object' ? (r.answerBookId as AnswerBook) : null;
      const exam = typeof r.examId === 'object' ? (r.examId as Exam) : null;
      const examiner = typeof r.examinerId === 'object' ? (r.examinerId as User) : null;
      const certifier = typeof r.finalizedBy === 'object' ? (r.finalizedBy as User) : null;
      const publisher = typeof r.publishedBy === 'object' ? (r.publishedBy as User) : null;

      return [
        `"${ab?.studentCode || '—'}"`,
        `"${ab?.answerBookCode || '—'}"`,
        `"${exam?.subjectCode || '—'}"`,
        `"${exam?.title || '—'}"`,
        `"${examiner?.name || '—'}"`,
        r.totalMarks,
        r.maximumMarks,
        `"${r.percentage}%"`,
        `"${r.grade || '—'}"`,
        r.gradePoint !== undefined ? r.gradePoint : '—',
        `"${formatClassification(r.classification)}"`,
        r.status,
        `"${r.finalizedAt ? new Date(r.finalizedAt).toLocaleString() : '—'}"`,
        `"${certifier?.name || 'Examination Board'}"`,
        `"${r.publishedAt ? new Date(r.publishedAt).toLocaleString() : '—'}"`,
        `"${publisher?.name || '—'}"`,
        `"${r.withheldReason || '—'}"`,
      ].join(',');
    });

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `evalnexa-results-ledger-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Real Export JSON
  const handleExportJSON = () => {
    if (examScopedResults.length === 0) {
      alert('No certified result records available for export.');
      return;
    }

    const payload = examScopedResults.map((r) => {
      const ab = typeof r.answerBookId === 'object' ? (r.answerBookId as AnswerBook) : null;
      const exam = typeof r.examId === 'object' ? (r.examId as Exam) : null;
      const examiner = typeof r.examinerId === 'object' ? (r.examinerId as User) : null;
      const certifier = typeof r.finalizedBy === 'object' ? (r.finalizedBy as User) : null;
      const publisher = typeof r.publishedBy === 'object' ? (r.publishedBy as User) : null;

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
        grade: r.grade || null,
        gradePoint: r.gradePoint ?? null,
        classification: r.classification || null,
        status: r.status,
        finalizedAt: r.finalizedAt || null,
        finalizedBy: certifier?.name || 'Examination Board',
        publishedAt: r.publishedAt || null,
        publishedBy: publisher?.name || null,
        withheldReason: r.withheldReason || null,
      };
    });

    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(payload, null, 2));
    const link = document.createElement('a');
    link.setAttribute('href', dataStr);
    link.setAttribute('download', `evalnexa-results-ledger-${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const isLoading = isLoadingResults || isLoadingBooks || isLoadingEvals;
  const isAnyCertifiedView = ['CERTIFIED_ALL', 'PUBLISHED', 'FINALIZED', 'WITHHELD'].includes(statusFilter);

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Control Center · Certification & Ledger Publishing</div>
          <h1 className="page-header__title">Results & Certification</h1>
          <p className="page-header__subtitle">
            Authoritative certified examination results, grade calculations, and institutional ledger publication.
          </p>
        </div>
        <div className="page-header__actions" style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
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

          {/* Contextual batch actions for selected exam */}
          {selectedExamId && finalizedUnpublishedCount > 0 && (
            <button
              className="btn btn-primary"
              onClick={() => publishExamMutation.mutate(selectedExamId)}
              disabled={publishExamMutation.isPending}
            >
              {publishExamMutation.isPending ? 'Publishing...' : `Publish Exam Results (${finalizedUnpublishedCount})`}
            </button>
          )}

          {selectedExamId && approvedAwaitingFinalization.length > 0 && (
            <button
              className="btn btn-secondary"
              onClick={() => batchFinalizeMutation.mutate(selectedExamId)}
              disabled={batchFinalizeMutation.isPending}
            >
              {batchFinalizeMutation.isPending ? 'Finalizing...' : `Finalize All Approved (${approvedAwaitingFinalization.length})`}
            </button>
          )}

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
          <span><strong>Notice:</strong> {actionError}</span>
          <button style={{ background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700 }} onClick={() => setActionError(null)}>✕</button>
        </div>
      )}
      {successMsg && (
        <div style={{ background: '#dcfce7', border: '1px solid #86efac', color: '#166534', borderRadius: 'var(--radius-sm)', padding: 'var(--space-3) var(--space-4)', marginBottom: 'var(--space-4)', display: 'flex', justifyContent: 'space-between' }}>
          <span><strong>Success:</strong> {successMsg}</span>
          <button style={{ background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700, color: '#166534' }} onClick={() => setSuccessMsg(null)}>✕</button>
        </div>
      )}

      {/* FINAL RESULT PIPELINE METRICS */}
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
          <div className="stat-card__eyebrow">APPROVED (READY)</div>
          <div className="stat-card__value" style={{ color: 'var(--status-approved-text)' }}>
            {approvedCount}
          </div>
          <div className="stat-card__sub">Moderator cleared</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow">CERTIFIED LEDGER</div>
          <div className="stat-card__value" style={{ color: 'var(--parchment-navy)' }}>
            {publishedCount} <span style={{ fontSize: 'var(--text-table)', color: 'var(--text-muted)' }}>/ {finalizedCount}</span>
          </div>
          <div className="stat-card__sub">
            {publishedCount} published · {withheldCount} withheld
          </div>
        </div>
      </div>

      {/* RESULT REGISTER CARD */}
      <div className="folio-card">
        <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="folio-card__title">
              {statusFilter === 'CERTIFIED_ALL'
                ? `Certified Result Register (${displayResults.length})`
                : statusFilter === 'PUBLISHED'
                ? `Published Examination Results (${displayResults.length})`
                : statusFilter === 'FINALIZED'
                ? `Certified Unpublished Results (${displayResults.length})`
                : statusFilter === 'WITHHELD'
                ? `Withheld Examination Results (${displayResults.length})`
                : statusFilter === 'AWAITING_FINALIZATION'
                ? `Approved Scripts Awaiting Finalization (${approvedAwaitingFinalization.length})`
                : `Examination Lifecycle Register`}
            </span>
            <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
              {isAnyCertifiedView
                ? 'Official results computed, graded, and sealed in the authoritative institutional ledger'
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
              <option value="CERTIFIED_ALL">All Certified Results ({examScopedResults.length})</option>
              <option value="PUBLISHED">Published on Ledger ({publishedCount})</option>
              <option value="FINALIZED">Certified / Unpublished ({finalizedUnpublishedCount})</option>
              <option value="WITHHELD">Withheld by Board ({withheldCount})</option>
              <option value="AWAITING_FINALIZATION">Approved (Ready to Finalize) ({approvedAwaitingFinalization.length})</option>
              <option value="PENDING_MODERATION">Pending Moderation Review</option>
              <option value="ALL">All Evaluated Records</option>
            </select>
          </div>
        </div>

        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoading ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : isAnyCertifiedView ? (
            /* CERTIFIED RESULTS VIEW */
            displayResults.length === 0 ? (
              <div className="state-container" style={{ padding: 'var(--space-10)' }}>
                <div className="state-icon">🏛</div>
                <div className="state-title">No Records Found</div>
                <div className="state-body">
                  No certified results match the current status filter.
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
                      <th>Grade & GP</th>
                      <th>Classification</th>
                      <th>Status</th>
                      <th>Publication Date</th>
                      <th style={{ textAlign: 'right' }}>Ledger Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayResults.map((r) => {
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
                            <div>
                              <span style={{ fontSize: 'var(--text-body)', fontWeight: 700, color: 'var(--text-primary)' }}>
                                {r.totalMarks}
                              </span>
                              <span className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                                {' '}/ {r.maximumMarks}
                              </span>
                            </div>
                            <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', fontWeight: 600, color: 'var(--parchment-navy)' }}>
                              {r.percentage}%
                            </div>
                          </td>
                          <td>
                            <span
                              className="label-mono"
                              style={{
                                fontSize: 'var(--text-table)',
                                fontWeight: 700,
                                color: r.grade === 'F' ? 'var(--burgundy)' : 'var(--text-primary)',
                              }}
                            >
                              {r.grade || '—'} {r.gradePoint !== undefined ? `(${r.gradePoint})` : ''}
                            </span>
                          </td>
                          <td>
                            <span
                              style={{
                                fontSize: 'var(--text-metadata)',
                                fontWeight: 500,
                                color: r.classification === 'FAIL' ? 'var(--burgundy)' : 'var(--text-secondary)',
                              }}
                            >
                              {formatClassification(r.classification)}
                            </span>
                          </td>
                          <td>
                            <StatusBadge status={r.status} />
                            {r.status === 'WITHHELD' && r.withheldReason && (
                              <div
                                style={{
                                  fontSize: '11px',
                                  color: 'var(--burgundy)',
                                  marginTop: 'var(--space-1)',
                                  maxWidth: 200,
                                  whiteSpace: 'normal',
                                  wordBreak: 'break-word',
                                }}
                              >
                                <em>Reason: {r.withheldReason}</em>
                              </div>
                            )}
                          </td>
                          <td className="label-mono" style={{ fontSize: 'var(--text-metadata)' }}>
                            {r.publishedAt
                              ? new Date(r.publishedAt).toLocaleString()
                              : r.finalizedAt
                              ? `Finalized: ${new Date(r.finalizedAt).toLocaleDateString()}`
                              : '—'}
                          </td>
                          <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                            <div style={{ display: 'inline-flex', gap: 'var(--space-2)' }}>
                              {r.status === 'FINALIZED' && (
                                <button
                                  className="btn btn-primary btn-sm"
                                  onClick={() => publishMutation.mutate(r._id)}
                                  disabled={publishMutation.isPending}
                                  title="Publish certified result to institutional ledger"
                                >
                                  {publishMutation.isPending ? 'Publishing...' : 'Publish'}
                                </button>
                              )}
                              {r.status === 'PUBLISHED' && (
                                <button
                                  className="btn btn-secondary btn-sm"
                                  style={{ color: 'var(--burgundy)', borderColor: 'rgba(92, 29, 36, 0.4)' }}
                                  onClick={() => {
                                    setWithholdModalResultId(r._id);
                                    setWithholdReasonInput('');
                                  }}
                                  title="Flag result as withheld with administrative rationale"
                                >
                                  Withhold
                                </button>
                              )}
                              {r.status === 'WITHHELD' && (
                                <button
                                  className="btn btn-secondary btn-sm"
                                  style={{ color: '#2D6A4F', borderColor: 'rgba(45, 106, 79, 0.4)' }}
                                  onClick={() => releaseMutation.mutate(r._id)}
                                  disabled={releaseMutation.isPending}
                                  title="Release from withheld status back to active register"
                                >
                                  {releaseMutation.isPending ? 'Releasing...' : 'Release'}
                                </button>
                              )}
                            </div>
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

      {/* WITHHOLD MODAL */}
      {withholdModalResultId && (
        <div
          className="modal-backdrop"
          onClick={(e) => e.target === e.currentTarget && setWithholdModalResultId(null)}
        >
          <div className="modal" style={{ maxWidth: 540 }}>
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow">Academic Governance · Administrative Action</div>
                <div className="modal__title">Withhold Certified Examination Result</div>
              </div>
              <button className="modal__close" onClick={() => setWithholdModalResultId(null)}>✕</button>
            </div>
            <div className="modal__body">
              <p style={{ fontSize: 'var(--text-table)', color: 'var(--text-secondary)', marginBottom: 'var(--space-4)' }}>
                Please specify the authoritative governance rationale for withholding this result from public dissemination. This justification will be immutably recorded in the institutional audit ledger.
              </p>
              <div className="form-group">
                <label className="form-label" htmlFor="withhold-reason">
                  Withholding Rationale *
                </label>
                <textarea
                  id="withhold-reason"
                  className="form-textarea"
                  rows={4}
                  placeholder="e.g. Identity verification discrepancy flagged by academic board..."
                  value={withholdReasonInput}
                  onChange={(e) => setWithholdReasonInput(e.target.value)}
                />
              </div>
            </div>
            <div className="modal__footer">
              <button className="btn btn-secondary" onClick={() => setWithholdModalResultId(null)}>
                Cancel
              </button>
              <button
                className="btn btn-danger"
                disabled={!withholdReasonInput.trim() || withholdMutation.isPending}
                onClick={() => {
                  if (withholdModalResultId && withholdReasonInput.trim()) {
                    withholdMutation.mutate({
                      resultId: withholdModalResultId,
                      reason: withholdReasonInput.trim(),
                    });
                  }
                }}
              >
                {withholdMutation.isPending ? 'Withholding...' : 'Confirm Withhold'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
