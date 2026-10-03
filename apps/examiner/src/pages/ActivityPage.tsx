import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Exam } from '@evalnexa/types';

export function ActivityPage() {
  const { data: answerBooks = [], isLoading } = useQuery<AnswerBook[]>({
    queryKey: ['my-papers-activity'],
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
    <div style={{ maxWidth: 1240, margin: '0 auto', paddingBottom: 'var(--sp-10)' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--sp-6)', borderBottom: '1px solid var(--border)', paddingBottom: 'var(--sp-4)' }}>
        <div style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--gold)', fontWeight: 600, marginBottom: 4 }}>
          EXAMINER WORKSPACE · OPERATIONAL AUDIT
        </div>
        <h1 style={{ fontSize: 42, fontWeight: 700, color: 'var(--navy)', lineHeight: 1.15, margin: '4px 0 8px 0' }}>
          ACTIVITY & MARKING HISTORY
        </h1>
        <p style={{ fontSize: 17, color: 'var(--charcoal)', lineHeight: 1.5, margin: 0 }}>
          Personal examination docket audit, session timeline, and evaluated booklet records.
        </p>
      </div>

      {/* Metric Cards */}
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
            TOTAL ASSIGNED
          </div>
          <div style={{ fontSize: 38, fontWeight: 700, color: 'var(--navy)', marginTop: 6, lineHeight: 1 }}>
            {isLoading ? '—' : totalAssigned}
          </div>
          <div style={{ fontSize: 14, color: 'var(--charcoal)', marginTop: 8 }}>
            Total in examination docket
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
          <div style={{ fontSize: 38, fontWeight: 700, color: inProgress > 0 ? '#b45309' : 'var(--navy)', marginTop: 6, lineHeight: 1 }}>
            {isLoading ? '—' : inProgress}
          </div>
          <div style={{ fontSize: 14, color: 'var(--charcoal)', marginTop: 8 }}>
            Currently under evaluation
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
            {isLoading ? '—' : submitted}
          </div>
          <div style={{ fontSize: 14, color: 'var(--charcoal)', marginTop: 8 }}>
            Successfully transmitted
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
          <div style={{ fontSize: 38, fontWeight: 700, color: returned > 0 ? 'var(--burgundy)' : 'var(--navy)', marginTop: 6, lineHeight: 1 }}>
            {isLoading ? '—' : returned}
          </div>
          <div style={{ fontSize: 14, color: 'var(--charcoal)', marginTop: 8 }}>
            Returned for revision
          </div>
        </div>
      </div>

      {/* History Table */}
      <div
        style={{
          background: 'var(--parchment-card)',
          border: '1px solid var(--border)',
        }}
      >
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
          <h3 style={{ fontSize: 24, fontWeight: 700, color: 'var(--navy)', margin: 0 }}>
            Marking Activity Log
          </h3>
          <div style={{ fontSize: 14, color: 'var(--charcoal)', marginTop: 2 }}>
            Chronological audit of evaluation actions and booklet status updates
          </div>
        </div>

        <div>
          {isLoading ? (
            <div style={{ padding: '32px 0', textAlign: 'center', color: 'var(--charcoal)', fontSize: 15 }}>
              Loading marking history…
            </div>
          ) : answerBooks.length === 0 ? (
            <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--charcoal)' }}>
              <div style={{ fontSize: 28, marginBottom: 8 }}>📊</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--navy)' }}>
                No evaluation activity recorded yet.
              </div>
              <div style={{ fontSize: 14, marginTop: 4 }}>
                Activity will appear as scripts are assigned, evaluated, and submitted.
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
                    Assigned Date
                  </th>
                  <th style={{ padding: '12px 16px', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--gold)', fontWeight: 700, textAlign: 'right' }}>
                    Action
                  </th>
                </tr>
              </thead>
              <tbody>
                {answerBooks.map((ab) => {
                  const exam = typeof ab.examId === 'object' ? (ab.examId as unknown as Exam) : null;
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
                        {new Date(ab.createdAt).toLocaleDateString()}
                      </td>
                      <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                        <Link
                          to={`/evaluate/${ab._id}`}
                          className="btn btn-secondary"
                          style={{ fontSize: 14, padding: '6px 16px' }}
                        >
                          View Docket
                        </Link>
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
