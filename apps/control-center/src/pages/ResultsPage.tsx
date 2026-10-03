import React, { useState, useMemo, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { Evaluation, Exam, AnswerBook, User } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';
import { useSocketEvents } from '../hooks/useSocketEvents';

export function ResultsPage() {
  const queryClient = useQueryClient();
  const [selectedExamId, setSelectedExamId] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('FINALIZED'); // Default to finalized records

  // 1. Fetch real Answer Books for accurate total script counts
  const { data: answerBooks = [], isLoading: isLoadingBooks } = useQuery<AnswerBook[]>({
    queryKey: ['results-answerbooks'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books');
      return data.data;
    },
  });

  // 2. Fetch real Evaluations from MongoDB
  const { data: evaluations = [], isLoading: isLoadingEvals } = useQuery<Evaluation[]>({
    queryKey: ['results-evaluations'],
    queryFn: async () => {
      const { data } = await apiClient.get('/evaluations');
      return data.data;
    },
  });

  // 3. Fetch real Exams
  const { data: exams = [] } = useQuery<Exam[]>({
    queryKey: ['results-exams'],
    queryFn: async () => {
      const { data } = await apiClient.get('/exams');
      return data.data;
    },
  });

  // Live Socket.IO invalidation
  const handlers = useCallback(() => ({
    'evaluation.submitted': () => {
      queryClient.invalidateQueries({ queryKey: ['results-evaluations'] });
      queryClient.invalidateQueries({ queryKey: ['results-answerbooks'] });
    },
    'moderation.approved': () => {
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
    },
    'result.updated': () => {
      queryClient.invalidateQueries({ queryKey: ['results-evaluations'] });
      queryClient.invalidateQueries({ queryKey: ['results-answerbooks'] });
    },
  }), [queryClient]);
  useSocketEvents(handlers());

  // Filter answer books by selected exam
  const examScopedBooks = useMemo(() => {
    return selectedExamId
      ? answerBooks.filter((b) => {
          const eid = typeof b.examId === 'object' ? (b.examId as any)._id : b.examId;
          return eid === selectedExamId;
        })
      : answerBooks;
  }, [answerBooks, selectedExamId]);

  // Filter evaluations by selected exam
  const examScopedEvals = useMemo(() => {
    return selectedExamId
      ? evaluations.filter((ev) => {
          const ab = ev.answerBookId as unknown as AnswerBook;
          const eid = typeof ab?.examId === 'object' ? (ab.examId as any)._id : ab?.examId;
          return eid === selectedExamId;
        })
      : evaluations;
  }, [evaluations, selectedExamId]);

  // FINAL RESULT PIPELINE (Prompt Section 19: Evaluated, Pending Moderation, Approved, Finalized)
  const evaluatedCount = examScopedBooks.filter((b) =>
    ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'FINALIZED'].includes(b.status)
  ).length;
  const pendingModerationCount = examScopedBooks.filter((b) =>
    ['SUBMITTED', 'UNDER_REVIEW'].includes(b.status)
  ).length;
  const approvedCount = examScopedBooks.filter((b) => b.status === 'APPROVED').length;
  const finalizedCount = examScopedBooks.filter((b) => b.status === 'FINALIZED' || b.status === 'APPROVED').length;

  // Filtered rows for the results table
  const displayEvaluations = useMemo(() => {
    return examScopedEvals.filter((ev) => {
      if (statusFilter === 'FINALIZED') {
        return ev.status === 'APPROVED'; // In EvalNexa, moderator approval marks evaluation approved/finalized
      }
      if (statusFilter === 'PENDING_MODERATION') {
        return ev.status === 'SUBMITTED' || ev.status === 'UNDER_REVIEW';
      }
      if (statusFilter === 'EVALUATED') {
        return ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'RETURNED'].includes(ev.status);
      }
      return true; // 'ALL'
    });
  }, [examScopedEvals, statusFilter]);

  // Real Export CSV
  const handleExportCSV = () => {
    if (displayEvaluations.length === 0) {
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
      'Status',
      'Approved At',
    ];

    const rows = displayEvaluations.map((ev) => {
      const ab = ev.answerBookId as unknown as AnswerBook;
      const exam = typeof ab?.examId === 'object' ? (ab.examId as unknown as Exam) : null;
      const examiner = typeof ev.examinerId === 'object' ? (ev.examinerId as unknown as User) : null;

      return [
        `"${ab?.studentCode || '—'}"`,
        `"${ab?.answerBookCode || '—'}"`,
        `"${exam?.subjectCode || '—'}"`,
        `"${exam?.title || '—'}"`,
        `"${examiner?.name || '—'}"`,
        ev.totalMarks ?? 0,
        exam?.maximumMarks ?? 100,
        ev.status,
        `"${ev.updatedAt ? new Date(ev.updatedAt).toLocaleString() : '—'}"`,
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
    if (displayEvaluations.length === 0) {
      alert('No finalized result records available for export.');
      return;
    }

    const payload = displayEvaluations.map((ev) => {
      const ab = ev.answerBookId as unknown as AnswerBook;
      const exam = typeof ab?.examId === 'object' ? (ab.examId as unknown as Exam) : null;
      const examiner = typeof ev.examinerId === 'object' ? (ev.examinerId as unknown as User) : null;

      return {
        studentCode: ab?.studentCode || null,
        scriptCode: ab?.answerBookCode || null,
        subjectCode: exam?.subjectCode || null,
        examination: exam?.title || null,
        examiner: examiner?.name || null,
        marks: ev.totalMarks ?? 0,
        maximumMarks: exam?.maximumMarks ?? 100,
        status: ev.status,
        approvedAt: ev.updatedAt || null,
        questionMarks: ev.questionMarks || [],
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

  const isLoading = isLoadingBooks || isLoadingEvals;

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Control Center · Certification & Publishing</div>
          <h1 className="page-header__title">Results & Certification</h1>
          <p className="page-header__subtitle">
            Certified examination results approved by the Moderation & Quality Center. Updates in real time without page reload.
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

      {/* FINAL RESULT PIPELINE (Prompt Section 19: Evaluated, Pending Moderation, Approved, Finalized) */}
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

      {/* RESULT REGISTER (Prompt Section 19: Student Code, Script, Exam, Marks, Maximum, Status, Approved At) */}
      <div className="folio-card">
        <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="folio-card__title">Result Register ({displayEvaluations.length})</span>
            <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
              Certified marks verified by the university examination board
            </div>
          </div>

          <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
            <span className="label-caps" style={{ fontSize: 'var(--text-metadata)' }}>Filter:</span>
            <select
              className="form-select"
              style={{ fontSize: 'var(--text-metadata)', padding: '5px 10px', minWidth: 220 }}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="FINALIZED">Finalized / Approved Results</option>
              <option value="PENDING_MODERATION">Pending Moderation</option>
              <option value="EVALUATED">All Evaluated Scripts</option>
              <option value="ALL">All Records</option>
            </select>
          </div>
        </div>

        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoading ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : displayEvaluations.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-10)' }}>
              <div className="state-icon">🏛</div>
              <div className="state-title">No Finalized Results</div>
              <div className="state-body">
                Official marks will appear here once submitted evaluations are reviewed and approved by the Moderation & Quality Center.
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
                    <th>Status</th>
                    <th>Approved At</th>
                  </tr>
                </thead>
                <tbody>
                  {displayEvaluations.map((ev) => {
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
                          <span className="label-mono" style={{ fontSize: 'var(--text-table)', color: 'var(--text-muted)' }}>
                            {exam?.maximumMarks ?? 100}
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
          )}
        </div>
      </div>
    </div>
  );
}
