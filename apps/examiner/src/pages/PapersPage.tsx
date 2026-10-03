import React, { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Exam } from '@evalnexa/types';
import { getSocket } from '../lib/socket';

export function PapersPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [examFilter, setExamFilter] = useState<string>('ALL');
  const [selectedReturnNote, setSelectedReturnNote] = useState<{ code: string; reason: string; id: string } | null>(null);

  const { data: papers = [], isLoading, isError, refetch } = useQuery<AnswerBook[]>({
    queryKey: ['my-papers'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books/my');
      return data.data;
    },
  });

  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;

    const handleUpdate = () => {
      queryClient.invalidateQueries({ queryKey: ['my-papers'] });
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

  // Extract unique exams for filter
  const uniqueExams = Array.from(
    new Map(
      papers
        .map((p) => (typeof p.examId === 'object' ? (p.examId as unknown as Exam) : null))
        .filter((e): e is Exam => Boolean(e && e._id))
        .map((e) => [e._id, e])
    ).values()
  );

  // Filter papers
  const filteredPapers = papers.filter((p) => {
    if (statusFilter !== 'ALL' && p.status !== statusFilter) return false;
    if (examFilter !== 'ALL') {
      const examId = typeof p.examId === 'object' ? (p.examId as any)._id : p.examId;
      if (examId !== examFilter) return false;
    }
    return true;
  });

  return (
    <div style={{ maxWidth: 1240, margin: '0 auto', paddingBottom: 'var(--sp-10)' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--sp-6)', borderBottom: '1px solid var(--border)', paddingBottom: 'var(--sp-4)' }}>
        <div style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--gold)', fontWeight: 600, marginBottom: 4 }}>
          EXAMINER WORKSPACE · SCRIPTS DOCKET
        </div>
        <h1 style={{ fontSize: 42, fontWeight: 700, color: 'var(--navy)', lineHeight: 1.15, margin: '4px 0 8px 0' }}>
          MY DIGITAL SCRIPTS
        </h1>
        <p style={{ fontSize: 17, color: 'var(--charcoal)', lineHeight: 1.5, margin: 0 }}>
          All digitized answer books assigned to your examination docket.
        </p>
      </div>

      {/* Filters Bar */}
      <div
        style={{
          background: 'var(--parchment-card)',
          border: '1px solid var(--border)',
          padding: '16px 20px',
          marginBottom: 'var(--sp-6)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 16,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          <div>
            <label style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--gold)', fontWeight: 700, display: 'block', marginBottom: 4 }}>
              Status Filter
            </label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{
                fontFamily: 'Cambria',
                fontSize: 15,
                padding: '6px 12px',
                border: '1px solid var(--border)',
                background: '#ffffff',
                color: 'var(--ink)',
              }}
            >
              <option value="ALL">All Statuses ({papers.length})</option>
              <option value="ASSIGNED">Assigned ({papers.filter((p) => p.status === 'ASSIGNED').length})</option>
              <option value="IN_PROGRESS">In Progress ({papers.filter((p) => p.status === 'IN_PROGRESS').length})</option>
              <option value="SUBMITTED">Submitted ({papers.filter((p) => ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED'].includes(p.status)).length})</option>
              <option value="RETURNED">Returned ({papers.filter((p) => p.status === 'RETURNED').length})</option>
            </select>
          </div>

          {uniqueExams.length > 0 && (
            <div>
              <label style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--gold)', fontWeight: 700, display: 'block', marginBottom: 4 }}>
                Examination
              </label>
              <select
                value={examFilter}
                onChange={(e) => setExamFilter(e.target.value)}
                style={{
                  fontFamily: 'Cambria',
                  fontSize: 15,
                  padding: '6px 12px',
                  border: '1px solid var(--border)',
                  background: '#ffffff',
                  color: 'var(--ink)',
                }}
              >
                <option value="ALL">All Examinations</option>
                {uniqueExams.map((e) => (
                  <option key={e._id} value={e._id}>
                    {e.title} ({e.subjectCode})
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div style={{ fontSize: 15, color: 'var(--charcoal)' }}>
          Showing <strong>{filteredPapers.length}</strong> of {papers.length} assigned scripts
        </div>
      </div>

      {/* Main Table */}
      <div
        style={{
          background: 'var(--parchment-card)',
          border: '1px solid var(--border)',
        }}
      >
        {isLoading ? (
          <div style={{ padding: '48px 0', textAlign: 'center', color: 'var(--charcoal)', fontSize: 16 }}>
            Loading assigned digital scripts…
          </div>
        ) : isError ? (
          <div style={{ padding: '32px', textAlign: 'center', color: 'var(--burgundy)' }}>
            <div style={{ fontSize: 18, fontWeight: 700 }}>Unable to load assigned scripts.</div>
            <button onClick={() => refetch()} className="btn btn-secondary" style={{ marginTop: 12 }}>
              Retry
            </button>
          </div>
        ) : filteredPapers.length === 0 ? (
          <div style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--charcoal)' }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>📭</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--navy)' }}>
              No scripts are currently assigned to your examination docket.
            </div>
            <p style={{ fontSize: 15, maxWidth: 500, margin: '8px auto 0 auto', lineHeight: 1.5 }}>
              {statusFilter !== 'ALL' || examFilter !== 'ALL'
                ? 'No scripts match the selected filter criteria. Try resetting the filters above.'
                : 'Please check back after the administrator distributes examination scripts to your account.'}
            </p>
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
                  Progress
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
              {filteredPapers.map((ab) => {
                const exam = typeof ab.examId === 'object' ? (ab.examId as unknown as Exam) : null;
                const canEvaluate = ['ASSIGNED', 'IN_PROGRESS', 'RETURNED'].includes(ab.status);
                const isReturned = ab.status === 'RETURNED';

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
                        {exam?.subjectCode} {exam?.maximumMarks ? `(Max ${exam.maximumMarks}m)` : ''}
                      </div>
                    </td>
                    <td style={{ padding: '14px 16px', fontSize: 15, color: 'var(--navy)' }}>
                      {ab.pageCount} pages
                    </td>
                    <td style={{ padding: '14px 16px', fontSize: 14, color: 'var(--charcoal)' }}>
                      {exam?.totalQuestions ? `${exam.totalQuestions} Questions` : '—'}
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
                      <div style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                        {isReturned && (
                          <button
                            className="btn btn-secondary"
                            style={{ fontSize: 13, padding: '5px 12px', color: 'var(--burgundy)', borderColor: 'var(--burgundy)' }}
                            onClick={() => {
                              setSelectedReturnNote({
                                code: ab.answerBookCode,
                                reason: (ab as any).remarks || 'Moderator returned this evaluation docket requesting verification of marks or justification notes before approval.',
                                id: ab._id,
                              });
                            }}
                          >
                            Review Return Note
                          </button>
                        )}
                        {canEvaluate ? (
                          <Link
                            to={`/evaluate/${ab._id}`}
                            className="btn btn-primary"
                            style={{ fontSize: 14, padding: '6px 16px' }}
                          >
                            {ab.status === 'IN_PROGRESS'
                              ? 'Resume'
                              : isReturned
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
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Return Note Modal */}
      {selectedReturnNote && (
        <div
          className="modal-backdrop"
          onClick={(e) => e.target === e.currentTarget && setSelectedReturnNote(null)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(14,26,43,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: '#ffffff',
              border: '2px solid var(--border)',
              padding: 24,
              maxWidth: 520,
              width: '90%',
              boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
            }}
          >
            <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--burgundy)', fontWeight: 700 }}>
              MODERATOR RETURN NOTE
            </div>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--navy)', margin: '4px 0 12px 0' }}>
              Script {selectedReturnNote.code}
            </div>
            <div
              style={{
                background: 'rgba(92,29,36,0.06)',
                border: '1px solid var(--burgundy)',
                padding: '14px 16px',
                fontSize: 15,
                color: 'var(--burgundy)',
                lineHeight: 1.5,
                marginBottom: 20,
              }}
            >
              <strong>Moderator Feedback:</strong>
              <div style={{ marginTop: 6, fontStyle: 'italic' }}>
                "{selectedReturnNote.reason}"
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button
                className="btn btn-secondary"
                onClick={() => setSelectedReturnNote(null)}
                style={{ fontSize: 14, padding: '8px 16px' }}
              >
                Close
              </button>
              <Link
                to={`/evaluate/${selectedReturnNote.id}`}
                className="btn btn-primary"
                style={{ fontSize: 14, padding: '8px 20px', background: 'var(--navy)', color: '#ffffff' }}
              >
                Open for Revision →
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
