import React, { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Exam, QualityStatus } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';
import { useSocketEvents } from '../hooks/useSocketEvents';

interface IngestionForm {
  examId: string;
  answerBookCode: string;
  studentCode: string;
  pageCount: string;
  scanBatch: string;
  pdfUrl: string;
  qualityStatus: QualityStatus;
}

const EMPTY_INGESTION: IngestionForm = {
  examId: '',
  answerBookCode: '',
  studentCode: '',
  pageCount: '12',
  scanBatch: `BATCH-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-01`,
  pdfUrl: '',
  qualityStatus: 'VERIFIED',
};

export function ScanCenterPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<IngestionForm>(EMPTY_INGESTION);
  const [formError, setFormError] = useState('');
  const [activeBatchFilter, setActiveBatchFilter] = useState('');

  const { data: answerBooks = [], isLoading, isError } = useQuery<AnswerBook[]>({
    queryKey: ['answer-books-scan'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books');
      return data.data;
    },
  });

  const { data: exams = [] } = useQuery<Exam[]>({
    queryKey: ['exams'],
    queryFn: async () => {
      const { data } = await apiClient.get('/exams');
      return data.data;
    },
  });

  const handlers = useCallback(() => ({
    'answerbook.created': () => queryClient.invalidateQueries({ queryKey: ['answer-books-scan'] }),
    'answerbook.assigned': () => queryClient.invalidateQueries({ queryKey: ['answer-books-scan'] }),
    'answerbook.status.changed': () => queryClient.invalidateQueries({ queryKey: ['answer-books-scan'] }),
  }), [queryClient]);
  useSocketEvents(handlers());

  const ingestMutation = useMutation({
    mutationFn: async (payload: object) => {
      const { data } = await apiClient.post('/answer-books', payload);
      return data;
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['answer-books-scan'] });
      setShowModal(false);
      setForm(EMPTY_INGESTION);
      setFormError('');
      if (res?.data?._id) setSelectedId(res.data._id);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || 'Ingestion failed';
      setFormError(msg);
    },
  });

  const updateQualityMutation = useMutation({
    mutationFn: async ({ id, qualityStatus }: { id: string; qualityStatus: QualityStatus }) => {
      const { data } = await apiClient.patch(`/answer-books/${id}`, { qualityStatus });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['answer-books-scan'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    ingestMutation.mutate({
      ...form,
      pageCount: parseInt(form.pageCount) || 1,
    });
  };

  // Metric strip calculations
  const totalPages = answerBooks.reduce((acc, b) => acc + (b.pageCount || 0), 0);
  const passedCount = answerBooks.filter(
    (b) => b.qualityStatus === 'VERIFIED' || b.qualityStatus === 'READY' || (!b.qualityStatus && b.status === 'READY')
  ).length;
  const issuesCount = answerBooks.filter(
    (b) => b.qualityStatus === 'QUALITY_REVIEW' || b.qualityStatus === 'RESCAN_REQUIRED'
  ).length;
  const readyForEvalCount = answerBooks.filter(
    (b) => b.status === 'READY' || b.status === 'ASSIGNED'
  ).length;

  const batches = Array.from(new Set(answerBooks.map((b) => b.scanBatch).filter(Boolean)));

  const filteredBooks = activeBatchFilter
    ? answerBooks.filter((b) => b.scanBatch === activeBatchFilter)
    : answerBooks;

  const selectedBook = filteredBooks.find((b) => b._id === selectedId) || filteredBooks[0] || null;

  return (
    <div>
      <div className="page-header">
        <div className="page-header__eyebrow">Control Center · Scan & Quality Center</div>
        <h1 className="page-header__title">Digital Script Ingestion & Quality Control</h1>
        <p className="page-header__subtitle">
          Convert physical answer books into verified digital scripts before examiner assignment.
        </p>
        <div className="page-header__actions">
          {batches.length > 0 && (
            <select
              className="form-select"
              style={{ width: 200 }}
              value={activeBatchFilter}
              onChange={(e) => setActiveBatchFilter(e.target.value)}
            >
              <option value="">All Ingestion Batches</option>
              {batches.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          )}
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>
            + Ingest Digital Answer Book
          </button>
        </div>
      </div>

      {/* Top Status Strip */}
      <div className="stat-grid" style={{ marginBottom: 'var(--space-6)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Active Batches</div>
          <div className="stat-card__value">{batches.length || (answerBooks.length > 0 ? 1 : 0)}</div>
          <div className="stat-card__sub">{answerBooks.length} registered scripts</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Total Pages Ingested</div>
          <div className="stat-card__value">{totalPages}</div>
          <div className="stat-card__sub">Across all batches</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Passed Verification</div>
          <div className="stat-card__value" style={{ color: 'var(--status-approved-text)' }}>
            {passedCount}
          </div>
          <div className="stat-card__sub">No quality defects noted</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Quality Issues</div>
          <div className="stat-card__value" style={{ color: issuesCount > 0 ? 'var(--status-returned-text)' : 'inherit' }}>
            {issuesCount}
          </div>
          <div className="stat-card__sub">Requires review / rescan</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Ready for Evaluation</div>
          <div className="stat-card__value" style={{ color: 'var(--parchment-navy)' }}>
            {readyForEvalCount}
          </div>
          <div className="stat-card__sub">Pending examiner docket</div>
        </div>
      </div>

      {isLoading ? (
        <div className="state-container"><div className="spinner" /></div>
      ) : isError ? (
        <div className="state-container">
          <div className="state-title">Failed to load scan records</div>
        </div>
      ) : answerBooks.length === 0 ? (
        <div className="state-container">
          <div className="state-icon">📥</div>
          <div className="state-title">No Digital Scripts Ingested</div>
          <div className="state-body">
            Upload a complete answer book PDF or register a digital script batch to initiate ingestion and quality verification.
          </div>
          <div className="state-action">
            <button className="btn btn-primary" onClick={() => setShowModal(true)}>
              Ingest First Digital Answer Book
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 'var(--space-6)' }}>
          {/* LEFT: Booklet/Script Queue */}
          <div className="folio-card" style={{ padding: 0 }}>
            <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="folio-card__title">Ingested Scripts Queue ({filteredBooks.length})</span>
              <span className="label-mono" style={{ fontSize: 11 }}>Batch-centric queue</span>
            </div>
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Script Code</th>
                    <th>Exam</th>
                    <th>Pages</th>
                    <th>Quality Status</th>
                    <th>Batch</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredBooks.map((ab) => {
                    const exam = typeof ab.examId === 'object' ? (ab.examId as unknown as Exam) : null;
                    const isSelected = selectedBook?._id === ab._id;
                    const qStatus = ab.qualityStatus || 'READY';

                    return (
                      <tr
                        key={ab._id}
                        style={{
                          cursor: 'pointer',
                          background: isSelected ? 'rgba(14, 26, 43, 0.05)' : undefined,
                        }}
                        onClick={() => setSelectedId(ab._id)}
                      >
                        <td>
                          <span className="data-table__code">{ab.answerBookCode}</span>
                          <div className="label-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                            {ab.studentCode}
                          </div>
                        </td>
                        <td>
                          {exam ? (
                            <span style={{ fontSize: 12, fontWeight: 500 }}>{exam.subjectCode}</span>
                          ) : '—'}
                        </td>
                        <td>{ab.pageCount}</td>
                        <td>
                          <span
                            className="label-mono"
                            style={{
                              fontSize: 10,
                              padding: '2px 6px',
                              borderRadius: 2,
                              background:
                                qStatus === 'VERIFIED'
                                  ? 'var(--status-approved-bg)'
                                  : qStatus === 'QUALITY_REVIEW'
                                  ? 'var(--status-review-bg)'
                                  : qStatus === 'RESCAN_REQUIRED'
                                  ? 'var(--status-returned-bg)'
                                  : 'var(--parchment-border)',
                              color:
                                qStatus === 'VERIFIED'
                                  ? 'var(--status-approved-text)'
                                  : qStatus === 'QUALITY_REVIEW'
                                  ? 'var(--status-review-text)'
                                  : qStatus === 'RESCAN_REQUIRED'
                                  ? 'var(--status-returned-text)'
                                  : 'inherit',
                            }}
                          >
                            {qStatus}
                          </span>
                        </td>
                        <td className="label-mono" style={{ fontSize: 10 }}>
                          {ab.scanBatch || '—'}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <button
                            className={`btn btn-sm ${isSelected ? 'btn-primary' : 'btn-ghost'}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedId(ab._id);
                            }}
                          >
                            {isSelected ? 'Inspecting' : 'Select'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* RIGHT: Selected Script Detail */}
          <div>
            {selectedBook ? (
              <div className="folio-card">
                <div className="folio-card__header">
                  <span className="folio-card__title">Script Quality Inspector</span>
                </div>
                <div className="folio-card__body">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
                    <div>
                      <div className="label-caps">Answer Book Code</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700 }}>
                        {selectedBook.answerBookCode}
                      </div>
                    </div>
                    <StatusBadge status={selectedBook.status} />
                  </div>

                  <div className="divider" />

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
                    <div>
                      <div className="label-caps">Student Reference</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{selectedBook.studentCode}</div>
                    </div>
                    <div>
                      <div className="label-caps">Page Count</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{selectedBook.pageCount} pages</div>
                    </div>
                    <div>
                      <div className="label-caps">Ingestion Batch</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{selectedBook.scanBatch || 'Standard Ingestion'}</div>
                    </div>
                    <div>
                      <div className="label-caps">Quality Status</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600 }}>
                        {selectedBook.qualityStatus || 'READY'}
                      </div>
                    </div>
                  </div>

                  <div className="divider" />

                  {/* Quality Analysis section */}
                  <div style={{ marginBottom: 'var(--space-4)' }}>
                    <div className="label-caps" style={{ marginBottom: 6 }}>Quality Analysis Diagnostic</div>
                    <div
                      style={{
                        padding: 'var(--space-3)',
                        background: 'rgba(14, 26, 43, 0.03)',
                        border: '1px dashed var(--parchment-border)',
                        borderRadius: 'var(--radius-sm)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: 12,
                        color: 'var(--text-muted)',
                      }}
                    >
                      {selectedBook.qualityStatus === 'VERIFIED' ? (
                        <span>Verified: Complete page sequence intact. Ready for marking assignment.</span>
                      ) : selectedBook.qualityStatus === 'QUALITY_REVIEW' ? (
                        <span style={{ color: 'var(--status-review-text)' }}>Flagged: Examiner or scanning operator requested manual verification of page clarity.</span>
                      ) : selectedBook.qualityStatus === 'RESCAN_REQUIRED' ? (
                        <span style={{ color: 'var(--status-returned-text)' }}>Defect: Physical booklet requires re-scanning prior to examiner assignment.</span>
                      ) : (
                        <span>Quality analysis pending.</span>
                      )}
                    </div>
                  </div>

                  {/* Document Source */}
                  <div style={{ marginBottom: 'var(--space-5)' }}>
                    <div className="label-caps" style={{ marginBottom: 6 }}>Ingested Document Source</div>
                    {selectedBook.pdfUrl ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, wordBreak: 'break-all' }}>
                          {selectedBook.pdfUrl}
                        </span>
                        <a
                          href={selectedBook.pdfUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="btn btn-secondary btn-sm"
                        >
                          View PDF
                        </a>
                      </div>
                    ) : (
                      <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        Digital booklet registered via direct scanner interface. Waiting for imaging pipeline.
                      </div>
                    )}
                  </div>

                  {/* Operational Quality Actions */}
                  <div>
                    <div className="label-caps" style={{ marginBottom: 8 }}>Quality Control Actions</div>
                    <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                      <button
                        className="btn btn-sm btn-primary"
                        disabled={selectedBook.qualityStatus === 'VERIFIED' || updateQualityMutation.isPending}
                        onClick={() => updateQualityMutation.mutate({ id: selectedBook._id, qualityStatus: 'VERIFIED' })}
                      >
                        ✓ Mark Verified
                      </button>
                      <button
                        className="btn btn-sm btn-secondary"
                        disabled={selectedBook.qualityStatus === 'QUALITY_REVIEW' || updateQualityMutation.isPending}
                        onClick={() => updateQualityMutation.mutate({ id: selectedBook._id, qualityStatus: 'QUALITY_REVIEW' })}
                      >
                        ⚠ Flag Quality Review
                      </button>
                      <button
                        className="btn btn-sm btn-ghost"
                        disabled={selectedBook.qualityStatus === 'RESCAN_REQUIRED' || updateQualityMutation.isPending}
                        onClick={() => updateQualityMutation.mutate({ id: selectedBook._id, qualityStatus: 'RESCAN_REQUIRED' })}
                      >
                        ✕ Require Rescan
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="state-container">
                <div className="state-title">No Script Selected</div>
                <div className="state-body">Select an answer book from the queue to view quality diagnostics.</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Ingestion Modal */}
      {showModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowModal(false)}>
          <div className="modal modal--lg">
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow">Ingestion Pipeline</div>
                <div className="modal__title">Ingest Digital Answer Book (Batch / PDF)</div>
              </div>
              <button className="modal__close" onClick={() => setShowModal(false)}>✕</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal__body">
                <div className="form-grid" style={{ marginBottom: 'var(--space-4)' }}>
                  <div className="form-field form-field--full">
                    <label className="form-label">Target Examination <span className="required">*</span></label>
                    <select
                      className="form-select"
                      required
                      value={form.examId}
                      onChange={(e) => setForm((f) => ({ ...f, examId: e.target.value }))}
                    >
                      <option value="">— Select examination —</option>
                      {exams.map((ex) => (
                        <option key={ex._id} value={ex._id}>
                          {ex.title} ({ex.subjectCode}) · {ex.academicSession}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="form-field">
                    <label className="form-label">Answer Book Code <span className="required">*</span></label>
                    <input
                      className="form-input"
                      placeholder="e.g., AB2024101"
                      required
                      value={form.answerBookCode}
                      onChange={(e) => setForm((f) => ({ ...f, answerBookCode: e.target.value }))}
                    />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Student Roll / Identifier <span className="required">*</span></label>
                    <input
                      className="form-input"
                      placeholder="e.g., STU2024101"
                      required
                      value={form.studentCode}
                      onChange={(e) => setForm((f) => ({ ...f, studentCode: e.target.value }))}
                    />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Page Count <span className="required">*</span></label>
                    <input
                      className="form-input"
                      type="number"
                      min={1}
                      required
                      value={form.pageCount}
                      onChange={(e) => setForm((f) => ({ ...f, pageCount: e.target.value }))}
                    />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Scan Batch Identifier</label>
                    <input
                      className="form-input"
                      placeholder="e.g., BATCH-20241003-01"
                      value={form.scanBatch}
                      onChange={(e) => setForm((f) => ({ ...f, scanBatch: e.target.value }))}
                    />
                  </div>
                  <div className="form-field form-field--full">
                    <label className="form-label">Complete Answer Book PDF URL / Filepath</label>
                    <input
                      className="form-input"
                      placeholder="https://.../scans/AB2024101.pdf or /vault/scripts/AB2024101.pdf"
                      value={form.pdfUrl}
                      onChange={(e) => setForm((f) => ({ ...f, pdfUrl: e.target.value }))}
                    />
                    <div className="form-hint">
                      Ingest complete multi-page document as a single unit. Individual page splitting will happen automatically downstream.
                    </div>
                  </div>
                  <div className="form-field">
                    <label className="form-label">Initial Quality Verification</label>
                    <select
                      className="form-select"
                      value={form.qualityStatus}
                      onChange={(e) => setForm((f) => ({ ...f, qualityStatus: e.target.value as QualityStatus }))}
                    >
                      <option value="VERIFIED">VERIFIED (Ready for Marking)</option>
                      <option value="READY">READY (Pending Routine Check)</option>
                      <option value="QUALITY_REVIEW">QUALITY_REVIEW (Flagged for Review)</option>
                      <option value="RESCAN_REQUIRED">RESCAN_REQUIRED (Defective)</option>
                    </select>
                  </div>
                </div>

                {formError && (
                  <div className="form-error" style={{ padding: 'var(--space-3)', background: 'var(--status-returned-bg)', borderRadius: 'var(--radius-sm)' }}>
                    ⚠ {formError}
                  </div>
                )}
              </div>
              <div className="modal__footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={ingestMutation.isPending}>
                  {ingestMutation.isPending ? 'Ingesting Script…' : 'Complete Ingestion'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
