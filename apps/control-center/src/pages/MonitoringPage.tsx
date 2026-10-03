import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Exam, User, AuditLog, Evaluation } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';
import { useSocketEvents } from '../hooks/useSocketEvents';

interface LiveEventItem {
  id: string;
  time: string;
  action: string;
  entity: string;
  actor: string;
  status: string;
}

export function MonitoringPage() {
  const queryClient = useQueryClient();
  const [selectedExamId, setSelectedExamId] = useState<string>('');
  const [selectedExaminerFilter, setSelectedExaminerFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [liveEvents, setLiveEvents] = useState<LiveEventItem[]>([]);

  // 1. Fetch real Answer Books from MongoDB
  const { data: answerBooks = [], isLoading: isLoadingBooks } = useQuery<AnswerBook[]>({
    queryKey: ['monitoring-books'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books');
      return data.data;
    },
  });

  // 2. Fetch real Exams
  const { data: exams = [] } = useQuery<Exam[]>({
    queryKey: ['monitoring-exams'],
    queryFn: async () => {
      const { data } = await apiClient.get('/exams');
      return data.data;
    },
  });

  // 3. Fetch accredited Examiners
  const { data: examiners = [] } = useQuery<User[]>({
    queryKey: ['monitoring-examiners'],
    queryFn: async () => {
      const { data } = await apiClient.get('/users/examiners');
      return data.data;
    },
  });

  // 4. Fetch real Evaluations
  const { data: evaluations = [] } = useQuery<Evaluation[]>({
    queryKey: ['monitoring-evaluations'],
    queryFn: async () => {
      const { data } = await apiClient.get('/evaluations');
      return data.data;
    },
  });

  // 5. Fetch real Audit Logs to seed the Live Event Stream
  const { data: auditLogs = [] } = useQuery<AuditLog[]>({
    queryKey: ['monitoring-audit-logs'],
    queryFn: async () => {
      const { data } = await apiClient.get('/audit-logs?limit=30');
      return data.data;
    },
  });

  // Seed liveEvents once auditLogs load
  useEffect(() => {
    if (auditLogs.length > 0 && liveEvents.length === 0) {
      const initial: LiveEventItem[] = auditLogs.map((log) => ({
        id: log._id,
        time: new Date(log.createdAt).toLocaleTimeString(),
        action: log.action,
        entity: log.entityId || log.entityType || 'Record',
        actor: typeof log.actorId === 'object' && log.actorId ? (log.actorId as any).name : 'System Operations',
        status: ((log.metadata as any)?.status as string) || 'LOGGED',
      }));
      setLiveEvents(initial);
    }
  }, [auditLogs, liveEvents.length]);

  // Real-time Socket.IO handler to push to live stream (Section 16)
  const pushLiveEvent = useCallback((action: string, entity: string, actor: string, status: string) => {
    const newItem: LiveEventItem = {
      id: `${Date.now()}-${Math.random()}`,
      time: new Date().toLocaleTimeString(),
      action,
      entity,
      actor,
      status,
    };
    setLiveEvents((prev) => [newItem, ...prev.slice(0, 49)]);
  }, []);

  const handlers = useCallback(() => ({
    'script.finalized': (payload: any) => {
      queryClient.invalidateQueries({ queryKey: ['monitoring-books'] });
      pushLiveEvent('SCRIPT_FINALIZED', payload?.answerBook?.answerBookCode || 'Digital Script', 'Scan Center', 'READY');
    },
    'answerbook.assigned': (payload: any) => {
      queryClient.invalidateQueries({ queryKey: ['monitoring-books'] });
      queryClient.invalidateQueries({ queryKey: ['monitoring-evaluations'] });
      pushLiveEvent('SCRIPT_ASSIGNED', payload?.answerBook?.answerBookCode || 'Script', 'Admin Operations', 'ASSIGNED');
    },
    'answerbook.status.changed': () => {
      queryClient.invalidateQueries({ queryKey: ['monitoring-books'] });
    },
    'evaluation.started': (payload: any) => {
      queryClient.invalidateQueries({ queryKey: ['monitoring-books'] });
      queryClient.invalidateQueries({ queryKey: ['monitoring-evaluations'] });
      pushLiveEvent('EVALUATION_STARTED', payload?.evaluation?._id || 'Evaluation', 'Examiner', 'IN_PROGRESS');
    },
    'evaluation.submitted': (payload: any) => {
      queryClient.invalidateQueries({ queryKey: ['monitoring-books'] });
      queryClient.invalidateQueries({ queryKey: ['monitoring-evaluations'] });
      pushLiveEvent('EVALUATION_SUBMITTED', payload?.evaluation?._id || 'Evaluation', 'Examiner', 'SUBMITTED');
    },
    'moderation.approved': (payload: any) => {
      queryClient.invalidateQueries({ queryKey: ['monitoring-books'] });
      queryClient.invalidateQueries({ queryKey: ['monitoring-evaluations'] });
      pushLiveEvent('MODERATION_APPROVED', payload?.evaluation?._id || 'Evaluation', 'Moderator', 'APPROVED');
    },
    'moderation.returned': (payload: any) => {
      queryClient.invalidateQueries({ queryKey: ['monitoring-books'] });
      queryClient.invalidateQueries({ queryKey: ['monitoring-evaluations'] });
      pushLiveEvent('MODERATION_RETURNED', payload?.evaluation?._id || 'Evaluation', 'Moderator', 'RETURNED');
    },
  }), [queryClient, pushLiveEvent]);
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

  // Section 16 Metrics: Total Scripts, Ready, Assigned, In Evaluation, Submitted, Under Review, Approved
  const totalScripts = examScopedBooks.length;
  const readyCount = examScopedBooks.filter((b) => b.status === 'READY').length;
  const assignedCount = examScopedBooks.filter((b) => b.status === 'ASSIGNED').length;
  const inEvaluationCount = examScopedBooks.filter((b) => b.status === 'IN_PROGRESS').length;
  const submittedCount = examScopedBooks.filter((b) => b.status === 'SUBMITTED').length;
  const underReviewCount = examScopedBooks.filter((b) => b.status === 'UNDER_REVIEW').length;
  const approvedCount = examScopedBooks.filter((b) => b.status === 'APPROVED' || b.status === 'FINALIZED').length;

  // Filtered queue table
  const filteredQueue = useMemo(() => {
    return examScopedBooks.filter((b) => {
      if (selectedExaminerFilter) {
        const exId = typeof b.assignedExaminerId === 'object' ? (b.assignedExaminerId as any)?._id : b.assignedExaminerId;
        if (exId !== selectedExaminerFilter) return false;
      }
      if (statusFilter && b.status !== statusFilter) return false;
      return true;
    });
  }, [examScopedBooks, selectedExaminerFilter, statusFilter]);

  // Real Examiner Activity (Section 16: Examiner, Assigned, In Progress, Submitted)
  const examinerActivity = useMemo(() => {
    return examiners.map((ex) => {
      const exBooks = examScopedBooks.filter((b) => {
        const examinerId = typeof b.assignedExaminerId === 'object' ? (b.assignedExaminerId as any)?._id : b.assignedExaminerId;
        return examinerId === ex._id;
      });

      const aCount = exBooks.filter((b) => b.status === 'ASSIGNED').length;
      const ipCount = exBooks.filter((b) => b.status === 'IN_PROGRESS').length;
      const sCount = exBooks.filter((b) => b.status === 'SUBMITTED').length;

      const exEvals = evaluations.filter((ev) => {
        const eid = typeof ev.examinerId === 'object' ? (ev.examinerId as any)?._id : ev.examinerId;
        return eid === ex._id;
      });

      let latestTimestamp: string | null = null;
      if (exEvals.length > 0) {
        latestTimestamp = exEvals[0].updatedAt;
      } else if (exBooks.length > 0) {
        latestTimestamp = exBooks[0].updatedAt;
      }

      return {
        examiner: ex,
        assigned: aCount,
        inProgress: ipCount,
        submitted: sCount,
        lastActivity: latestTimestamp ? new Date(latestTimestamp).toLocaleTimeString() : '—',
      };
    });
  }, [examiners, examScopedBooks, evaluations]);

  const selectedExam = exams.find((e) => e._id === selectedExamId) || null;

  return (
    <div>
      {/* Page Header (Section 16) */}
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Control Center · Real-Time Examination Operations</div>
          <h1 className="page-header__title">Live Examination Monitoring</h1>
          <p className="page-header__subtitle">
            Real-time telemetry showing live evaluation activity across examinations, active examiner progress, and system event stream.
          </p>
        </div>
        <div className="page-header__actions" style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
          <select
            className="form-select"
            style={{ width: 280, fontSize: 'var(--text-body)' }}
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
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', background: 'var(--parchment-panel)', border: '1px solid var(--parchment-border)', borderRadius: 'var(--radius-sm)' }}>
            <div className="live-dot" />
            <span className="label-mono" style={{ fontSize: 'var(--text-metadata)', letterSpacing: '0.06em', color: 'var(--text-primary)', fontWeight: 600 }}>
              SOCKET.IO TELEMETRY ACTIVE
            </span>
          </div>
        </div>
      </div>

      {/* TOP METRICS (Section 16: Total Scripts, Ready, Assigned, In Evaluation, Submitted, Under Review, Approved) */}
      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(7, 1fr)', marginBottom: 'var(--space-6)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow">TOTAL SCRIPTS</div>
          <div className="stat-card__value">{totalScripts}</div>
          <div className="stat-card__sub">In monitored scope</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow">READY</div>
          <div className="stat-card__value">{readyCount}</div>
          <div className="stat-card__sub">Awaiting allocation</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow">ASSIGNED</div>
          <div className="stat-card__value">{assignedCount}</div>
          <div className="stat-card__sub">In examiner queue</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow">IN EVALUATION</div>
          <div className="stat-card__value" style={{ color: 'var(--status-review-text)' }}>
            {inEvaluationCount}
          </div>
          <div className="stat-card__sub">Marking in progress</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow">SUBMITTED</div>
          <div className="stat-card__value">{submittedCount}</div>
          <div className="stat-card__sub">Marking complete</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow">UNDER REVIEW</div>
          <div className="stat-card__value" style={{ color: 'var(--status-review-text)' }}>
            {underReviewCount}
          </div>
          <div className="stat-card__sub">Moderator docket</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow">APPROVED</div>
          <div className="stat-card__value" style={{ color: 'var(--status-approved-text)' }}>
            {approvedCount}
          </div>
          <div className="stat-card__sub">Quality certified</div>
        </div>
      </div>

      {/* EXAMINER ACTIVITY TABLE (Section 16: Examiner, Assigned, In Progress, Submitted) */}
      <div className="folio-card" style={{ marginBottom: 'var(--space-6)' }}>
        <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="folio-card__title">Examiner Activity</span>
            <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
              Accredited examiners actively evaluating examination scripts
            </div>
          </div>
          <span className="label-mono" style={{ fontSize: 'var(--text-metadata)' }}>
            {examiners.length} Registered Examiners
          </span>
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
                    <th>Assigned</th>
                    <th>In Progress</th>
                    <th>Submitted</th>
                    <th style={{ textAlign: 'right' }}>Last Activity</th>
                  </tr>
                </thead>
                <tbody>
                  {examinerActivity.map(({ examiner, assigned, inProgress, submitted, lastActivity }) => (
                    <tr key={examiner._id}>
                      <td>
                        <div style={{ fontWeight: 600, fontSize: 'var(--text-table)' }}>{examiner.name}</div>
                        <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                          {examiner.email}
                        </div>
                      </td>
                      <td className="label-mono" style={{ fontSize: 'var(--text-table)' }}>{assigned}</td>
                      <td className="label-mono" style={{ fontSize: 'var(--text-table)', color: inProgress > 0 ? 'var(--status-review-text)' : 'inherit', fontWeight: inProgress > 0 ? 700 : 400 }}>
                        {inProgress}
                      </td>
                      <td className="label-mono" style={{ fontSize: 'var(--text-table)' }}>{submitted}</td>
                      <td className="label-mono" style={{ fontSize: 'var(--text-metadata)', textAlign: 'right' }}>
                        {lastActivity}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* LIVE EVENT STREAM & EVALUATION QUEUE (Section 16) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1.2fr', gap: 'var(--space-6)' }}>
        {/* LIVE EVENT STREAM */}
        <div className="folio-card" style={{ padding: 0 }}>
          <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span className="folio-card__title">Live Event Stream</span>
              <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                Real-time operational events from Socket.IO
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div className="live-dot" />
              <span className="label-mono" style={{ fontSize: 'var(--text-metadata)' }}>STREAMING</span>
            </div>
          </div>

          <div className="folio-card__body" style={{ maxHeight: 440, overflowY: 'auto', padding: 'var(--space-3)' }}>
            {liveEvents.length === 0 ? (
              <div className="state-container" style={{ padding: 'var(--space-6)' }}>
                <div className="state-body">No operational events recorded yet.</div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                {liveEvents.map((evt) => (
                  <div
                    key={evt.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 12px',
                      background: 'var(--parchment-panel)',
                      border: '1px solid var(--parchment-border)',
                      borderRadius: 'var(--radius-sm)',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className="label-mono" style={{ fontSize: 'var(--text-metadata)', fontWeight: 700, color: 'var(--parchment-navy)' }}>
                          {evt.action}
                        </span>
                        <span className="data-table__code" style={{ fontSize: 'var(--text-metadata)' }}>
                          {evt.entity}
                        </span>
                      </div>
                      <div style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-secondary)', marginTop: 3 }}>
                        {evt.actor}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <span className="label-mono" style={{ fontSize: '11px', padding: '2px 6px', borderRadius: 2, background: 'rgba(14, 26, 43, 0.05)', color: 'var(--text-primary)' }}>
                        {evt.status}
                      </span>
                      <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)', marginTop: 3 }}>
                        {evt.time}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* SCRIPT EVALUATION QUEUE */}
        <div className="folio-card" style={{ padding: 0 }}>
          <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span className="folio-card__title">Evaluation Queue ({filteredQueue.length})</span>
              <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                Monitored scripts in active examination scope
              </div>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <select
                className="form-select"
                style={{ fontSize: 'var(--text-metadata)', padding: '3px 8px', width: 140 }}
                value={selectedExaminerFilter}
                onChange={(e) => setSelectedExaminerFilter(e.target.value)}
              >
                <option value="">All Examiners</option>
                {examiners.map((ex) => (
                  <option key={ex._id} value={ex._id}>{ex.name}</option>
                ))}
              </select>
              <select
                className="form-select"
                style={{ fontSize: 'var(--text-metadata)', padding: '3px 8px', width: 130 }}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="">All Statuses</option>
                <option value="READY">READY</option>
                <option value="ASSIGNED">ASSIGNED</option>
                <option value="IN_PROGRESS">IN_PROGRESS</option>
                <option value="SUBMITTED">SUBMITTED</option>
                <option value="APPROVED">APPROVED</option>
              </select>
            </div>
          </div>

          <div className="folio-card__body" style={{ padding: 0, maxHeight: 440, overflowY: 'auto' }}>
            {isLoadingBooks ? (
              <div className="state-container"><div className="spinner" /></div>
            ) : filteredQueue.length === 0 ? (
              <div className="state-container" style={{ padding: 'var(--space-6)' }}>
                <div className="state-body">No answer books match current filters.</div>
              </div>
            ) : (
              <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Script</th>
                      <th>Examiner</th>
                      <th>Status</th>
                      <th>Last Activity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredQueue.map((ab) => {
                      const examiner = typeof ab.assignedExaminerId === 'object' ? (ab.assignedExaminerId as unknown as User) : null;

                      return (
                        <tr key={ab._id}>
                          <td>
                            <span className="data-table__code">{ab.answerBookCode}</span>
                            <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                              {ab.studentCode}
                            </div>
                          </td>
                          <td style={{ fontSize: 'var(--text-table)' }}>
                            {examiner ? examiner.name : <span style={{ color: 'var(--text-faint)' }}>Unassigned</span>}
                          </td>
                          <td>
                            <StatusBadge status={ab.status} />
                          </td>
                          <td className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                            {new Date(ab.updatedAt).toLocaleTimeString()}
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
    </div>
  );
}
