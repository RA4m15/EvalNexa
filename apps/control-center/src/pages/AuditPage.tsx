import React, { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AuditLog, User } from '@evalnexa/types';
import { useSocketEvents } from '../hooks/useSocketEvents';

export function AuditPage() {
  const queryClient = useQueryClient();
  const [entityFilter, setEntityFilter] = useState('');
  const [page, setPage] = useState(1);
  const [selectedLogForModal, setSelectedLogForModal] = useState<AuditLog | null>(null);

  const { data, isLoading, isError } = useQuery<{
    logs: AuditLog[];
    pagination: { total: number; page: number; limit: number; totalPages: number };
  }>({
    queryKey: ['audit-logs', entityFilter, page],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append('page', String(page));
      params.append('limit', '25');
      if (entityFilter) params.append('entityType', entityFilter);

      const res = await apiClient.get(`/audit-logs?${params.toString()}`);
      return {
        logs: res.data.data,
        pagination: res.data.pagination,
      };
    },
    refetchInterval: 15000,
  });

  const handlers = useCallback(
    () => ({
      'exam.created': () => queryClient.invalidateQueries({ queryKey: ['audit-logs'] }),
      'exam.updated': () => queryClient.invalidateQueries({ queryKey: ['audit-logs'] }),
      'answerbook.created': () => queryClient.invalidateQueries({ queryKey: ['audit-logs'] }),
      'answerbook.assigned': () => queryClient.invalidateQueries({ queryKey: ['audit-logs'] }),
      'answerbook.status.changed': () => queryClient.invalidateQueries({ queryKey: ['audit-logs'] }),
      'evaluation.started': () => queryClient.invalidateQueries({ queryKey: ['audit-logs'] }),
      'evaluation.submitted': () => queryClient.invalidateQueries({ queryKey: ['audit-logs'] }),
      'moderation.approved': () => queryClient.invalidateQueries({ queryKey: ['audit-logs'] }),
      'moderation.returned': () => queryClient.invalidateQueries({ queryKey: ['audit-logs'] }),
    }),
    [queryClient]
  );
  useSocketEvents(handlers());

  const logs = data?.logs || [];
  const pagination = data?.pagination;

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Control Center · Governance & Compliance</div>
          <h1 className="page-header__title">Audit & Activity Trail</h1>
          <p className="page-header__subtitle">
            Immutable, append-only operational ledger recording all administrative, intake, marking, and moderation actions.
          </p>
        </div>
        <div className="page-header__actions">
          <select
            className="form-select"
            style={{ width: 220, fontSize: 'var(--text-body)' }}
            value={entityFilter}
            onChange={(e) => {
              setEntityFilter(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All Entity Scopes</option>
            <option value="Exam">Examinations</option>
            <option value="AnswerBook">Digital Scripts</option>
            <option value="Evaluation">Evaluations</option>
            <option value="Moderation">Moderations</option>
            <option value="User">Users</option>
          </select>
        </div>
      </div>

      {/* Main Folio Card with Clean Ledger Table */}
      <div className="folio-card">
        <div
          className="folio-card__header"
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
        >
          <div>
            <span className="folio-card__title">
              Recorded Ledger Entries ({pagination?.total ?? logs.length})
            </span>
            <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
              Sequential cryptographic audit events
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div className="live-dot" />
            <span className="label-mono" style={{ fontSize: 'var(--text-metadata)', letterSpacing: '0.06em', color: 'var(--text-primary)', fontWeight: 600 }}>
              REAL-TIME LEDGER ACTIVE
            </span>
          </div>
        </div>

        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoading ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : isError ? (
            <div className="state-container">
              <div className="state-title">Unable to load audit logs</div>
              <div className="state-body">Check connection to EvalNexa backend services.</div>
              <button
                className="btn btn-secondary state-action"
                onClick={() => queryClient.invalidateQueries({ queryKey: ['audit-logs'] })}
              >
                Retry
              </button>
            </div>
          ) : logs.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-10)' }}>
              <div className="state-icon">📜</div>
              <div className="state-title">No Audit Events Logged</div>
              <div className="state-body">
                Operational events will be recorded here automatically when exams are created, scripts assigned, or evaluations submitted.
              </div>
            </div>
          ) : (
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Action</th>
                    <th>Actor</th>
                    <th>Entity</th>
                    <th>Entity Identifier</th>
                    <th style={{ textAlign: 'right' }}>Metadata</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => {
                    const actor = typeof log.actorId === 'object' ? (log.actorId as User) : null;
                    const dateObj = new Date(log.createdAt);

                    return (
                      <tr key={log._id}>
                        <td>
                          <div className="label-mono" style={{ fontSize: 'var(--text-table)', fontWeight: 600 }}>
                            {dateObj.toLocaleTimeString()}
                          </div>
                          <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                            {dateObj.toLocaleDateString()}
                          </div>
                        </td>
                        <td>
                          <span
                            className="label-mono"
                            style={{
                              fontSize: '11px',
                              padding: '3px 8px',
                              borderRadius: 'var(--radius-sm)',
                              background: 'rgba(14, 26, 43, 0.06)',
                              color: 'var(--parchment-navy)',
                              fontWeight: 700,
                              letterSpacing: '0.04em',
                            }}
                          >
                            {log.action}
                          </span>
                        </td>
                        <td>
                          {actor ? (
                            <div>
                              <div style={{ fontWeight: 600, fontSize: 'var(--text-table)' }}>{actor.name}</div>
                              <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                                {actor.role}
                              </div>
                            </div>
                          ) : (
                            <span className="label-mono" style={{ fontSize: 'var(--text-table)', color: 'var(--text-muted)' }}>
                              System / Automated
                            </span>
                          )}
                        </td>
                        <td>
                          <span className="data-table__code" style={{ fontSize: 'var(--text-table)' }}>
                            {log.entityType}
                          </span>
                        </td>
                        <td>
                          <span className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-secondary)' }}>
                            {log.entityId}
                          </span>
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          {log.metadata ? (
                            <button
                              className="btn btn-ghost btn-sm"
                              onClick={() => setSelectedLogForModal(log)}
                              title="Inspect structured audit metadata payload"
                            >
                              View Metadata ↗
                            </button>
                          ) : (
                            <span style={{ color: 'var(--text-muted)', fontSize: 'var(--text-metadata)' }}>—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination Controls */}
          {pagination && pagination.totalPages > 1 && (
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: 'var(--space-3) var(--space-5)',
                borderTop: '1px solid var(--parchment-border)',
                background: 'var(--parchment-panel)',
              }}
            >
              <div style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-secondary)' }}>
                Showing page <strong>{pagination.page}</strong> of <strong>{pagination.totalPages}</strong> ({pagination.total} total events)
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  ← Previous
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={page >= pagination.totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Structured Metadata Drawer / Modal (Prompt Section 20: Do NOT show huge raw JSON blocks by default) */}
      {selectedLogForModal && (
        <div
          className="modal-backdrop"
          onClick={(e) => e.target === e.currentTarget && setSelectedLogForModal(null)}
        >
          <div className="modal" style={{ maxWidth: 640 }}>
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow">Audit Record Details</div>
                <div className="modal__title" style={{ fontSize: 'var(--text-card-title)' }}>
                  {selectedLogForModal.action}
                </div>
              </div>
              <button className="modal__close" onClick={() => setSelectedLogForModal(null)}>
                ✕
              </button>
            </div>

            <div className="modal__body">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)', marginBottom: 'var(--space-4)', padding: 'var(--space-3) var(--space-4)', background: 'var(--parchment-panel)', border: '1px solid var(--parchment-border)', borderRadius: 'var(--radius-sm)' }}>
                <div>
                  <div className="label-caps" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Entity Type</div>
                  <div style={{ fontWeight: 600, fontSize: 'var(--text-body)' }}>{selectedLogForModal.entityType}</div>
                </div>
                <div>
                  <div className="label-caps" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Recorded At</div>
                  <div className="label-mono" style={{ fontSize: 'var(--text-metadata)' }}>
                    {new Date(selectedLogForModal.createdAt).toLocaleString()}
                  </div>
                </div>
                <div style={{ gridColumn: 'span 2' }}>
                  <div className="label-caps" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Entity Identifier</div>
                  <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', wordBreak: 'break-all' }}>
                    {selectedLogForModal.entityId}
                  </div>
                </div>
              </div>

              <div className="label-caps" style={{ marginBottom: 'var(--space-2)' }}>Structured Metadata Payload</div>
              <pre
                className="metadata-pre"
                style={{
                  maxHeight: 320,
                  overflowY: 'auto',
                  margin: 0,
                  padding: 'var(--space-4)',
                }}
              >
                {JSON.stringify(selectedLogForModal.metadata, null, 2)}
              </pre>
            </div>

            <div className="modal__footer">
              <button
                className="btn btn-secondary"
                onClick={() => {
                  navigator.clipboard.writeText(JSON.stringify(selectedLogForModal.metadata, null, 2));
                  alert('Audit metadata copied to clipboard.');
                }}
              >
                Copy JSON
              </button>
              <button className="btn btn-primary" onClick={() => setSelectedLogForModal(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
