import React, { useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '../lib/apiClient';
import { Evaluation, AnswerBook, Exam, User } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';
import { getSocket } from '../lib/socket';

export function ReviewQueuePage() {
  const queryClient = useQueryClient();

  const { data: evaluations = [], isLoading, isError } = useQuery<Evaluation[]>({
    queryKey: ['moderation-queue'],
    queryFn: async () => {
      const { data } = await apiClient.get('/moderation');
      return data.data;
    },
  });

  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;
    const handler = () => queryClient.invalidateQueries({ queryKey: ['moderation-queue'] });
    socket.on('evaluation.submitted', handler);
    socket.on('moderation.approved', handler);
    socket.on('moderation.returned', handler);
    return () => {
      socket.off('evaluation.submitted', handler);
      socket.off('moderation.approved', handler);
      socket.off('moderation.returned', handler);
    };
  }, [queryClient]);

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Moderation & Quality Center · Review Docket</div>
          <h1 className="page-header__title">Evaluation Review Queue</h1>
          <p className="page-header__subtitle">
            Structured moderation queue of submitted scripts requiring second-examiner clearance and certification.
          </p>
        </div>
        <div className="page-header__actions">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px', background: 'rgba(14,26,43,0.05)', borderRadius: 'var(--radius-sm)' }}>
            <div className="live-dot" />
            <span className="label-mono" style={{ fontSize: 10, letterSpacing: '0.08em' }}>REAL-TIME QUEUE</span>
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="state-container"><div className="spinner" /></div>
      ) : isError ? (
        <div className="state-container">
          <div className="state-title">Failed to load review queue</div>
          <button className="btn btn-secondary state-action" onClick={() => queryClient.invalidateQueries({ queryKey: ['moderation-queue'] })}>
            Retry
          </button>
        </div>
      ) : evaluations.length === 0 ? (
        <div className="state-container">
          <div className="state-icon">✓</div>
          <div className="state-title">Review Queue Clear</div>
          <div className="state-body">
            No evaluations are currently pending moderation. When examiners complete and submit marking on their workspace, scripts appear here automatically.
          </div>
        </div>
      ) : (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Answer Book</th>
                <th>Exam</th>
                <th>Examiner</th>
                <th>Total Marks</th>
                <th>Submitted At</th>
                <th>Review Reason</th>
                <th>Priority</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {evaluations.map((ev) => {
                const ab = typeof ev.answerBookId === 'object' ? (ev.answerBookId as unknown as AnswerBook) : null;
                const exam = ab && typeof ab.examId === 'object' ? (ab.examId as unknown as Exam) : null;
                const examiner = typeof ev.examinerId === 'object' ? (ev.examinerId as unknown as User) : null;

                // Priority determination from backend flags:
                const hasFlags = ev.questionMarks?.some((q) => q.status === 'FLAGGED');
                const isReturned = ev.status === 'RETURNED';
                const priority = isReturned || hasFlags ? 'HIGH PRIORITY' : ev.remarks ? 'REVIEW' : 'NORMAL';

                return (
                  <tr key={ev._id}>
                    <td>
                      <span className="data-table__code">{ab?.answerBookCode || '—'}</span>
                      <div className="label-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                        {ab?.studentCode}
                      </div>
                    </td>
                    <td>
                      {exam ? (
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 500 }}>{exam.title}</div>
                          <div className="label-mono" style={{ fontSize: 10 }}>{exam.subjectCode}</div>
                        </div>
                      ) : '—'}
                    </td>
                    <td>
                      {examiner ? (
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 500 }}>{examiner.name}</div>
                          <div className="label-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{examiner.email}</div>
                        </div>
                      ) : '—'}
                    </td>
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
                    <td className="label-mono" style={{ fontSize: 11 }}>
                      {ev.submittedAt ? new Date(ev.submittedAt).toLocaleString() : '—'}
                    </td>
                    <td style={{ fontSize: 12, maxWidth: 200, color: ev.remarks ? 'inherit' : 'var(--text-muted)' }}>
                      {ev.remarks || 'Standard routine submission'}
                    </td>
                    <td>
                      <span
                        className="label-mono"
                        style={{
                          fontSize: 9.5,
                          fontWeight: 700,
                          padding: '2px 6px',
                          borderRadius: 2,
                          background:
                            priority === 'HIGH PRIORITY'
                              ? 'var(--status-returned-bg)'
                              : priority === 'REVIEW'
                              ? 'var(--status-review-bg)'
                              : 'var(--parchment-border)',
                          color:
                            priority === 'HIGH PRIORITY'
                              ? 'var(--status-returned-text)'
                              : priority === 'REVIEW'
                              ? 'var(--status-review-text)'
                              : 'var(--text-muted)',
                        }}
                      >
                        {priority}
                      </span>
                    </td>
                    <td><StatusBadge status={ev.status} /></td>
                    <td style={{ textAlign: 'right' }}>
                      <Link to={`/review/${ev._id}`} className="btn btn-primary btn-sm">
                        Open Review →
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
