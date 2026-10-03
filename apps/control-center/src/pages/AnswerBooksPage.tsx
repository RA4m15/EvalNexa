import React, { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Exam, User } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';
import { useSocketEvents } from '../hooks/useSocketEvents';

interface CreateAnswerBookForm {
  examId: string;
  answerBookCode: string;
  studentCode: string;
  pageCount: string;
  scanBatch?: string;
  pdfUrl?: string;
}

const EMPTY_FORM: CreateAnswerBookForm = {
  examId: '',
  answerBookCode: '',
  studentCode: '',
  pageCount: '12',
  scanBatch: '',
  pdfUrl: '',
};

export function AnswerBooksPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [assignExaminerId, setAssignExaminerId] = useState('');
  const [form, setForm] = useState<CreateAnswerBookForm>(EMPTY_FORM);
  const [formError, setFormError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const { data: answerBooks = [], isLoading, isError } = useQuery<AnswerBook[]>({
    queryKey: ['answer-books', statusFilter],
    queryFn: async () => {
      const params = statusFilter ? `?status=${statusFilter}` : '';
      const { data } = await apiClient.get(`/answer-books${params}`);
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

  const { data: examiners = [] } = useQuery<User[]>({
    queryKey: ['examiners'],
    queryFn: async () => {
      const { data } = await apiClient.get('/users?role=EXAMINER');
      return data.data;
    },
  });

  const handlers = useCallback(() => ({
    'answerbook.created': () => queryClient.invalidateQueries({ queryKey: ['answer-books'] }),
    'answerbook.assigned': () => queryClient.invalidateQueries({ queryKey: ['answer-books'] }),
    'answerbook.status.changed': () => queryClient.invalidateQueries({ queryKey: ['answer-books'] }),
    'evaluation.started': () => queryClient.invalidateQueries({ queryKey: ['answer-books'] }),
    'evaluation.submitted': () => queryClient.invalidateQueries({ queryKey: ['answer-books'] }),
    'moderation.approved': () => queryClient.invalidateQueries({ queryKey: ['answer-books'] }),
    'moderation.returned': () => queryClient.invalidateQueries({ queryKey: ['answer-books'] }),
  }), [queryClient]);
  useSocketEvents(handlers());

  const createMutation = useMutation({
    mutationFn: async (payload: object) => {
      const { data } = await apiClient.post('/answer-books', payload);
      return data;
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['answer-books'] });
      setShowRegisterModal(false);
      setForm(EMPTY_FORM);
      setFormError('');
      if (res?.data?._id) setSelectedId(res.data._id);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || 'Failed to register answer book';
      setFormError(msg);
    },
  });

  const assignMutation = useMutation({
    mutationFn: async ({ answerBookId, examinerId }: { answerBookId: string; examinerId: string }) => {
      const { data } = await apiClient.post(`/answer-books/${answerBookId}/assign`, { examinerId });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['answer-books'] });
      setShowAssignModal(false);
      setAssignExaminerId('');
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || 'Failed to assign examiner';
      alert(msg);
    },
  });

  const handleRegisterSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    createMutation.mutate({
      ...form,
      pageCount: parseInt(form.pageCount) || 1,
    });
  };

  const selectedBook = answerBooks.find((b) => b._id === selectedId) || answerBooks[0] || null;
  const selectedExam = selectedBook && typeof selectedBook.examId === 'object' ? (selectedBook.examId as unknown as Exam) : null;
  const selectedExaminer = selectedBook && typeof selectedBook.assignedExaminerId === 'object' ? (selectedBook.assignedExaminerId as unknown as User) : null;

  return (
    <div>
      <div className="page-header">
        <div className="page-header__eyebrow">Control Center · Answer Book Register</div>
        <h1 className="page-header__title">Answer Book Register</h1>
        <p className="page-header__subtitle">
          Track digital script booklets, verify institutional custody, and manage examiner docket assignment.
        </p>
        <div className="page-header__actions">
          <select
            className="form-select"
            style={{ width: 180 }}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All Statuses</option>
            {['READY','ASSIGNED','IN_PROGRESS','SUBMITTED','UNDER_REVIEW','APPROVED','RETURNED','FINALIZED'].map((s) => (
              <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
            ))}
          </select>
          <button className="btn btn-primary" onClick={() => setShowRegisterModal(true)}>
            + Register Answer Book
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="state-container"><div className="spinner" /></div>
      ) : isError ? (
        <div className="state-container">
          <div className="state-title">Failed to load answer books</div>
          <button className="btn btn-secondary state-action" onClick={() => queryClient.invalidateQueries({ queryKey: ['answer-books'] })}>
            Retry
          </button>
        </div>
      ) : answerBooks.length === 0 ? (
        <div className="state-container">
          <div className="state-icon">📄</div>
          <div className="state-title">No Answer Books Registered</div>
          <div className="state-body">
            {statusFilter
              ? `No answer books found with status "${statusFilter.replace(/_/g, ' ')}".`
              : 'No answer books have been registered yet. Register an answer book to begin the evaluation workflow.'}
          </div>
          <div className="state-action">
            {statusFilter ? (
              <button className="btn btn-secondary" onClick={() => setStatusFilter('')}>Clear Filter</button>
            ) : (
              <button className="btn btn-primary" onClick={() => setShowRegisterModal(true)}>Register Answer Book</button>
            )}
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1.45fr 1fr', gap: 'var(--space-6)' }}>
          {/* LEFT: Answer Book Queue (Booklets in Stack) */}
          <div className="folio-card" style={{ padding: 0 }}>
            <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="folio-card__title">Answer Book Queue ({answerBooks.length})</span>
              <span className="label-mono" style={{ fontSize: 11 }}>Booklets in stack</span>
            </div>
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Answer Book Code</th>
                    <th>Exam</th>
                    <th>Student Code</th>
                    <th>Pages</th>
                    <th>Status</th>
                    <th>Examiner</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {answerBooks.map((ab) => {
                    const exam = typeof ab.examId === 'object' ? (ab.examId as unknown as Exam) : null;
                    const examiner = typeof ab.assignedExaminerId === 'object' ? (ab.assignedExaminerId as unknown as User) : null;
                    const isSelected = selectedBook?._id === ab._id;

                    return (
                      <tr
                        key={ab._id}
                        style={{
                          cursor: 'pointer',
                          background: isSelected ? 'rgba(14, 26, 43, 0.05)' : undefined,
                        }}
                        onClick={() => setSelectedId(ab._id)}
                      >
                        <td><span className="data-table__code">{ab.answerBookCode}</span></td>
                        <td>
                          {exam ? (
                            <span style={{ fontSize: 12, fontWeight: 500 }}>{exam.subjectCode}</span>
                          ) : '—'}
                        </td>
                        <td><span className="data-table__code" style={{ fontSize: 11 }}>{ab.studentCode}</span></td>
                        <td>{ab.pageCount}</td>
                        <td><StatusBadge status={ab.status} /></td>
                        <td style={{ fontSize: 12 }}>
                          {examiner ? examiner.name : <span style={{ color: 'var(--text-faint)' }}>Unassigned</span>}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <button
                            className={`btn btn-sm ${isSelected ? 'btn-primary' : 'btn-ghost'}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedId(ab._id);
                            }}
                          >
                            {isSelected ? 'Selected' : 'View'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* RIGHT: Selected Answer Book Inspector */}
          <div>
            {selectedBook ? (
              <div className="folio-card">
                <div className="folio-card__header">
                  <span className="folio-card__title">Selected Answer Book</span>
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

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                    {[
                      { label: 'Examination', value: selectedExam ? `${selectedExam.title} (${selectedExam.subjectCode})` : '—' },
                      { label: 'Academic Session', value: selectedExam?.academicSession || '—' },
                      { label: 'Student Identifier', value: selectedBook.studentCode },
                      { label: 'Page Count', value: `${selectedBook.pageCount} Pages` },
                      {
                        label: 'Assigned Examiner',
                        value: selectedExaminer ? `${selectedExaminer.name} (${selectedExaminer.email})` : 'Unassigned',
                      },
                      { label: 'Quality Status', value: selectedBook.qualityStatus || 'READY' },
                      { label: 'Ingestion Batch', value: selectedBook.scanBatch || 'Direct Registration' },
                      { label: 'Created Time', value: new Date(selectedBook.createdAt).toLocaleString() },
                      { label: 'Updated Time', value: new Date(selectedBook.updatedAt).toLocaleString() },
                    ].map(({ label, value }) => (
                      <div key={label} style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dotted var(--parchment-border)', paddingBottom: 4 }}>
                        <span className="label-caps">{label}</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, textAlign: 'right', maxWidth: '60%' }}>
                          {value}
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className="divider" />

                  {/* Actions */}
                  <div>
                    <div className="label-caps" style={{ marginBottom: 8 }}>Docket Actions</div>
                    <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => {
                          setAssignExaminerId(selectedExaminer?._id || '');
                          setShowAssignModal(true);
                        }}
                      >
                        {selectedExaminer ? 'Reassign Examiner' : 'Assign Examiner'}
                      </button>
                      {selectedBook.pdfUrl && (
                        <a
                          href={selectedBook.pdfUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="btn btn-secondary btn-sm"
                        >
                          View Document
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="state-container">
                <div className="state-title">No Answer Book Selected</div>
                <div className="state-body">Select a booklet from the stack on the left to view docket details.</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Register Modal */}
      {showRegisterModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowRegisterModal(false)}>
          <div className="modal">
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow">Answer Book Register</div>
                <div className="modal__title">Register Answer Book</div>
              </div>
              <button className="modal__close" onClick={() => setShowRegisterModal(false)}>✕</button>
            </div>
            <form onSubmit={handleRegisterSubmit}>
              <div className="modal__body">
                <div className="form-grid form-grid--1" style={{ gap: 'var(--space-4)' }}>
                  <div className="form-field">
                    <label className="form-label">Examination <span className="required">*</span></label>
                    <select
                      className="form-select"
                      required
                      value={form.examId}
                      onChange={(e) => setForm((f) => ({ ...f, examId: e.target.value }))}
                    >
                      <option value="">— Select examination —</option>
                      {exams.map((exam) => (
                        <option key={exam._id} value={exam._id}>{exam.title} ({exam.subjectCode})</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-field">
                    <label className="form-label">Answer Book Code <span className="required">*</span></label>
                    <input
                      className="form-input"
                      placeholder="e.g., AB2024001"
                      required
                      value={form.answerBookCode}
                      onChange={(e) => setForm((f) => ({ ...f, answerBookCode: e.target.value }))}
                    />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Student Code <span className="required">*</span></label>
                    <input
                      className="form-input"
                      placeholder="e.g., STU2024001"
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
                </div>
                {formError && (
                  <div className="form-error mt-4" style={{ padding: 'var(--space-3)', background: 'var(--status-returned-bg)', borderRadius: 'var(--radius-sm)' }}>
                    ⚠ {formError}
                  </div>
                )}
              </div>
              <div className="modal__footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowRegisterModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Registering…' : 'Register Answer Book'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Assign Examiner Modal */}
      {showAssignModal && selectedBook && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowAssignModal(false)}>
          <div className="modal">
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow">Assignment Docket</div>
                <div className="modal__title">Assign Examiner to {selectedBook.answerBookCode}</div>
              </div>
              <button className="modal__close" onClick={() => setShowAssignModal(false)}>✕</button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!assignExaminerId) return;
                assignMutation.mutate({
                  answerBookId: selectedBook._id,
                  examinerId: assignExaminerId,
                });
              }}
            >
              <div className="modal__body">
                <div className="form-field">
                  <label className="form-label">Select Accredited Examiner <span className="required">*</span></label>
                  <select
                    className="form-select"
                    required
                    value={assignExaminerId}
                    onChange={(e) => setAssignExaminerId(e.target.value)}
                  >
                    <option value="">— Select examiner —</option>
                    {examiners.map((ex) => (
                      <option key={ex._id} value={ex._id}>
                        {ex.name} ({ex.email})
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="modal__footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowAssignModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={assignMutation.isPending || !assignExaminerId}>
                  {assignMutation.isPending ? 'Assigning…' : 'Confirm Assignment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
