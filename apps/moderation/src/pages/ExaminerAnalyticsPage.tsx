import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { ExaminerAnalyticsItem } from '@evalnexa/types';

export function ExaminerAnalyticsPage() {
  const { data: analytics = [], isLoading, isError } = useQuery<ExaminerAnalyticsItem[]>({
    queryKey: ['examiner-analytics'],
    queryFn: async () => {
      const { data } = await apiClient.get('/moderation/examiner-analytics');
      return data.data;
    },
    refetchInterval: 20000,
  });

  const totalExaminers = analytics.length;
  const totalAssigned = analytics.reduce((acc, a) => acc + (a.assigned || 0), 0);
  const totalCompleted = analytics.reduce((acc, a) => acc + (a.completed || 0), 0);
  const totalReturned = analytics.reduce((acc, a) => acc + (a.returned || 0), 0);

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Moderation & Quality Center · Operational Telemetry</div>
          <h1 className="page-header__title">Examiner Performance & Workload Analytics</h1>
          <p className="page-header__subtitle">
            Operational monitoring of examiner workload allocation, evaluation velocity, and return frequencies.
          </p>
        </div>
      </div>

      {/* Metric strip */}
      <div className="stat-grid" style={{ marginBottom: 'var(--space-8)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow">ACCREDITED EXAMINERS</div>
          <div className="stat-card__value">{isLoading ? '—' : totalExaminers}</div>
          <div className="stat-card__sub">Institutional faculty on record</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">TOTAL ASSIGNED SCRIPTS</div>
          <div className="stat-card__value">{isLoading ? '—' : totalAssigned}</div>
          <div className="stat-card__sub">Distributed across roster</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">COMPLETED EVALUATIONS</div>
          <div className="stat-card__value" style={{ color: 'var(--status-approved-text)' }}>
            {isLoading ? '—' : totalCompleted}
          </div>
          <div className="stat-card__sub">Submitted to moderation</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">REMANDED / RETURNED</div>
          <div className="stat-card__value" style={{ color: totalReturned > 0 ? 'var(--status-returned-text)' : 'inherit' }}>
            {isLoading ? '—' : totalReturned}
          </div>
          <div className="stat-card__sub">Returned for marking review</div>
        </div>
      </div>

      {/* Roster Table */}
      <div className="folio-card">
        <div className="folio-card__header">
          <span className="folio-card__title">Examiner Operational Ledger ({analytics.length})</span>
        </div>
        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoading ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : isError ? (
            <div className="state-container">
              <div className="state-title">Failed to load examiner telemetry</div>
            </div>
          ) : analytics.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-8)' }}>
              <div className="state-icon">👥</div>
              <div className="state-title">No Examiner Records Found</div>
              <div className="state-body">Examiner telemetry will populate once faculty examiners are registered in the Control Center.</div>
            </div>
          ) : (
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Examiner</th>
                    <th>Email</th>
                    <th>Assigned</th>
                    <th>Completed</th>
                    <th>Average Marks</th>
                    <th>Avg Evaluation Time</th>
                    <th>Returned</th>
                    <th>Flags</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.map((item) => (
                    <tr key={item.examinerId}>
                      <td style={{ fontWeight: 600 }}>{item.name}</td>
                      <td className="label-mono" style={{ fontSize: 11 }}>{item.email}</td>
                      <td className="label-mono">{item.assigned}</td>
                      <td className="label-mono" style={{ fontWeight: 600, color: item.completed > 0 ? 'var(--status-approved-text)' : 'inherit' }}>
                        {item.completed}
                      </td>
                      <td className="label-mono">
                        {item.averageMarks > 0 ? `${item.averageMarks} pts` : '—'}
                      </td>
                      <td className="label-mono">
                        {item.averageEvaluationTimeMinutes > 0 ? `${item.averageEvaluationTimeMinutes} mins` : '—'}
                      </td>
                      <td className="label-mono" style={{ color: item.returned > 0 ? 'var(--status-returned-text)' : 'inherit' }}>
                        {item.returned}
                      </td>
                      <td className="label-mono" style={{ color: item.flags > 0 ? 'var(--status-review-text)' : 'inherit' }}>
                        {item.flags}
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
