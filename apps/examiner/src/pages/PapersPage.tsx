import React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '../lib/apiClient';
import { AnswerBook } from '@evalnexa/types';
import { useEffect } from 'react';
import { getSocket } from '../lib/socket';

export function PapersPage() {
  const queryClient = useQueryClient();

  const { data: papers = [], isLoading, isError } = useQuery<AnswerBook[]>({
    queryKey: ['my-papers'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books/my');
      return data.data;
    },
  });

  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;
    const handler = () => queryClient.invalidateQueries({ queryKey: ['my-papers'] });
    socket.on('answerbook.assigned', handler);
    socket.on('evaluation.submitted', handler);
    socket.on('moderation.returned', handler);
    return () => {
      socket.off('answerbook.assigned', handler);
      socket.off('evaluation.submitted', handler);
      socket.off('moderation.returned', handler);
    };
  }, [queryClient]);

  const statusOrder: Record<string, number> = {
    ASSIGNED: 0, RETURNED: 1, IN_PROGRESS: 2, SUBMITTED: 3, UNDER_REVIEW: 4, APPROVED: 5, FINALIZED: 6,
  };
  const sorted = [...papers].sort((a, b) => (statusOrder[a.status] ?? 99) - (statusOrder[b.status] ?? 99));

  return (
    <div>
      <div className="page-header">
        <div className="page-header__eyebrow">Examiner Workspace · My Papers</div>
        <h1 className="page-header__title">Assigned Answer Books</h1>
        <p className="page-header__subtitle">Only answer books assigned to your account are shown here.</p>
      </div>

      {isLoading ? (
        <div className="state-container"><div className="spinner" /></div>
      ) : isError ? (
        <div className="state-container">
          <div className="state-title">Failed to load papers</div>
          <button className="btn btn-secondary state-action" onClick={() => queryClient.invalidateQueries({ queryKey: ['my-papers'] })}>Retry</button>
        </div>
      ) : sorted.length === 0 ? (
        <div className="state-container">
          <div className="state-icon">📭</div>
          <div className="state-title">No Answer Books Assigned</div>
          <div className="state-body">
            You have no answer books assigned at this time. Please check back after the administrator assigns papers to your account.
          </div>
        </div>
      ) : (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Answer Book Code</th>
                <th>Examination</th>
                <th>Max Marks</th>
                <th>Status</th>
                <th>Assigned</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((ab) => {
                const exam = typeof ab.examId === 'object' ? ab.examId as { title: string; subjectCode: string; maximumMarks: number } : null;
                const canEvaluate = ['ASSIGNED', 'IN_PROGRESS', 'RETURNED'].includes(ab.status);
                return (
                  <tr key={ab._id}>
                    <td><span className="data-table__code">{ab.answerBookCode}</span></td>
                    <td>
                      {exam ? (
                        <div>
                          <div style={{ fontWeight: 500, fontSize: 13 }}>{exam.title}</div>
                          <div className="label-mono" style={{ fontSize: 10 }}>{exam.subjectCode}</div>
                        </div>
                      ) : '—'}
                    </td>
                    <td>{exam?.maximumMarks ?? '—'}</td>
                    <td>
                      <span className={`status-badge status-badge--${ab.status.toLowerCase().replace(/_/g, '_')}`}>
                        {ab.status.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="label-mono" style={{ fontSize: 11 }}>
                      {new Date(ab.createdAt).toLocaleDateString()}
                    </td>
                    <td>
                      {canEvaluate ? (
                        <Link to={`/papers/${ab._id}`} className="btn btn-primary btn-sm">
                          {ab.status === 'IN_PROGRESS' ? 'Continue →' : 'Evaluate →'}
                        </Link>
                      ) : (
                        <span className="label-mono" style={{ fontSize: 10, color: 'var(--text-faint)' }}>
                          {ab.status === 'SUBMITTED' ? 'Under review' : '—'}
                        </span>
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
  );
}
