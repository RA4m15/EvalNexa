import React, { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Exam, User } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';
import { useSocketEvents } from '../hooks/useSocketEvents';

export function MonitoringPage() {
  const queryClient = useQueryClient();
  const [selectedExamId, setSelectedExamId] = useState<string>('');

  const { data: answerBooks = [], isLoading: isLoadingBooks } = useQuery<AnswerBook[]>({
    queryKey: ['monitoring-books'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books');
      return data.data;
    },
    refetchInterval: 10000,
  });

  const { data: exams = [] } = useQuery<Exam[]>({
    queryKey: ['monitoring-exams'],
    queryFn: async () => {
      const { data } = await apiClient.get('/exams');
      return data.data;
    },
  });

  const { data: examiners = [] } = useQuery<User[]>({
    queryKey: ['monitoring-examiners'],
    queryFn: async () => {
      const { data } = await apiClient.get('/users?role=EXAMINER');
      return data.data;
    },
  });

  const handlers = useCallback(() => ({
    'answerbook.assigned': () => queryClient.invalidateQueries({ queryKey: ['monitoring-books'] }),
    'answerbook.status.changed': () => queryClient.invalidateQueries({ queryKey: ['monitoring-books'] }),
    'evaluation.started': () => queryClient.invalidateQueries({ queryKey: ['monitoring-books'] }),
    'evaluation.updated': () => queryClient.invalidateQueries({ queryKey: ['monitoring-books'] }),
    'evaluation.submitted': () => queryClient.invalidateQueries({ queryKey: ['monitoring-books'] }),
    'moderation.approved': () => queryClient.invalidateQueries({ queryKey: ['monitoring-books'] }),
    'moderation.returned': () => queryClient.invalidateQueries({ queryKey: ['monitoring-books'] }),
  }), [queryClient]);
  useSocketEvents(handlers());

  // Filter books by selected exam if any
  const filteredBooks = selectedExamId
    ? answerBooks.filter((b) => {
        const eid = typeof b.examId === 'object' ? (b.examId as any)._id : b.examId;
        return eid === selectedExamId;
      })
    : answerBooks;

  // Breakdown metrics
  const totalScripts = filteredBooks.length;
  const assigned = filteredBooks.filter((b) => b.status === 'ASSIGNED');
  const inProgress = filteredBooks.filter((b) => b.status === 'IN_PROGRESS');
  const submitted = filteredBooks.filter((b) => b.status === 'SUBMITTED');
  const underReview = filteredBooks.filter((b) => b.status === 'UNDER_REVIEW');
  const approved = filteredBooks.filter((b) => b.status === 'APPROVED' || b.status === 'FINALIZED');

  // Compute examiner activity from real data
  const examinerActivity = examiners.map((ex) => {
    const exBooks = filteredBooks.filter((b) => {
      const examinerId = typeof b.assignedExaminerId === 'object' ? (b.assignedExaminerId as any)?._id : b.assignedExaminerId;
      return examinerId === ex._id;
    });

    return {
      examiner: ex,
      assigned: exBooks.length,
      inProgress: exBooks.filter((b) => b.status === 'IN_PROGRESS').length,
      submitted: exBooks.filter((b) => b.status === 'SUBMITTED' || b.status === 'UNDER_REVIEW' || b.status === 'APPROVED').length,
    };
  });

  return (
    <div>
      <div className="page-header">
        <div className="page-header__eyebrow">Control Center · Live Operations</div>
        <h1 className="page-header__title">Live Examination Monitoring</h1>
        <p className="page-header__subtitle">
          Real-time oversight of examiner marking dockets, session completion rates, and moderation transitions.
        </p>
        <div className="page-header__actions" style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
          <select
            className="form-select"
            style={{ width: 260 }}
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
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px', background: 'rgba(14, 26, 43, 0.05)', borderRadius: 'var(--radius-sm)' }}>
            <div className="live-dot" />
            <span className="label-mono" style={{ fontSize: 10, letterSpacing: '0.08em' }}>SOCKET.IO LIVE</span>
          </div>
        </div>
      </div>

      {/* METRIC STRIP (Exact requirements from prompt) */}
      <div className="stat-grid" style={{ marginBottom: 'var(--space-8)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Total Scripts</div>
          <div className="stat-card__value">{totalScripts}</div>
          <div className="stat-card__sub">In monitored scope</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Assigned</div>
          <div className="stat-card__value">{assigned.length}</div>
          <div className="stat-card__sub">Awaiting evaluation start</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">In Progress</div>
          <div className="stat-card__value" style={{ color: 'var(--status-review-text)' }}>
            {inProgress.length}
          </div>
          <div className="stat-card__sub">Active on examiner screens</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Submitted</div>
          <div className="stat-card__value">{submitted.length}</div>
          <div className="stat-card__sub">Ready for moderation</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Under Review</div>
          <div className="stat-card__value" style={{ color: 'var(--status-review-text)' }}>
            {underReview.length}
          </div>
          <div className="stat-card__sub">Moderator docket active</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Approved</div>
          <div className="stat-card__value" style={{ color: 'var(--status-approved-text)' }}>
            {approved.length}
          </div>
          <div className="stat-card__sub">Final marks certified</div>
        </div>
      </div>

      {/* EXAMINER ACTIVITY (Prompt required) */}
      <div className="folio-card" style={{ marginBottom: 'var(--space-8)' }}>
        <div className="folio-card__header">
          <span className="folio-card__title">Examiner Activity Roster</span>
          <span className="label-mono" style={{ fontSize: 11 }}>Real-time evaluation throughput</span>
        </div>
        <div className="folio-card__body" style={{ padding: 0 }}>
          {examiners.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-6)' }}>
              <div className="state-body">No accredited examiners registered.</div>
            </div>
          ) : (
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Examiner</th>
                    <th>Email</th>
                    <th>Assigned</th>
                    <th>In Progress</th>
                    <th>Submitted / Evaluated</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {examinerActivity.map(({ examiner, assigned: aCount, inProgress: ipCount, submitted: sCount }) => (
                    <tr key={examiner._id}>
                      <td style={{ fontWeight: 600 }}>{examiner.name}</td>
                      <td className="label-mono" style={{ fontSize: 12 }}>{examiner.email}</td>
                      <td className="label-mono">{aCount}</td>
                      <td className="label-mono" style={{ color: ipCount > 0 ? 'var(--status-review-text)' : 'inherit', fontWeight: ipCount > 0 ? 700 : 400 }}>
                        {ipCount}
                      </td>
                      <td className="label-mono" style={{ color: sCount > 0 ? 'var(--status-approved-text)' : 'inherit', fontWeight: sCount > 0 ? 700 : 400 }}>
                        {sCount}
                      </td>
                      <td>
                        <span
                          className="label-mono"
                          style={{
                            fontSize: 10,
                            padding: '2px 6px',
                            borderRadius: 2,
                            background: ipCount > 0 ? 'var(--status-review-bg)' : 'var(--parchment-border)',
                            color: ipCount > 0 ? 'var(--status-review-text)' : 'var(--text-muted)',
                          }}
                        >
                          {ipCount > 0 ? 'EVALUATING NOW' : 'IDLE / DOCKET READY'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* SCRIPT EVALUATION FEED */}
      <div className="folio-card">
        <div className="folio-card__header">
          <span className="folio-card__title">Script Evaluation Queue ({filteredBooks.length})</span>
        </div>
        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoadingBooks ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : filteredBooks.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-6)' }}>
              <div className="state-body">No answer books in this monitoring view.</div>
            </div>
          ) : (
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Answer Book</th>
                    <th>Examination</th>
                    <th>Assigned Examiner</th>
                    <th>Status</th>
                    <th>Last Activity</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredBooks.map((ab) => {
                    const exam = typeof ab.examId === 'object' ? (ab.examId as unknown as Exam) : null;
                    const examiner = typeof ab.assignedExaminerId === 'object' ? (ab.assignedExaminerId as unknown as User) : null;

                    return (
                      <tr key={ab._id}>
                        <td>
                          <span className="data-table__code">{ab.answerBookCode}</span>
                          <div className="label-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{ab.studentCode}</div>
                        </td>
                        <td>
                          {exam ? (
                            <div>
                              <div style={{ fontWeight: 500, fontSize: 13 }}>{exam.title}</div>
                              <div className="label-mono" style={{ fontSize: 10 }}>{exam.subjectCode}</div>
                            </div>
                          ) : '—'}
                        </td>
                        <td>
                          {examiner ? examiner.name : <span style={{ color: 'var(--text-faint)' }}>Unassigned</span>}
                        </td>
                        <td><StatusBadge status={ab.status} /></td>
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
