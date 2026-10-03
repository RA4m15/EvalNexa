import React, { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { Evaluation, Exam, AnswerBook, User } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';
import { useSocketEvents } from '../hooks/useSocketEvents';

export function ResultsPage() {
  const queryClient = useQueryClient();
  const [selectedExamId, setSelectedExamId] = useState<string>('');

  const { data: evaluations = [], isLoading } = useQuery<Evaluation[]>({
    queryKey: ['results-evaluations'],
    queryFn: async () => {
      const { data } = await apiClient.get('/evaluations');
      return data.data;
    },
  });

  const { data: exams = [] } = useQuery<Exam[]>({
    queryKey: ['results-exams'],
    queryFn: async () => {
      const { data } = await apiClient.get('/exams');
      return data.data;
    },
  });

  const handlers = useCallback(() => ({
    'evaluation.submitted': () => queryClient.invalidateQueries({ queryKey: ['results-evaluations'] }),
    'moderation.approved': () => queryClient.invalidateQueries({ queryKey: ['results-evaluations'] }),
    'moderation.returned': () => queryClient.invalidateQueries({ queryKey: ['results-evaluations'] }),
  }), [queryClient]);
  useSocketEvents(handlers());

  const filteredEvals = selectedExamId
    ? evaluations.filter((ev) => {
        const ab = ev.answerBookId as unknown as AnswerBook;
        const eid = typeof ab?.examId === 'object' ? (ab.examId as any)._id : ab?.examId;
        return eid === selectedExamId;
      })
    : evaluations;

  // Split into Moderation Queue and Finalized / Certified Results
  const moderationQueue = filteredEvals.filter(
    (ev) => ev.status === 'SUBMITTED' || ev.status === 'UNDER_REVIEW'
  );
  const finalizedResults = filteredEvals.filter(
    (ev) => ev.status === 'APPROVED'
  );

  // Compute summary values from real data
  const totalEvaluated = filteredEvals.filter(
    (ev) => ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'RETURNED'].includes(ev.status)
  ).length;

  const totalCertified = finalizedResults.length;
  const avgMarks = finalizedResults.length > 0
    ? (finalizedResults.reduce((acc, ev) => acc + (ev.totalMarks || 0), 0) / finalizedResults.length).toFixed(1)
    : totalEvaluated > 0
    ? (filteredEvals.reduce((acc, ev) => acc + (ev.totalMarks || 0), 0) / filteredEvals.length).toFixed(1)
    : '0';

  // Export functions using real database data
  const handleExportCSV = () => {
    const records = finalizedResults.length > 0 ? finalizedResults : filteredEvals;
    if (records.length === 0) {
      alert('No evaluation records available for export.');
      return;
    }

    const headers = ['Answer Book Code', 'Student Code', 'Subject Code', 'Examination', 'Examiner', 'Marks', 'Status', 'Certified Date'];
    const rows = records.map((ev) => {
      const ab = ev.answerBookId as unknown as AnswerBook;
      const exam = typeof ab?.examId === 'object' ? (ab.examId as unknown as Exam) : null;
      const examiner = typeof ev.examinerId === 'object' ? (ev.examinerId as unknown as User) : null;

      return [
        ab?.answerBookCode || '—',
        ab?.studentCode || '—',
        exam?.subjectCode || '—',
        `"${exam?.title || '—'}"`,
        `"${examiner?.name || '—'}"`,
        ev.totalMarks ?? 0,
        ev.status,
        ev.submittedAt ? new Date(ev.submittedAt).toLocaleDateString() : '—',
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

  const handleExportJSON = () => {
    const records = finalizedResults.length > 0 ? finalizedResults : filteredEvals;
    if (records.length === 0) {
      alert('No evaluation records available for export.');
      return;
    }

    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(records, null, 2));
    const link = document.createElement('a');
    link.setAttribute('href', dataStr);
    link.setAttribute('download', `evalnexa-results-${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div>
      <div className="page-header">
        <div className="page-header__eyebrow">Control Center · Results Administration</div>
        <h1 className="page-header__title">Examination Results & Certification</h1>
        <p className="page-header__subtitle">
          Tabulate completed evaluations, review pending moderation releases, and export certified result registers.
        </p>
        <div className="page-header__actions" style={{ display: 'flex', gap: 'var(--space-3)' }}>
          <select
            className="form-select"
            style={{ width: 220 }}
            value={selectedExamId}
            onChange={(e) => setSelectedExamId(e.target.value)}
          >
            <option value="">All Examinations</option>
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

      {/* EVALUATION SUMMARY STRIP */}
      <div className="stat-grid" style={{ marginBottom: 'var(--space-8)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Total In Scope</div>
          <div className="stat-card__value">{filteredEvals.length}</div>
          <div className="stat-card__sub">Evaluations recorded</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Evaluated Scripts</div>
          <div className="stat-card__value">{totalEvaluated}</div>
          <div className="stat-card__sub">Marked by examiners</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Pending Moderation</div>
          <div className="stat-card__value" style={{ color: 'var(--status-review-text)' }}>
            {moderationQueue.length}
          </div>
          <div className="stat-card__sub">In moderation review queue</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Certified Results</div>
          <div className="stat-card__value" style={{ color: 'var(--status-approved-text)' }}>
            {totalCertified}
          </div>
          <div className="stat-card__sub">Moderator approved</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Average Marks</div>
          <div className="stat-card__value">{avgMarks}</div>
          <div className="stat-card__sub">Across completed scripts</div>
        </div>
      </div>

      {isLoading ? (
        <div className="state-container"><div className="spinner" /></div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)' }}>
          {/* FINALIZED RESULTS SECTION */}
          <div className="folio-card">
            <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <span className="folio-card__title">Certified Institutional Results ({finalizedResults.length})</span>
                <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  Certified marks with moderator verification
                </div>
              </div>
              {finalizedResults.length > 0 && (
                <span className="label-caps" style={{ color: 'var(--status-approved-text)' }}>
                  ✓ Official Certification Completed
                </span>
              )}
            </div>
            <div className="folio-card__body" style={{ padding: 0 }}>
              {finalizedResults.length === 0 ? (
                <div className="state-container" style={{ padding: 'var(--space-8)' }}>
                  <div className="state-icon">🏛</div>
                  <div className="state-title">Official Results Certification Pending</div>
                  <div className="state-body">
                    Official results are certified only once submitted scripts are reviewed and approved by the Moderation & Quality Center.
                  </div>
                </div>
              ) : (
                <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Student Code</th>
                        <th>Answer Book</th>
                        <th>Examination</th>
                        <th>Accredited Examiner</th>
                        <th>Certified Marks</th>
                        <th>Status</th>
                        <th>Approval Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {finalizedResults.map((ev) => {
                        const ab = ev.answerBookId as unknown as AnswerBook;
                        const exam = typeof ab?.examId === 'object' ? (ab.examId as unknown as Exam) : null;
                        const examiner = typeof ev.examinerId === 'object' ? (ev.examinerId as unknown as User) : null;

                        return (
                          <tr key={ev._id}>
                            <td><span className="data-table__code">{ab?.studentCode || '—'}</span></td>
                            <td><span className="data-table__code">{ab?.answerBookCode || '—'}</span></td>
                            <td>
                              {exam ? (
                                <div>
                                  <div style={{ fontWeight: 500, fontSize: 13 }}>{exam.title}</div>
                                  <div className="label-mono" style={{ fontSize: 10 }}>{exam.subjectCode}</div>
                                </div>
                              ) : '—'}
                            </td>
                            <td>{examiner ? examiner.name : '—'}</td>
                            <td>
                              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700 }}>
                                {ev.totalMarks ?? 0}
                              </span>
                              {exam && (
                                <span className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                  {' '}/ {exam.maximumMarks}
                                </span>
                              )}
                            </td>
                            <td><StatusBadge status={ev.status} /></td>
                            <td className="label-mono" style={{ fontSize: 11 }}>
                              {ev.updatedAt ? new Date(ev.updatedAt).toLocaleDateString() : '—'}
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

          {/* MODERATION QUEUE SECTION */}
          <div className="folio-card">
            <div className="folio-card__header">
              <span className="folio-card__title">Moderation Queue ({moderationQueue.length})</span>
              <span className="label-mono" style={{ fontSize: 11 }}>Awaiting moderator approval before final results release</span>
            </div>
            <div className="folio-card__body" style={{ padding: 0 }}>
              {moderationQueue.length === 0 ? (
                <div className="state-container" style={{ padding: 'var(--space-6)' }}>
                  <div className="state-body">No evaluations are currently pending moderation review.</div>
                </div>
              ) : (
                <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Script Code</th>
                        <th>Examination</th>
                        <th>Examiner</th>
                        <th>Awarded Marks</th>
                        <th>Status</th>
                        <th>Submitted At</th>
                      </tr>
                    </thead>
                    <tbody>
                      {moderationQueue.map((ev) => {
                        const ab = ev.answerBookId as unknown as AnswerBook;
                        const exam = typeof ab?.examId === 'object' ? (ab.examId as unknown as Exam) : null;
                        const examiner = typeof ev.examinerId === 'object' ? (ev.examinerId as unknown as User) : null;

                        return (
                          <tr key={ev._id}>
                            <td><span className="data-table__code">{ab?.answerBookCode || '—'}</span></td>
                            <td>
                              {exam ? (
                                <span style={{ fontWeight: 500, fontSize: 13 }}>{exam.title} ({exam.subjectCode})</span>
                              ) : '—'}
                            </td>
                            <td>{examiner ? examiner.name : '—'}</td>
                            <td>
                              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                                {ev.totalMarks ?? '—'}
                              </span>
                            </td>
                            <td><StatusBadge status={ev.status} /></td>
                            <td className="label-mono" style={{ fontSize: 11 }}>
                              {ev.submittedAt ? new Date(ev.submittedAt).toLocaleString() : '—'}
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
      )}
    </div>
  );
}
