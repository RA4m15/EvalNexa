import React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AuditLog, User } from '@evalnexa/types';
import { useEffect, useState } from 'react';
import { getSocket } from '../lib/socket';

export function AuditPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [entityTypeFilter, setEntityTypeFilter] = useState('');

  const { data, isLoading, isError } = useQuery<{
    data: AuditLog[];
    pagination: { total: number; page: number; totalPages: number; limit: number };
  }>({
    queryKey: ['audit-logs', page, entityTypeFilter],
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(page), limit: '30' });
      if (entityTypeFilter) params.set('entityType', entityTypeFilter);
      const { data } = await apiClient.get(`/audit-logs?${params}`);
      return data;
    },
  });

  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;
    const handler = () => queryClient.invalidateQueries({ queryKey: ['audit-logs'] });
    socket.on('evaluation.submitted', handler);
    socket.on('moderation.approved', handler);
    socket.on('moderation.returned', handler);
    return () => {
      socket.off('evaluation.submitted', handler);
      socket.off('moderation.approved', handler);
      socket.off('moderation.returned', handler);
    };
  }, [queryClient]);

  const logs = data?.data ?? [];
  const pagination = data?.pagination;

  const ACTION_COLORS: Record<string, string> = {
    EVALUATION_APPROVED: 'var(--status-approved)',
    EVALUATION_RETURNED: 'var(--status-returned)',
    EVALUATION_SUBMITTED: 'var(--status-submitted)',
    EVALUATION_STARTED: 'var(--status-progress)',
    ANSWER_BOOK_ASSIGNED: 'var(--gold-dark)',
    ANSWER_BOOK_CREATED: 'var(--text-muted)',
    EXAM_CREATED: 'var(--text-muted)',
    EXAM_UPDATED: 'var(--text-muted)',
    USER_LOGIN: 'var(--text-faint)',
    USER_CREATED: 'var(--text-muted)',
  };

  return (
    <div>
      <div className="page-header">
        <div className="page-header__eyebrow">Moderation Centre · Audit Trail</div>
        <h1 className="page-header__title">Immutable Audit Trail</h1>
        <p className="page-header__subtitle">
          Complete, tamper-evident log of all system actions. Newest entries first.
        </p>
        <div className="page-header__actions">
          <select
            className="form-select"
            style={{ width: 200 }}
            value={entityTypeFilter}
            onChange={(e) => { setEntityTypeFilter(e.target.value); setPage(1); }}
          >
            <option value="">All Entity Types</option>
            {['Exam', 'AnswerBook', 'Evaluation', 'User'].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="state-container"><div className="spinner" /></div>
      ) : isError ? (
        <div className="state-container">
          <div className="state-title">Failed to load audit trail</div>
          <button className="btn btn-secondary state-action" onClick={() => queryClient.invalidateQueries({ queryKey: ['audit-logs'] })}>Retry</button>
        </div>
      ) : logs.length === 0 ? (
        <div className="state-container">
          <div className="state-icon">📜</div>
          <div className="state-title">No Audit Records Found</div>
          <div className="state-body">
            {entityTypeFilter
              ? `No audit records for entity type "${entityTypeFilter}".`
              : 'No system actions have been recorded yet. Audit entries are created automatically as the system is used.'}
          </div>
          {entityTypeFilter && (
            <div className="state-action">
              <button className="btn btn-secondary" onClick={() => setEntityTypeFilter('')}>Clear Filter</button>
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Action</th>
                  <th>Entity</th>
                  <th>Entity ID</th>
                  <th>Actor</th>
                  <th>Metadata</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => {
                  const actor = typeof log.actorId === 'object' ? log.actorId as unknown as User : null;
                  const color = ACTION_COLORS[log.action] || 'var(--text-muted)';
                  return (
                    <tr key={log._id}>
                      <td>
                        <div className="label-mono" style={{ fontSize: 10 }}>
                          {new Date(log.createdAt).toLocaleString()}
                        </div>
                      </td>
                      <td>
                        <span style={{
                          fontFamily: '"Cambria"',
                          fontSize: 10,
                          fontWeight: 600,
                          letterSpacing: '0.08em',
                          color,
                        }}>
                          {log.action}
                        </span>
                      </td>
                      <td>
                        <span className="label-mono" style={{ fontSize: 10 }}>{log.entityType}</span>
                      </td>
                      <td>
                        <span className="data-table__code" style={{ fontSize: 10 }}>
                          {log.entityId.slice(-8)}…
                        </span>
                      </td>
                      <td>
                        {actor ? (
                          <div>
                            <div style={{ fontSize: 12, fontWeight: 500 }}>{actor.name}</div>
                            <div className="label-mono" style={{ fontSize: 9 }}>{(actor as User & { role: string }).role}</div>
                          </div>
                        ) : (
                          <span className="label-mono" style={{ fontSize: 10, color: 'var(--text-faint)' }}>System</span>
                        )}
                      </td>
                      <td>
                        {log.metadata && Object.keys(log.metadata).length > 0 ? (
                          <details>
                            <summary style={{ cursor: 'pointer', fontSize: 11, color: 'var(--text-muted)' }}>View</summary>
                            <pre style={{
                              fontSize: 10,
                              fontFamily: '"Cambria"',
                              background: 'var(--bg-inset)',
                              padding: 'var(--space-2)',
                              borderRadius: 'var(--radius-sm)',
                              marginTop: 4,
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-all',
                              maxWidth: 260,
                              color: 'var(--text-secondary)',
                            }}>
                              {JSON.stringify(log.metadata, null, 2)}
                            </pre>
                          </details>
                        ) : (
                          <span style={{ color: 'var(--text-faint)', fontSize: 11 }}>—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {pagination && pagination.totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'var(--space-5)' }}>
              <span className="label-mono" style={{ fontSize: 10 }}>
                {pagination.total} records · Page {pagination.page} of {pagination.totalPages}
              </span>
              <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={page === 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  ← Prev
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
        </>
      )}
    </div>
  );
}
