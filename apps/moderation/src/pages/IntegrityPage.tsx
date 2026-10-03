import React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
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
        <div className="page-header__actions">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['integrity-issues'] })}
            style={{ fontSize: 13 }}
          >
            ↻ Re-run Verification Sweep
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
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-4)' }}>
            {[
              { rule: 'Unchecked Questions', desc: 'Flags scripts submitted without explicit status on every question.' },
              { rule: 'Marks Above Maximum', desc: 'Detects question or total scores exceeding exam paper boundaries.' },
              { rule: 'Invalid Arithmetic Totals', desc: 'Verifies sum of question scores strictly matches final awarded score.' },
              { rule: 'Duplicate Evaluations', desc: 'Flags conflicting evaluation dockets registered against identical scripts.' },
              { rule: 'Missing Ingestion Leaves', desc: 'Verifies physical booklet scan page count matches docket specification.' },
            ].map(({ rule, desc }) => (
              <div key={rule} style={{ padding: 'var(--space-3)', background: 'rgba(14,26,43,0.03)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontFamily: 'Cambria, serif', fontSize: 13, fontWeight: 700, marginBottom: 2 }}>{rule}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 }}>{desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Issues Table or Clean Empty State */}
      <div className="folio-card">
        <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="folio-card__title" style={{ fontSize: 18, fontFamily: 'Cambria, serif' }}>
            Integrity Surveillance Log ({issues.length})
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
                onClick={() => queryClient.invalidateQueries({ queryKey: ['integrity-issues'] })}
                style={{ marginTop: 'var(--space-3)', fontSize: 13 }}
              >
                Retry
              </button>
            </div>
          ) : issues.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-10)' }}>
              <div className="state-icon" style={{ fontSize: 32 }}>🛡</div>
              <div className="state-title" style={{ fontSize: 20, fontFamily: 'Cambria, serif', marginTop: 8 }}>
                No integrity issues detected.
              </div>
              <div className="state-body" style={{ fontSize: 14, color: 'var(--text-muted)', maxWidth: 440, marginTop: 4 }}>
                All submitted evaluation dockets and answer books strictly conform to arithmetic bounds, full question coverage, and page custody rules.
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
                      <td style={{ fontWeight: 600, fontSize: 14, fontFamily: 'Cambria, serif' }}>{issue.ruleName}</td>
                      <td><span className="data-table__code" style={{ fontSize: 13, fontWeight: 700 }}>{issue.answerBookCode}</span></td>
                      <td><span className="data-table__code" style={{ fontSize: 12 }}>{issue.examCode}</span></td>
                      <td style={{ fontSize: 13 }}>{issue.examinerName}</td>
                      <td style={{ fontSize: 13, maxWidth: 320, lineHeight: 1.4 }}>{issue.description}</td>
                      <td className="label-mono" style={{ fontSize: 11 }}>
                        {new Date(issue.timestamp).toLocaleTimeString()}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <Link to="/review" className="btn btn-secondary btn-sm" style={{ fontSize: 12 }}>
                          Inspect Queue →
                        </Link>
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
