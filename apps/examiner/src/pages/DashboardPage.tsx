import React, { useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Exam } from '@evalnexa/types';
import { getSocket } from '../lib/socket';

export function DashboardPage() {
  const queryClient = useQueryClient();

  const { data: allBooks = [], isLoading } = useQuery<AnswerBook[]>({
    queryKey: ['my-papers'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books/my');
      return data.data;
    },
  });

  // Real-time: re-fetch when assigned or updated
  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;
    const handler = () => queryClient.invalidateQueries({ queryKey: ['my-papers'] });
    socket.on('answerbook.assigned', handler);
    socket.on('answerbook.status.changed', handler);
    socket.on('moderation.approved', handler);
    socket.on('moderation.returned', handler);
    return () => {
      socket.off('answerbook.assigned', handler);
      socket.off('answerbook.status.changed', handler);
      socket.off('moderation.approved', handler);
      socket.off('moderation.returned', handler);
    };
  }, [queryClient]);

  // Real database metrics only
  const assignedCount = allBooks.length;
  const inProgressCount = allBooks.filter((b) => b.status === 'IN_PROGRESS').length;
  const submittedCount = allBooks.filter((b) =>
    ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'FINALIZED'].includes(b.status)
  ).length;
  const flagsCount = allBooks.filter((b) => b.status === 'RETURNED').length;

  // Find next assigned answer book for "Ready for Evaluation" hero
  const nextReadyBook =
    allBooks.find((b) => b.status === 'IN_PROGRESS') ||
    allBooks.find((b) => b.status === 'RETURNED') ||
    allBooks.find((b) => b.status === 'ASSIGNED') ||
    null;

  const nextExam = nextReadyBook && typeof nextReadyBook.examId === 'object'
    ? (nextReadyBook.examId as unknown as Exam)
    : null;

  return (
    <div>
      {/* Header */}
      <div className="page-header" style={{ marginBottom: 'var(--space-6)' }}>
        <div>
          <div className="page-header__eyebrow">Examiner Workspace · On-Screen Evaluation</div>
          <h1 className="page-header__title">Examiner Marking Workspace</h1>
          <p className="page-header__subtitle">
            Review assigned digital scripts and record examination marks.
          </p>
        </div>
        <div className="page-header__actions">
          <Link to="/papers" className="btn btn-secondary">
            View All Assigned Scripts ({assignedCount})
          </Link>
        </div>
      </div>

      {/* Top Metrics: Assigned Scripts, In Progress, Submitted, Review Flags */}
      <div className="stat-grid" style={{ marginBottom: 'var(--space-8)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow">ASSIGNED SCRIPTS</div>
          <div className="stat-card__value">{isLoading ? '—' : assignedCount}</div>
          <div className="stat-card__sub">Total in personal docket</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">IN PROGRESS</div>
          <div className="stat-card__value" style={{ color: inProgressCount > 0 ? 'var(--status-review-text)' : 'inherit' }}>
            {isLoading ? '—' : inProgressCount}
          </div>
          <div className="stat-card__sub">Marking in progress</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">SUBMITTED</div>
          <div className="stat-card__value" style={{ color: 'var(--status-approved-text)' }}>
            {isLoading ? '—' : submittedCount}
          </div>
          <div className="stat-card__sub">Transmitted to moderation</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">REVIEW FLAGS</div>
          <div className="stat-card__value" style={{ color: flagsCount > 0 ? 'var(--status-returned-text)' : 'inherit' }}>
            {isLoading ? '—' : flagsCount}
          </div>
          <div className="stat-card__sub">{flagsCount > 0 ? 'Returned by moderator' : 'No items returned'}</div>
        </div>
      </div>

      {/* READY TO GRADE (Large hero area inspired by reference) */}
      {nextReadyBook && (
        <div
          className="folio-card"
          style={{
            marginBottom: 'var(--space-8)',
            border: '2px solid var(--parchment-border)',
            background: 'linear-gradient(135deg, rgba(255,255,255,0.7) 0%, rgba(247,244,238,0.9) 100%)',
          }}
        >
          <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span className="label-caps" style={{ color: 'var(--status-review-text)', letterSpacing: '0.14em' }}>
                STATUS · READY FOR EVALUATION
              </span>
              <div className="folio-card__title" style={{ fontSize: '1.25rem', marginTop: 2 }}>
                Next Priority Script in Queue
              </div>
            </div>
            <span
              className="label-mono"
              style={{
                fontSize: 11,
                padding: '4px 10px',
                borderRadius: 2,
                background: nextReadyBook.status === 'RETURNED' ? 'var(--status-returned-bg)' : 'rgba(14,26,43,0.06)',
                color: nextReadyBook.status === 'RETURNED' ? 'var(--status-returned-text)' : 'inherit',
                fontWeight: 600,
              }}
            >
              {nextReadyBook.status.replace(/_/g, ' ')}
            </span>
          </div>

          <div className="folio-card__body">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-5)', alignItems: 'center' }}>
              <div>
                <div className="label-caps">SCRIPT CODE</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, color: 'var(--parchment-navy)', marginTop: 2 }}>
                  {nextReadyBook.answerBookCode}
                </div>
                <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  Student: {nextReadyBook.studentCode} · {nextReadyBook.pageCount} Pages
                </div>
              </div>

              <div>
                <div className="label-caps">EXAMINATION</div>
                <div style={{ fontFamily: 'var(--font-serif)', fontSize: 16, fontWeight: 600, marginTop: 2 }}>
                  {nextExam ? nextExam.title : 'Official Examination'}
                </div>
                <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {nextExam?.subjectCode} · Max {nextExam?.maximumMarks || '—'} Marks
                </div>
              </div>

              <div>
                <div className="label-caps">ESTIMATED QUESTIONS</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 600, marginTop: 2 }}>
                  {nextExam ? `${nextExam.totalQuestions} Questions` : 'Questions on record'}
                </div>
                <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  Sequential on-screen marking
                </div>
              </div>

              <div style={{ textAlign: 'right' }}>
                <Link
                  to={`/papers/${nextReadyBook._id}`}
                  className="btn btn-primary btn-lg"
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  {nextReadyBook.status === 'IN_PROGRESS' ? 'Resume Marking Screen →' : 'Open Marking Screen →'}
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MY VERIFIED SCRIPTS TABLE */}
      <div className="folio-card">
        <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="folio-card__title">My Verified Scripts ({allBooks.length})</span>
            <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              Accredited digital booklets allocated to your docket
            </div>
          </div>
          <Link to="/papers" className="btn btn-ghost btn-sm">
            View All Scripts
          </Link>
        </div>

        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoading ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : allBooks.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-8)' }}>
              <div className="state-icon">📋</div>
              <div className="state-title">No Scripts Assigned</div>
              <div className="state-body">
                You have no digital answer books assigned at this time. The examination administrator will distribute script batches to your docket.
              </div>
            </div>
          ) : (
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Script Code</th>
                    <th>Exam</th>
                    <th>Page Count</th>
                    <th>Question Progress</th>
                    <th>Status</th>
                    <th>Last Updated</th>
                    <th style={{ textAlign: 'right' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {allBooks.map((ab) => {
                    const exam = typeof ab.examId === 'object' ? (ab.examId as unknown as Exam) : null;
                    const canMark = ['ASSIGNED', 'IN_PROGRESS', 'RETURNED'].includes(ab.status);

                    return (
                      <tr key={ab._id}>
                        <td>
                          <span className="data-table__code">{ab.answerBookCode}</span>
                          <div className="label-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                            {ab.studentCode}
                          </div>
                        </td>
                        <td>
                          {exam ? (
                            <div>
                              <div style={{ fontWeight: 500, fontSize: 13 }}>{exam.title}</div>
                              <div className="label-mono" style={{ fontSize: 10 }}>{exam.subjectCode}</div>
                            </div>
                          ) : '—'}
                        </td>
                        <td>{ab.pageCount} pages</td>
                        <td>
                          <span className="label-mono" style={{ fontSize: 12 }}>
                            {exam ? `${exam.totalQuestions} Questions` : '—'}
                          </span>
                        </td>
                        <td>
                          <span className={`status-badge status-badge--${ab.status.toLowerCase().replace('_', '-')}`}>
                            {ab.status.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td className="label-mono" style={{ fontSize: 11 }}>
                          {new Date(ab.updatedAt).toLocaleDateString()}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          {canMark ? (
                            <Link to={`/papers/${ab._id}`} className="btn btn-primary btn-sm">
                              {ab.status === 'IN_PROGRESS' ? 'Resume' : 'Open'}
                            </Link>
                          ) : (
                            <Link to={`/papers/${ab._id}`} className="btn btn-ghost btn-sm">
                              View
                            </Link>
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
