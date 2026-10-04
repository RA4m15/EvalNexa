import React, { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '../lib/apiClient';
import { IntegrityIssue } from '@evalnexa/types';
import { getSocket } from '../lib/socket';

export function IntegrityPage() {
  const queryClient = useQueryClient();
  const [selectedSeverity, setSelectedSeverity] = useState<'ALL' | 'HIGH' | 'MEDIUM' | 'LOW'>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date>(new Date());

  const { data: issues = [], isLoading, isError, isFetching, refetch } = useQuery<IntegrityIssue[]>({
    queryKey: ['integrity-issues'],
    queryFn: async () => {
      const { data } = await apiClient.get('/moderation/integrity-checks');
      setLastRefreshedAt(new Date());
      return data.data;
    },
    refetchInterval: 15000,
  });

  // Real-time synchronization with Socket.IO
  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;

    const handleUpdate = () => {
      queryClient.invalidateQueries({ queryKey: ['integrity-issues'] });
    };

    socket.on('evaluation.submitted', handleUpdate);
    socket.on('evaluation.updated', handleUpdate);
    socket.on('moderation.approved', handleUpdate);
    socket.on('moderation.returned', handleUpdate);
    socket.on('answerbook.status.changed', handleUpdate);
    socket.on('script.finalized', handleUpdate);

    return () => {
      socket.off('evaluation.submitted', handleUpdate);
      socket.off('evaluation.updated', handleUpdate);
      socket.off('moderation.approved', handleUpdate);
      socket.off('moderation.returned', handleUpdate);
      socket.off('answerbook.status.changed', handleUpdate);
      socket.off('script.finalized', handleUpdate);
    };
  }, [queryClient]);

  const highSeverity = issues.filter((i) => i.severity === 'HIGH').length;
  const mediumSeverity = issues.filter((i) => i.severity === 'MEDIUM').length;
  const lowSeverity = issues.filter((i) => i.severity === 'LOW').length;

  const filteredIssues = issues.filter((issue) => {
    if (selectedSeverity !== 'ALL' && issue.severity !== selectedSeverity) {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      return (
        issue.ruleName.toLowerCase().includes(q) ||
        issue.answerBookCode.toLowerCase().includes(q) ||
        issue.examCode.toLowerCase().includes(q) ||
        issue.examinerName.toLowerCase().includes(q) ||
        issue.description.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const ACTIVE_RULES = [
    { rule: 'Unchecked Questions', desc: 'Flags scripts submitted without explicit status on every question.' },
    { rule: 'Marks Above Maximum', desc: 'Detects question or total scores exceeding exam paper boundaries.' },
    { rule: 'Rubric Limit Exceeded', desc: 'Detects scores awarded exceeding question rubric specifications.' },
    { rule: 'Invalid Arithmetic Totals', desc: 'Verifies sum of question scores strictly matches final awarded score.' },
    { rule: 'Duplicate Evaluations', desc: 'Flags conflicting evaluation dockets registered against identical scripts.' },
    { rule: 'Rescan Custody Breach', desc: 'Alerts if scripts requiring rescan are in active evaluation.' },
    { rule: 'Custody Desynchronization', desc: 'Detects answer book custody states out of sync with evaluation.' },
    { rule: 'Missing Ingestion Leaves', desc: 'Verifies physical booklet scan page count matches docket specification.' },
  ];

  return (
    <div style={{ maxWidth: 1280, margin: '0 auto' }}>
      <div className="page-header" style={{ marginBottom: 'var(--space-6)' }}>
        <div>
          <div className="page-header__eyebrow" style={{ fontSize: 13, letterSpacing: '0.08em', color: 'var(--parchment-gold)' }}>
            MODERATION & QUALITY CENTER · INTEGRITY SURVEILLANCE
          </div>
          <h1 className="page-header__title" style={{ fontSize: 38, fontWeight: 700, margin: '4px 0 6px 0', fontFamily: 'Cambria, serif' }}>
            Examination Integrity Center
          </h1>
          <p className="page-header__subtitle" style={{ fontSize: 16, color: 'var(--text-muted)' }}>
            Deterministic rule-based integrity checks across all submitted digital answer books and examiner scoring records.
          </p>
        </div>
        <div className="page-header__actions" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            Last scan: {lastRefreshedAt.toLocaleTimeString()}
          </span>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => refetch()}
            disabled={isFetching}
            style={{ fontSize: 13 }}
          >
            {isFetching ? 'Scanning…' : '↻ Re-run Verification Sweep'}
          </button>
        </div>
      </div>

      {/* Metric strip */}
      <div className="stat-grid" style={{ marginBottom: 'var(--space-8)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow" style={{ fontSize: 12 }}>TOTAL INTEGRITY FLAGS</div>
          <div className="stat-card__value" style={{ fontSize: 34, fontFamily: 'Cambria, serif', color: issues.length > 0 ? 'var(--status-returned-text)' : 'var(--status-approved-text)' }}>
            {isLoading ? '—' : issues.length}
          </div>
          <div className="stat-card__sub" style={{ fontSize: 12 }}>{issues.length === 0 ? 'System operating nominally' : 'Actionable discrepancies detected'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow" style={{ fontSize: 12 }}>CRITICAL ANOMALIES</div>
          <div className="stat-card__value" style={{ fontSize: 34, fontFamily: 'Cambria, serif', color: highSeverity > 0 ? 'var(--status-returned-text)' : 'inherit' }}>
            {isLoading ? '—' : highSeverity}
          </div>
          <div className="stat-card__sub" style={{ fontSize: 12 }}>Score breaches & missing questions</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow" style={{ fontSize: 12 }}>ARITHMETIC DISCREPANCIES</div>
          <div className="stat-card__value" style={{ fontSize: 34, fontFamily: 'Cambria, serif', color: mediumSeverity > 0 ? 'var(--status-review-text)' : 'inherit' }}>
            {isLoading ? '—' : mediumSeverity}
          </div>
          <div className="stat-card__sub" style={{ fontSize: 12 }}>Sum calculation mismatches</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow" style={{ fontSize: 12 }}>DOCUMENT INTEGRITY</div>
          <div className="stat-card__value" style={{ fontSize: 34, fontFamily: 'Cambria, serif', color: lowSeverity > 0 ? 'var(--status-review-text)' : 'inherit' }}>
            {isLoading ? '—' : lowSeverity}
          </div>
          <div className="stat-card__sub" style={{ fontSize: 12 }}>Page custody & leaves</div>
        </div>
      </div>

      {/* Rules Reference Strip */}
      <div className="folio-card" style={{ marginBottom: 'var(--space-6)', background: 'rgba(255,255,255,0.5)' }}>
        <div className="folio-card__header">
          <span className="folio-card__title" style={{ fontSize: 16, fontFamily: 'Cambria, serif' }}>
            Deterministic Rules Actively Verified
          </span>
        </div>
        <div className="folio-card__body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-4)' }}>
            {ACTIVE_RULES.map(({ rule, desc }) => (
              <div key={rule} style={{ padding: 'var(--space-3)', background: 'rgba(14,26,43,0.03)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontFamily: 'Cambria, serif', fontSize: 13, fontWeight: 700, marginBottom: 2 }}>{rule}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 }}>{desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 12,
          marginBottom: 'var(--space-4)',
        }}
      >
        {/* Severity Tabs */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {(
            [
              { key: 'ALL', label: `All (${issues.length})` },
              { key: 'HIGH', label: `Critical (${highSeverity})` },
              { key: 'MEDIUM', label: `Medium (${mediumSeverity})` },
              { key: 'LOW', label: `Low (${lowSeverity})` },
            ] as const
          ).map(({ key, label }) => {
            const isActive = selectedSeverity === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setSelectedSeverity(key)}
                className={`btn btn-sm ${isActive ? 'btn-primary' : 'btn-secondary'}`}
                style={{
                  fontSize: 12,
                  fontFamily: 'Cambria, serif',
                  fontWeight: isActive ? 700 : 500,
                }}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Search Input */}
        <div style={{ width: 280 }}>
          <input
            type="text"
            className="form-input"
            placeholder="Search code, exam, examiner…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ fontSize: 13, padding: '6px 10px' }}
          />
        </div>
      </div>

      {/* Issues Table or Clean Empty State */}
      <div className="folio-card">
        <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="folio-card__title" style={{ fontSize: 18, fontFamily: 'Cambria, serif' }}>
            Integrity Surveillance Log ({filteredIssues.length}{filteredIssues.length !== issues.length ? ` of ${issues.length}` : ''})
          </span>
          <span className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>ZERO FAKE SCORES · DETERMINISTIC ONLY</span>
        </div>
        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoading ? (
            <div className="state-container" style={{ padding: 'var(--space-10)' }}>
              <div className="spinner" />
              <div style={{ marginTop: 'var(--space-3)', fontSize: 14 }}>Scanning MongoDB evaluation records…</div>
            </div>
          ) : isError ? (
            <div className="state-container" style={{ padding: 'var(--space-8)' }}>
              <div className="state-title" style={{ fontSize: 18 }}>Failed to load integrity diagnostics</div>
              <button
                className="btn btn-secondary state-action"
                onClick={() => refetch()}
                style={{ marginTop: 'var(--space-3)', fontSize: 13 }}
              >
                Retry
              </button>
            </div>
          ) : filteredIssues.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-10)' }}>
              <div className="state-icon" style={{ fontSize: 32 }}>🛡</div>
              <div className="state-title" style={{ fontSize: 20, fontFamily: 'Cambria, serif', marginTop: 8 }}>
                {issues.length === 0 ? 'No integrity issues detected.' : 'No matching issues found for current filter.'}
              </div>
              <div className="state-body" style={{ fontSize: 14, color: 'var(--text-muted)', maxWidth: 440, marginTop: 4 }}>
                {issues.length === 0
                  ? 'All submitted evaluation dockets and answer books strictly conform to arithmetic bounds, full question coverage, and page custody rules.'
                  : 'Try selecting a different severity category or clearing your search query.'}
              </div>
            </div>
          ) : (
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table" style={{ width: '100%', fontSize: 14 }}>
                <thead>
                  <tr>
                    <th style={{ fontSize: 12 }}>Severity</th>
                    <th style={{ fontSize: 12 }}>Anomaly Rule</th>
                    <th style={{ fontSize: 12 }}>Answer Book</th>
                    <th style={{ fontSize: 12 }}>Exam</th>
                    <th style={{ fontSize: 12 }}>Examiner</th>
                    <th style={{ fontSize: 12 }}>Diagnostic Description</th>
                    <th style={{ fontSize: 12 }}>Detected</th>
                    <th style={{ fontSize: 12, textAlign: 'right' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredIssues.map((issue) => (
                    <tr key={issue.id}>
                      <td>
                        <span
                          className="label-mono"
                          style={{
                            fontSize: 10,
                            padding: '2px 6px',
                            borderRadius: 2,
                            fontWeight: 700,
                            background:
                              issue.severity === 'HIGH'
                                ? 'var(--status-returned-bg)'
                                : issue.severity === 'MEDIUM'
                                ? 'var(--status-review-bg)'
                                : 'var(--parchment-border)',
                            color:
                              issue.severity === 'HIGH'
                                ? 'var(--status-returned-text)'
                                : issue.severity === 'MEDIUM'
                                ? 'var(--status-review-text)'
                                : 'inherit',
                          }}
                        >
                          {issue.severity}
                        </span>
                      </td>
                      <td style={{ fontWeight: 600, fontSize: 14, fontFamily: 'Cambria, serif' }}>{issue.ruleName}</td>
                      <td><span className="data-table__code" style={{ fontSize: 13, fontWeight: 700 }}>{issue.answerBookCode}</span></td>
                      <td><span className="data-table__code" style={{ fontSize: 12 }}>{issue.examCode}</span></td>
                      <td style={{ fontSize: 13 }}>{issue.examinerName}</td>
                      <td style={{ fontSize: 13, maxWidth: 320, lineHeight: 1.4 }}>{issue.description}</td>
                      <td className="label-mono" style={{ fontSize: 11 }}>
                        {new Date(issue.timestamp).toLocaleTimeString()}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {issue.evaluationId ? (
                          <Link to={`/review/${issue.evaluationId}`} className="btn btn-secondary btn-sm" style={{ fontSize: 12 }}>
                            Inspect Docket →
                          </Link>
                        ) : (
                          <Link to="/review" className="btn btn-secondary btn-sm" style={{ fontSize: 12 }}>
                            Inspect Queue →
                          </Link>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
