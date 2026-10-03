import React, { useState, useMemo, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Exam, User } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';
import { useSocketEvents } from '../hooks/useSocketEvents';

export function AnswerBooksPage() {
  const queryClient = useQueryClient();
  const [examFilter, setExamFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedScript, setSelectedScript] = useState<AnswerBook | null>(null);

  // Fetch real Answer Books from MongoDB
  const { data: answerBooks = [], isLoading, isError } = useQuery<AnswerBook[]>({
    queryKey: ['answer-books'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books');
      return data.data;
    },
  });

  // Fetch real Exams
  const { data: exams = [] } = useQuery<Exam[]>({
    queryKey: ['exams'],
    queryFn: async () => {
      const { data } = await apiClient.get('/exams');
      return data.data;
    },
  });

  // Real-time Socket.IO synchronization
  const handlers = useCallback(
    () => ({
      'answerbook.created': () => {
        queryClient.invalidateQueries({ queryKey: ['answer-books'] });
      },
      'answerbook.assigned': () => {
        queryClient.invalidateQueries({ queryKey: ['answer-books'] });
      },
      'answerbook.status.changed': () => {
        queryClient.invalidateQueries({ queryKey: ['answer-books'] });
      },
      'script.finalized': () => {
        queryClient.invalidateQueries({ queryKey: ['answer-books'] });
      },
      'evaluation.started': () => {
        queryClient.invalidateQueries({ queryKey: ['answer-books'] });
      },
      'evaluation.submitted': () => {
        queryClient.invalidateQueries({ queryKey: ['answer-books'] });
      },
      'moderation.approved': () => {
        queryClient.invalidateQueries({ queryKey: ['answer-books'] });
      },
    }),
    [queryClient]
  );
  useSocketEvents(handlers());

  // Filter application (Section 14: Examination & Status)
  const filteredBooks = useMemo(() => {
    return answerBooks.filter((ab) => {
      if (examFilter) {
        const eid = typeof ab.examId === 'object' ? (ab.examId as any)._id : ab.examId;
        if (eid !== examFilter) return false;
      }
      if (statusFilter && ab.status !== statusFilter) return false;
      return true;
    });
  }, [answerBooks, examFilter, statusFilter]);

  return (
    <div>
      {/* Page Header (Section 14) */}
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Control Center · Digital Script Register</div>
          <h1 className="page-header__title">Digital Scripts</h1>
          <p className="page-header__subtitle">
            Master register of scanned, verified, and finalized scripts ready for examiner assignment and evaluation.
          </p>
        </div>
        <div className="page-header__actions">
          <Link to="/scan-center" className="btn btn-primary" style={{ textDecoration: 'none' }}>
            + Open Scan Center
          </Link>
        </div>
      </div>

      {/* Filters (Section 14: Examination & Status) */}
      <div className="folio-card" style={{ marginBottom: 'var(--space-6)', padding: 'var(--space-3) var(--space-4)' }}>
        <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <span className="label-caps" style={{ fontSize: 'var(--text-metadata)' }}>Examination:</span>
            <select
              className="form-select"
              style={{ fontSize: 'var(--text-metadata)', padding: '5px 10px', minWidth: 220 }}
              value={examFilter}
              onChange={(e) => setExamFilter(e.target.value)}
            >
              <option value="">All Examinations ({exams.length})</option>
              {exams.map((ex) => (
                <option key={ex._id} value={ex._id}>
                  {ex.subjectCode} · {ex.title}
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <span className="label-caps" style={{ fontSize: 'var(--text-metadata)' }}>Status:</span>
            <select
              className="form-select"
              style={{ fontSize: 'var(--text-metadata)', padding: '5px 10px', minWidth: 160 }}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">All Statuses</option>
              <option value="READY">READY</option>
              <option value="ASSIGNED">ASSIGNED</option>
              <option value="IN_PROGRESS">IN_PROGRESS</option>
              <option value="SUBMITTED">SUBMITTED</option>
              <option value="APPROVED">APPROVED</option>
              <option value="RETURNED">RETURNED</option>
              <option value="FINALIZED">FINALIZED</option>
            </select>
          </div>

          {(examFilter || statusFilter) && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setExamFilter('');
                setStatusFilter('');
              }}
            >
              Reset Filters
            </button>
          )}

          <div style={{ marginLeft: 'auto', fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
            Showing <strong>{filteredBooks.length}</strong> of <strong>{answerBooks.length}</strong> digital scripts
          </div>
        </div>
      </div>

      {/* Main Table (Section 14: Script Code, Exam, Pages, Quality, Processing, Examiner, Evaluation, Action: OPEN SCRIPT) */}
      <div className="folio-card">
        <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="folio-card__title">Script Register ({filteredBooks.length})</span>
            <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
              Finalized script records in MongoDB
            </div>
          </div>
          <span className="label-mono" style={{ fontSize: 'var(--text-metadata)' }}>
            {answerBooks.filter((b) => b.status === 'READY').length} Ready for Assignment
          </span>
        </div>

        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoading ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : isError ? (
            <div className="state-container">
              <div className="state-title">Failed to load digital scripts</div>
              <div className="state-body">Could not connect to EvalNexa database.</div>
              <button
                className="btn btn-secondary state-action"
                onClick={() => queryClient.invalidateQueries({ queryKey: ['answer-books'] })}
              >
                Retry
              </button>
            </div>
          ) : filteredBooks.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-10)' }}>
              <div className="state-icon">📄</div>
              <div className="state-title">No Digital Scripts Found</div>
              <div className="state-body">
                {examFilter || statusFilter
                  ? 'No digital scripts match the selected filters.'
                  : 'No scripts have been finalized yet. Open the Scan Center to capture and verify physical answer books.'}
              </div>
              <div className="state-action">
                <Link to="/scan-center" className="btn btn-primary" style={{ textDecoration: 'none' }}>
                  + Open Scan Center
                </Link>
              </div>
            </div>
          ) : (
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Script Code</th>
                    <th>Exam</th>
                    <th>Pages</th>
                    <th>Quality</th>
                    <th>Processing</th>
                    <th>Examiner</th>
                    <th>Evaluation</th>
                    <th style={{ textAlign: 'right' }}>Action</th>
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
                          <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                            {ab.studentCode}
                          </div>
                        </td>
                        <td>
                          {exam ? (
                            <div>
                              <div style={{ fontWeight: 600, fontSize: 'var(--text-table)' }}>{exam.title}</div>
                              <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                                {exam.subjectCode}
                              </div>
                            </div>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="label-mono" style={{ fontSize: 'var(--text-table)' }}>
                          {ab.pageCount}
                        </td>
                        <td>
                          <span
                            className={`status-badge ${
                              ab.qualityStatus === 'VERIFIED'
                                ? 'status-badge--approved'
                                : ab.qualityStatus === 'RESCAN_REQUIRED'
                                ? 'status-badge--returned'
                                : 'status-badge--review'
                            }`}
                          >
                            {ab.qualityStatus || 'VERIFIED'}
                          </span>
                        </td>
                        <td>
                          <span className="label-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                            {ab.processingStatus || 'READY_FOR_EVALUATION'}
                          </span>
                        </td>
                        <td style={{ fontSize: 'var(--text-table)' }}>
                          {examiner ? (
                            <span style={{ fontWeight: 600 }}>{examiner.name}</span>
                          ) : (
                            <span style={{ color: 'var(--text-faint)', fontStyle: 'italic' }}>Unassigned</span>
                          )}
                        </td>
                        <td>
                          <StatusBadge status={ab.status} />
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => setSelectedScript(ab)}
                          >
                            Open Script
                          </button>
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

      {/* Script Inspector Modal (Section 14: Action OPEN SCRIPT) */}
      {selectedScript && (
        <div
          className="modal-backdrop"
          onClick={(e) => e.target === e.currentTarget && setSelectedScript(null)}
        >
          <div className="modal" style={{ maxWidth: 640 }}>
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow">Digital Script Dossier</div>
                <div className="modal__title" style={{ fontSize: 'var(--text-card-title)' }}>
                  {selectedScript.answerBookCode}
                </div>
              </div>
              <button className="modal__close" onClick={() => setSelectedScript(null)}>✕</button>
            </div>

            <div className="modal__body">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)', padding: 'var(--space-4)', background: 'var(--parchment-panel)', border: '1px solid var(--parchment-border)', borderRadius: 'var(--radius-sm)', marginBottom: 'var(--space-4)' }}>
                <div>
                  <div className="label-caps" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Student Code</div>
                  <div style={{ fontWeight: 700, fontSize: 'var(--text-body)' }}>{selectedScript.studentCode}</div>
                </div>

                <div>
                  <div className="label-caps" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Evaluation Status</div>
                  <StatusBadge status={selectedScript.status} />
                </div>

                <div>
                  <div className="label-caps" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Pages Verified</div>
                  <div style={{ fontSize: 'var(--text-body)', fontWeight: 600 }}>{selectedScript.pageCount} Pages</div>
                </div>

                <div>
                  <div className="label-caps" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Quality Assessment</div>
                  <span className={`status-badge ${selectedScript.qualityStatus === 'VERIFIED' ? 'status-badge--approved' : 'status-badge--review'}`}>
                    {selectedScript.qualityStatus || 'VERIFIED'}
                  </span>
                </div>

                <div style={{ gridColumn: 'span 2' }}>
                  <div className="label-caps" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Assigned Examiner</div>
                  <div style={{ fontSize: 'var(--text-body)', fontWeight: 600 }}>
                    {typeof selectedScript.assignedExaminerId === 'object' && selectedScript.assignedExaminerId
                      ? (selectedScript.assignedExaminerId as any).name
                      : 'None (Unassigned)'}
                  </div>
                </div>
              </div>

              {selectedScript.pdfUrl && (
                <div style={{ marginBottom: 'var(--space-4)' }}>
                  <div className="label-caps" style={{ marginBottom: 4 }}>Ingested Document URL</div>
                  <a
                    href={selectedScript.pdfUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="label-mono"
                    style={{ fontSize: '11px', wordBreak: 'break-all', color: 'var(--parchment-navy)' }}
                  >
                    {selectedScript.pdfUrl} ↗
                  </a>
                </div>
              )}
            </div>

            <div className="modal__footer">
              {selectedScript.status === 'READY' && (
                <Link
                  to="/assignments"
                  className="btn btn-primary"
                  style={{ textDecoration: 'none' }}
                  onClick={() => setSelectedScript(null)}
                >
                  Assign Examiner →
                </Link>
              )}
              <button className="btn btn-secondary" onClick={() => setSelectedScript(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
