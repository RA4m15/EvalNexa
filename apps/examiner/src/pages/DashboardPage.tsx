import React, { useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Exam } from '@evalnexa/types';
import { getSocket } from '../lib/socket';

export function DashboardPage() {
  const queryClient = useQueryClient();

  // Fetch all scripts assigned to the logged-in examiner
  const { data: allBooks = [], isLoading, isError, refetch } = useQuery<AnswerBook[]>({
    queryKey: ['my-papers'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books/my');
      return data.data;
    },
  });

  // Real-time synchronization via Socket.IO
  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;

    const handleUpdate = () => {
      queryClient.invalidateQueries({ queryKey: ['my-papers'] });
      queryClient.invalidateQueries({ queryKey: ['paper'] });
    };

    socket.on('answerbook.assigned', handleUpdate);
    socket.on('answerbook.status.changed', handleUpdate);
    socket.on('evaluation.started', handleUpdate);
    socket.on('evaluation.updated', handleUpdate);
    socket.on('evaluation.submitted', handleUpdate);
    socket.on('moderation.returned', handleUpdate);
    socket.on('moderation.approved', handleUpdate);
    socket.on('script.finalized', handleUpdate);

    return () => {
      socket.off('answerbook.assigned', handleUpdate);
      socket.off('answerbook.status.changed', handleUpdate);
      socket.off('evaluation.started', handleUpdate);
      socket.off('evaluation.updated', handleUpdate);
      socket.off('evaluation.submitted', handleUpdate);
      socket.off('moderation.returned', handleUpdate);
      socket.off('moderation.approved', handleUpdate);
      socket.off('script.finalized', handleUpdate);
    };
  }, [queryClient]);

  // Real database metrics only
  const assignedCount = allBooks.filter((b) => b.status === 'ASSIGNED').length;
  const inProgressCount = allBooks.filter((b) => b.status === 'IN_PROGRESS').length;
  const submittedCount = allBooks.filter((b) =>
    ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'FINALIZED'].includes(b.status)
  ).length;
  const returnedCount = allBooks.filter((b) => b.status === 'RETURNED').length;

  // Find next priority script (Returned first, then in-progress, then assigned)
  const nextReadyBook =
    allBooks.find((b) => b.status === 'RETURNED') ||
    allBooks.find((b) => b.status === 'IN_PROGRESS') ||
    allBooks.find((b) => b.status === 'ASSIGNED') ||
    null;

  const nextExam = nextReadyBook && typeof nextReadyBook.examId === 'object'
    ? (nextReadyBook.examId as unknown as Exam)
    : null;

  // Current examination context from the most recent or active assigned scripts
  const currentExam = nextExam || (
    allBooks.length > 0 && typeof allBooks[0].examId === 'object'
      ? (allBooks[0].examId as unknown as Exam)
      : null
  );

  return (
    <div style={{ maxWidth: 1240, margin: '0 auto', paddingBottom: 'var(--sp-10)' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--sp-6)', borderBottom: '1px solid var(--border)', paddingBottom: 'var(--sp-4)' }}>
        <div style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--gold)', fontWeight: 600, marginBottom: 4 }}>
          EVALNEXA · DIGITAL EVALUATION DESK
        </div>
        <h1 style={{ fontSize: 42, fontWeight: 700, color: 'var(--navy)', lineHeight: 1.15, margin: '4px 0 8px 0' }}>
          EXAMINER MARKING WORKSPACE
        </h1>
        <p style={{ fontSize: 17, color: 'var(--charcoal)', lineHeight: 1.5, margin: 0 }}>
          Evaluate assigned digital answer scripts and submit verified marks.
        </p>
      </div>

      {/* Current Examination Context Card */}
      {currentExam && (
        <div
          style={{
            background: 'var(--parchment-card)',
            border: '1px solid var(--border)',
            padding: '16px 20px',
            marginBottom: 'var(--sp-6)',
            boxShadow: '0 2px 8px rgba(0,0,0,0.03)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 16,
          }}
        >
          <div>
            <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--gold)', fontWeight: 700 }}>
              CURRENT EXAMINATION
            </div>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--navy)', marginTop: 2 }}>
              {currentExam.title}
            </div>
            <div style={{ fontSize: 15, color: 'var(--charcoal)', marginTop: 2 }}>
              Subject: <strong>{currentExam.subjectName || currentExam.subjectCode}</strong> ({currentExam.subjectCode})
              {currentExam.academicSession ? ` · Session: ${currentExam.academicSession}` : ''}
              {currentExam.maximumMarks ? ` · Max Marks: ${currentExam.maximumMarks}` : ''}
            </div>
          </div>
          <div>
            <span
              style={{
                display: 'inline-block',
                padding: '6px 14px',
                fontSize: 13,
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                background: 'rgba(14,26,43,0.08)',
                color: 'var(--navy)',
                border: '1px solid var(--border)',
              }}
            >
              ACTIVE EXAMINATION
            </span>
          </div>
        </div>
      )}

      {/* Primary Metrics: ASSIGNED, IN PROGRESS, SUBMITTED, RETURNED */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 'var(--sp-4)',
          marginBottom: 'var(--sp-8)',
        }}
      >
        <div
          style={{
            background: 'var(--parchment-card)',
            border: '1px solid var(--border)',
            padding: '20px',
            borderTop: '3px solid var(--navy)',
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--charcoal)' }}>
            ASSIGNED
          </div>
          <div style={{ fontSize: 38, fontWeight: 700, color: 'var(--navy)', marginTop: 6, lineHeight: 1 }}>
            {isLoading ? '—' : assignedCount}
          </div>
          <div style={{ fontSize: 14, color: 'var(--charcoal)', marginTop: 8 }}>
            Ready for marking
          </div>
        </div>

        <div
          style={{
            background: 'var(--parchment-card)',
            border: '1px solid var(--border)',
            padding: '20px',
            borderTop: '3px solid var(--gold)',
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--gold)' }}>
            IN PROGRESS
          </div>
          <div style={{ fontSize: 38, fontWeight: 700, color: inProgressCount > 0 ? '#b45309' : 'var(--navy)', marginTop: 6, lineHeight: 1 }}>
            {isLoading ? '—' : inProgressCount}
          </div>
          <div style={{ fontSize: 14, color: 'var(--charcoal)', marginTop: 8 }}>
            Under active evaluation
          </div>
        </div>

        <div
          style={{
            background: 'var(--parchment-card)',
            border: '1px solid var(--border)',
            padding: '20px',
            borderTop: '3px solid #15803d',
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#15803d' }}>
            SUBMITTED
          </div>
          <div style={{ fontSize: 38, fontWeight: 700, color: '#15803d', marginTop: 6, lineHeight: 1 }}>
            {isLoading ? '—' : submittedCount}
          </div>
          <div style={{ fontSize: 14, color: 'var(--charcoal)', marginTop: 8 }}>
            Transmitted to moderation
          </div>
        </div>

        <div
          style={{
            background: 'var(--parchment-card)',
            border: '1px solid var(--border)',
            padding: '20px',
            borderTop: '3px solid var(--burgundy)',
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--burgundy)' }}>
            RETURNED
          </div>
          <div style={{ fontSize: 38, fontWeight: 700, color: returnedCount > 0 ? 'var(--burgundy)' : 'var(--navy)', marginTop: 6, lineHeight: 1 }}>
            {isLoading ? '—' : returnedCount}
          </div>
          <div style={{ fontSize: 14, color: 'var(--charcoal)', marginTop: 8 }}>
            {returnedCount > 0 ? 'Requires revision' : 'No revisions pending'}
          </div>
        </div>
      </div>

      {/* Priority Section: NEXT SCRIPT TO EVALUATE */}
      <div
        style={{
          background: 'var(--parchment-card)',
          border: '2px solid var(--border)',
          padding: '24px 28px',
          marginBottom: 'var(--sp-8)',
          boxShadow: '0 4px 16px rgba(0,0,0,0.04)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--gold)', fontWeight: 700 }}>
              OPERATIONAL PRIORITY
            </div>
            <h2 style={{ fontSize: 28, fontWeight: 700, color: 'var(--navy)', margin: '4px 0 0 0' }}>
              NEXT SCRIPT TO EVALUATE
            </h2>
          </div>
          {nextReadyBook && (
            <span
              style={{
                padding: '6px 14px',
                fontSize: 13,
                fontWeight: 700,
                textTransform: 'uppercase',
                background: nextReadyBook.status === 'RETURNED' ? 'rgba(92,29,36,0.1)' : 'rgba(14,26,43,0.08)',
                color: nextReadyBook.status === 'RETURNED' ? 'var(--burgundy)' : 'var(--navy)',
                border: '1px solid var(--border)',
              }}
            >
              {nextReadyBook.status.replace(/_/g, ' ')}
            </span>
          )}
        </div>

        {isLoading ? (
          <div style={{ padding: '24px 0', textAlign: 'center', color: 'var(--charcoal)', fontSize: 16 }}>
            Loading assigned examination scripts…
          </div>
        ) : !nextReadyBook ? (
          <div
            style={{
              padding: '32px 20px',
              textAlign: 'center',
              background: 'rgba(255,255,255,0.6)',
              border: '1px dashed var(--border)',
            }}
          >
            <div style={{ fontSize: 28, marginBottom: 8 }}>📋</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--navy)', marginBottom: 4 }}>
              No scripts are currently ready for evaluation.
            </div>
            <p style={{ fontSize: 15, color: 'var(--charcoal)', maxWidth: 480, margin: '0 auto 16px auto', lineHeight: 1.5 }}>
              All allocated answer booklets have either been submitted or no new scripts have been distributed to your docket.
            </p>
            <Link to="/papers" className="btn btn-secondary" style={{ fontSize: 15, padding: '8px 20px' }}>
              View All Scripts Docket
            </Link>
          </div>
        ) : (
          <div>
            {nextReadyBook.status === 'RETURNED' && (
              <div
                style={{
                  background: 'rgba(92, 29, 36, 0.08)',
                  border: '1px solid var(--burgundy)',
                  padding: '12px 16px',
                  marginBottom: 16,
                  color: 'var(--burgundy)',
                  fontSize: 15,
                  lineHeight: 1.5,
                }}
              >
                <strong>⚠ Returned by Moderator for Revision:</strong> This answer book was marked and submitted, but the moderation panel requested review of specific marks before final accreditation.
              </div>
            )}

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: 20,
                alignItems: 'center',
                background: 'rgba(255,255,255,0.7)',
                padding: '20px 24px',
                border: '1px solid var(--border)',
                marginBottom: 20,
              }}
            >
              <div>
                <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--gold)', fontWeight: 700 }}>
                  SCRIPT CODE
                </div>
                <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--navy)', marginTop: 2 }}>
                  {nextReadyBook.answerBookCode}
                </div>
                <div style={{ fontSize: 14, color: 'var(--charcoal)', marginTop: 2 }}>
                  Student Code: <strong>{nextReadyBook.studentCode}</strong>
                </div>
              </div>

              <div>
                <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--gold)', fontWeight: 700 }}>
                  EXAMINATION & SUBJECT
                </div>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--navy)', marginTop: 2 }}>
                  {nextExam ? nextExam.title : 'Official Examination'}
                </div>
                <div style={{ fontSize: 14, color: 'var(--charcoal)', marginTop: 2 }}>
                  {nextExam?.subjectCode} {nextExam?.maximumMarks ? `· Max ${nextExam.maximumMarks} Marks` : ''}
                </div>
              </div>

              <div>
                <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--gold)', fontWeight: 700 }}>
                  PAGES & QUESTIONS
                </div>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--navy)', marginTop: 2 }}>
                  {nextReadyBook.pageCount} Pages Captured
                </div>
                <div style={{ fontSize: 14, color: 'var(--charcoal)', marginTop: 2 }}>
                  {nextExam?.totalQuestions ? `${nextExam.totalQuestions} Questions in rubric` : 'Rubric structured'}
                </div>
              </div>

              <div style={{ textAlign: 'right' }}>
                <Link
                  to={`/evaluate/${nextReadyBook._id}`}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                    background: 'var(--navy)',
                    color: '#ffffff',
                    padding: '14px 28px',
                    fontSize: 17,
                    fontWeight: 700,
                    textDecoration: 'none',
                    border: '1px solid var(--navy)',
                    boxShadow: '0 2px 6px rgba(14,26,43,0.2)',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {nextReadyBook.status === 'IN_PROGRESS'
                    ? 'RESUME MARKING DESK →'
                    : nextReadyBook.status === 'RETURNED'
                    ? 'REVISE RETURNED SCRIPT →'
                    : 'OPEN MARKING DESK →'}
                </Link>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* RECENT SCRIPTS TABLE */}
      <div
        style={{
          background: 'var(--parchment-card)',
          border: '1px solid var(--border)',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '16px 20px',
            borderBottom: '1px solid var(--border)',
          }}
        >
          <div>
            <h3 style={{ fontSize: 24, fontWeight: 700, color: 'var(--navy)', margin: 0 }}>
              Assigned Scripts Docket
            </h3>
            <div style={{ fontSize: 14, color: 'var(--charcoal)', marginTop: 2 }}>
              Verified answer scripts allocated to your examination docket ({allBooks.length})
            </div>
          </div>
          <Link to="/papers" className="btn btn-secondary" style={{ fontSize: 14, padding: '6px 16px' }}>
            View All ({allBooks.length})
          </Link>
        </div>

        <div>
          {isLoading ? (
            <div style={{ padding: '32px 0', textAlign: 'center', color: 'var(--charcoal)', fontSize: 15 }}>
              Loading assigned scripts…
            </div>
          ) : isError ? (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--burgundy)' }}>
              <div>Failed to load assigned scripts.</div>
              <button onClick={() => refetch()} className="btn btn-secondary" style={{ marginTop: 8 }}>
                Retry
              </button>
            </div>
          ) : allBooks.length === 0 ? (
            <div style={{ padding: '32px 20px', textAlign: 'center', color: 'var(--charcoal)' }}>
              <div style={{ fontSize: 24, marginBottom: 6 }}>📭</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--navy)' }}>
                No scripts are currently assigned to your examination docket.
              </div>
              <div style={{ fontSize: 14, marginTop: 4 }}>
                When the examination administration assigns scripts from the Control Center, they will immediately appear here.
              </div>
            </div>
          ) : (
            <table className="data-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'rgba(0,0,0,0.02)', textAlign: 'left', borderBottom: '1px solid var(--border)' }}>
                  <th style={{ padding: '12px 16px', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--gold)', fontWeight: 700 }}>
                    Script Code
                  </th>
                  <th style={{ padding: '12px 16px', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--gold)', fontWeight: 700 }}>
                    Examination
                  </th>
                  <th style={{ padding: '12px 16px', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--gold)', fontWeight: 700 }}>
                    Pages
                  </th>
                  <th style={{ padding: '12px 16px', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--gold)', fontWeight: 700 }}>
                    Status
                  </th>
                  <th style={{ padding: '12px 16px', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--gold)', fontWeight: 700 }}>
                    Last Updated
                  </th>
                  <th style={{ padding: '12px 16px', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--gold)', fontWeight: 700, textAlign: 'right' }}>
                    Action
                  </th>
                </tr>
              </thead>
              <tbody>
                {allBooks.slice(0, 6).map((ab) => {
                  const exam = typeof ab.examId === 'object' ? (ab.examId as unknown as Exam) : null;
                  const canEvaluate = ['ASSIGNED', 'IN_PROGRESS', 'RETURNED'].includes(ab.status);

                  return (
                    <tr key={ab._id} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td style={{ padding: '14px 16px' }}>
                        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--navy)' }}>
                          {ab.answerBookCode}
                        </div>
                        <div style={{ fontSize: 13, color: 'var(--charcoal)' }}>
                          Student: {ab.studentCode}
                        </div>
                      </td>
                      <td style={{ padding: '14px 16px' }}>
                        <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--navy)' }}>
                          {exam ? exam.title : 'Examination'}
                        </div>
                        <div style={{ fontSize: 13, color: 'var(--charcoal)' }}>
                          {exam?.subjectCode || '—'}
                        </div>
                      </td>
                      <td style={{ padding: '14px 16px', fontSize: 15, color: 'var(--navy)' }}>
                        {ab.pageCount} pages
                      </td>
                      <td style={{ padding: '14px 16px' }}>
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '4px 10px',
                            fontSize: 12,
                            fontWeight: 700,
                            letterSpacing: '0.04em',
                            textTransform: 'uppercase',
                            background:
                              ab.status === 'SUBMITTED' || ab.status === 'APPROVED'
                                ? 'rgba(21, 128, 61, 0.1)'
                                : ab.status === 'RETURNED'
                                ? 'rgba(92, 29, 36, 0.1)'
                                : ab.status === 'IN_PROGRESS'
                                ? 'rgba(180, 83, 9, 0.1)'
                                : 'rgba(14, 26, 43, 0.08)',
                            color:
                              ab.status === 'SUBMITTED' || ab.status === 'APPROVED'
                                ? '#15803d'
                                : ab.status === 'RETURNED'
                                ? 'var(--burgundy)'
                                : ab.status === 'IN_PROGRESS'
                                ? '#b45309'
                                : 'var(--navy)',
                            border: '1px solid var(--border)',
                          }}
                        >
                          {ab.status.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td style={{ padding: '14px 16px', fontSize: 14, color: 'var(--charcoal)' }}>
                        {new Date(ab.updatedAt).toLocaleDateString()}
                      </td>
                      <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                        {canEvaluate ? (
                          <Link
                            to={`/evaluate/${ab._id}`}
                            className="btn btn-primary"
                            style={{ fontSize: 14, padding: '6px 16px' }}
                          >
                            {ab.status === 'IN_PROGRESS'
                              ? 'Resume'
                              : ab.status === 'RETURNED'
                              ? 'Revise'
                              : 'Open'}
                          </Link>
                        ) : (
                          <Link
                            to={`/evaluate/${ab._id}`}
                            className="btn btn-secondary"
                            style={{ fontSize: 14, padding: '6px 16px' }}
                          >
                            View Script
                          </Link>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
