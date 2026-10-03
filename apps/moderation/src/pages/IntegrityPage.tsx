import React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { IntegrityIssue } from '@evalnexa/types';

export function IntegrityPage() {
  const queryClient = useQueryClient();

  const { data: issues = [], isLoading, isError } = useQuery<IntegrityIssue[]>({
    queryKey: ['integrity-issues'],
    queryFn: async () => {
      const { data } = await apiClient.get('/moderation/integrity-checks');
      return data.data;
    },
    refetchInterval: 15000,
  });

  const highSeverity = issues.filter((i) => i.severity === 'HIGH').length;
  const mediumSeverity = issues.filter((i) => i.severity === 'MEDIUM').length;
  const lowSeverity = issues.filter((i) => i.severity === 'LOW').length;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Moderation & Quality Center · Integrity Surveillance</div>
          <h1 className="page-header__title">Examination Integrity Center</h1>
          <p className="page-header__subtitle">
            Deterministic rule-based integrity checks across all submitted digital answer books and examiner scoring records.
          </p>
        </div>
        <div className="page-header__actions">
          <button className="btn btn-secondary" onClick={() => queryClient.invalidateQueries({ queryKey: ['integrity-issues'] })}>
            ↻ Re-run Verification Sweep
          </button>
        </div>
      </div>

      {/* Metric strip */}
      <div className="stat-grid" style={{ marginBottom: 'var(--space-8)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow">TOTAL INTEGRITY FLAGS</div>
          <div className="stat-card__value" style={{ color: issues.length > 0 ? 'var(--status-returned-text)' : 'var(--status-approved-text)' }}>
            {isLoading ? '—' : issues.length}
          </div>
          <div className="stat-card__sub">{issues.length === 0 ? 'System operating nominally' : 'Actionable discrepancies detected'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">CRITICAL ANOMALIES</div>
          <div className="stat-card__value" style={{ color: highSeverity > 0 ? 'var(--status-returned-text)' : 'inherit' }}>
            {isLoading ? '—' : highSeverity}
          </div>
          <div className="stat-card__sub">Score breaches & missing questions</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">ARITHMETIC DISCREPANCIES</div>
          <div className="stat-card__value" style={{ color: mediumSeverity > 0 ? 'var(--status-review-text)' : 'inherit' }}>
            {isLoading ? '—' : mediumSeverity}
          </div>
          <div className="stat-card__sub">Sum calculation mismatches</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">DOCUMENT INTEGRITY</div>
          <div className="stat-card__value" style={{ color: lowSeverity > 0 ? 'var(--status-review-text)' : 'inherit' }}>
            {isLoading ? '—' : lowSeverity}
          </div>
          <div className="stat-card__sub">Page sequence & missing leaves</div>
        </div>
      </div>

      {/* Rules Reference Strip */}
      <div className="folio-card" style={{ marginBottom: 'var(--space-6)', background: 'rgba(255,255,255,0.4)' }}>
        <div className="folio-card__header">
          <span className="folio-card__title">Deterministic Rule Engines Monitored</span>
        </div>
        <div className="folio-card__body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-4)' }}>
            {[
              { rule: 'Unchecked Questions', desc: 'Flags scripts submitted without explicit status on every question.' },
              { rule: 'Marks Above Maximum', desc: 'Detects question or total scores exceeding exam paper boundaries.' },
              { rule: 'Invalid Arithmetic Totals', desc: 'Verifies sum of question scores strictly matches final awarded score.' },
              { rule: 'Duplicate Evaluations', desc: 'Flags conflicting evaluation dockets registered against identical scripts.' },
              { rule: 'Missing Ingestion Leaves', desc: 'Verifies physical booklet scan page count matches docket specification.' },
            ].map(({ rule, desc }) => (
              <div key={rule} style={{ padding: 'var(--space-3)', background: 'rgba(14,26,43,0.03)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, marginBottom: 2 }}>{rule}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.4 }}>{desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Issues Table or Clean Empty State */}
      <div className="folio-card">
        <div className="folio-card__header">
          <span className="folio-card__title">Integrity Surveillance Log ({issues.length})</span>
        </div>
        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoading ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : isError ? (
            <div className="state-container">
              <div className="state-title">Failed to load integrity diagnostics</div>
            </div>
          ) : issues.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-10)' }}>
              <div className="state-icon">🛡</div>
              <div className="state-title">No integrity issues detected.</div>
              <div className="state-body">
                All submitted evaluation dockets and answer books strictly conform to arithmetic bounds, full question coverage, and page custody rules.
              </div>
            </div>
          ) : (
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Anomaly Rule</th>
                    <th>Answer Book</th>
                    <th>Exam</th>
                    <th>Examiner</th>
                    <th>Diagnostic Description</th>
                    <th>Detected</th>
                  </tr>
                </thead>
                <tbody>
                  {issues.map((issue) => (
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
                      <td style={{ fontWeight: 600, fontSize: 13 }}>{issue.ruleName}</td>
                      <td><span className="data-table__code">{issue.answerBookCode}</span></td>
                      <td><span className="data-table__code">{issue.examCode}</span></td>
                      <td style={{ fontSize: 12 }}>{issue.examinerName}</td>
                      <td style={{ fontSize: 12, maxWidth: 320 }}>{issue.description}</td>
                      <td className="label-mono" style={{ fontSize: 11 }}>
                        {new Date(issue.timestamp).toLocaleTimeString()}
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
