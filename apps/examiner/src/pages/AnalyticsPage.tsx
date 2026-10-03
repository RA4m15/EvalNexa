import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Exam } from '@evalnexa/types';

export function AnalyticsPage() {
  const { data: answerBooks = [], isLoading } = useQuery<AnswerBook[]>({
    queryKey: ['my-papers-analytics'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books/my');
      return data.data;
    },
  });

  const totalAssigned = answerBooks.length;
  const inProgress = answerBooks.filter((b) => b.status === 'IN_PROGRESS').length;
  const submitted = answerBooks.filter((b) =>
    ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'FINALIZED'].includes(b.status)
  ).length;
  const returned = answerBooks.filter((b) => b.status === 'RETURNED').length;

  return (
    <div>
      <div className="page-header">
        <div className="page-header__eyebrow">Examiner Workspace · Evaluation Telemetry</div>
        <h1 className="page-header__title">Evaluation Analytics</h1>
        <p className="page-header__subtitle">
          Personal marking volume, throughput metrics, and docket completion records.
        </p>
      </div>

      {/* METRIC STRIP */}
      <div className="stat-grid" style={{ marginBottom: 'var(--space-8)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow">TOTAL ASSIGNED</div>
          <div className="stat-card__value">{isLoading ? '—' : totalAssigned}</div>
          <div className="stat-card__sub">Answer books in personal docket</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">IN PROGRESS</div>
          <div className="stat-card__value" style={{ color: inProgress > 0 ? 'var(--status-review-text)' : 'inherit' }}>
            {isLoading ? '—' : inProgress}
          </div>
          <div className="stat-card__sub">Active marking sessions</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">SUBMITTED</div>
          <div className="stat-card__value" style={{ color: 'var(--status-approved-text)' }}>
            {isLoading ? '—' : submitted}
          </div>
          <div className="stat-card__sub">Transmitted to moderation</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">RETURNED FOR REVIEW</div>
          <div className="stat-card__value" style={{ color: returned > 0 ? 'var(--status-returned-text)' : 'inherit' }}>
            {isLoading ? '—' : returned}
          </div>
          <div className="stat-card__sub">Requires examiner attention</div>
        </div>
      </div>

      {/* DOCKET BREAKDOWN */}
      <div className="folio-card">
        <div className="folio-card__header">
          <span className="folio-card__title">Assigned Scripts Completion Roster ({answerBooks.length})</span>
        </div>
        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoading ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : answerBooks.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-8)' }}>
              <div className="state-icon">📊</div>
              <div className="state-title">No Evaluation Data Recorded</div>
              <div className="state-body">
                Evaluation metrics will populate automatically as examination answer books are assigned and marked.
              </div>
            </div>
          ) : (
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Answer Book</th>
                    <th>Examination</th>
                    <th>Page Count</th>
                    <th>Status</th>
                    <th>Assigned Date</th>
                    <th>Last Active</th>
                  </tr>
                </thead>
                <tbody>
                  {answerBooks.map((ab) => {
                    const exam = typeof ab.examId === 'object' ? (ab.examId as unknown as Exam) : null;
                    return (
                      <tr key={ab._id}>
                        <td><span className="data-table__code">{ab.answerBookCode}</span></td>
                        <td>{exam ? `${exam.title} (${exam.subjectCode})` : '—'}</td>
                        <td>{ab.pageCount} pages</td>
                        <td>
                          <span className={`status-badge status-badge--${ab.status.toLowerCase().replace(/_/g, '-')}`}>
                            {ab.status.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td className="label-mono" style={{ fontSize: 11 }}>
                          {new Date(ab.createdAt).toLocaleDateString()}
                        </td>
                        <td className="label-mono" style={{ fontSize: 11 }}>
                          {new Date(ab.updatedAt).toLocaleTimeString()} · {new Date(ab.updatedAt).toLocaleDateString()}
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
