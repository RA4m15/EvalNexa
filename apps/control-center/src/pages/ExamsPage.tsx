import React, { useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { Exam, AnswerBook } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';
import { useSocketEvents } from '../hooks/useSocketEvents';

interface ExamForm {
  title: string;
  subjectCode: string;
  subjectName: string;
  academicSession: string;
  maximumMarks: string;
  totalQuestions: string;
}

const EMPTY_FORM: ExamForm = {
  title: '',
  subjectCode: '',
  subjectName: '',
  academicSession: '',
  maximumMarks: '',
  totalQuestions: '',
};

export function ExamsPage() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [editingExamId, setEditingExamId] = useState<string | null>(null);
  const [form, setForm] = useState<ExamForm>(EMPTY_FORM);
  const [formError, setFormError] = useState('');

  const { data: exams = [], isLoading, isError } = useQuery<Exam[]>({
    queryKey: ['exams'],
    queryFn: async () => {
      const { data } = await apiClient.get('/exams');
      return data.data;
    },
  });

  const { data: answerBooks = [] } = useQuery<AnswerBook[]>({
    queryKey: ['answer-books'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books');
      return data.data;
    },
  });

  const handlers = useCallback(() => ({
    'exam.created': () => queryClient.invalidateQueries({ queryKey: ['exams'] }),
    'exam.updated': () => queryClient.invalidateQueries({ queryKey: ['exams'] }),
    'answerbook.created': () => queryClient.invalidateQueries({ queryKey: ['answer-books'] }),
    'answerbook.status.changed': () => queryClient.invalidateQueries({ queryKey: ['answer-books'] }),
    'evaluation.submitted': () => queryClient.invalidateQueries({ queryKey: ['answer-books'] }),
  }), [queryClient]);
  useSocketEvents(handlers());

  const saveMutation = useMutation({
    mutationFn: async (payload: object) => {
      if (editingExamId) {
        const { data } = await apiClient.patch(`/exams/${editingExamId}`, payload);
        return data;
      }
      const { data } = await apiClient.post('/exams', payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['exams'] });
      setShowModal(false);
      setEditingExamId(null);
      setForm(EMPTY_FORM);
      setFormError('');
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || 'Failed to save examination';
      setFormError(msg);
    },
  });

  const statusMutation = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: string }) => {
      const { data } = await apiClient.patch(`/exams/${id}`, { status });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['exams'] });
    },
  });

  const openCreateModal = () => {
    setEditingExamId(null);
    setForm(EMPTY_FORM);
    setFormError('');
    setShowModal(true);
  };

  const openEditModal = (exam: Exam) => {
    setEditingExamId(exam._id);
    setForm({
      title: exam.title,
      subjectCode: exam.subjectCode,
      subjectName: exam.subjectName,
      academicSession: exam.academicSession,
      maximumMarks: String(exam.maximumMarks),
      totalQuestions: String(exam.totalQuestions),
    });
    setFormError('');
    setShowModal(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    saveMutation.mutate({
      ...form,
      maximumMarks: parseInt(form.maximumMarks),
      totalQuestions: parseInt(form.totalQuestions),
    });
  };

  const field = (key: keyof ExamForm) => ({
    value: form[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [key]: e.target.value })),
  });

  return (
    <div>
      <div className="page-header">
        <div className="page-header__eyebrow">Control Center · Examinations</div>
        <h1 className="page-header__title">Examination Register</h1>
        <p className="page-header__subtitle">
          Manage institutional examinations, configure question papers & rubrics, and govern the evaluation lifecycle.
        </p>
        <div className="page-header__actions">
          <button className="btn btn-primary" onClick={openCreateModal}>
            + Register New Examination
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="state-container"><div className="spinner" /></div>
      ) : isError ? (
        <div className="state-container">
          <div className="state-title">Failed to load examinations</div>
          <button className="btn btn-secondary state-action" onClick={() => queryClient.invalidateQueries({ queryKey: ['exams'] })}>
            Retry
          </button>
        </div>
      ) : exams.length === 0 ? (
        <div className="state-container">
          <div className="state-icon">📋</div>
          <div className="state-title">No Examinations on Record</div>
          <div className="state-body">No examinations have been created yet. Register the first examination to begin the evaluation workflow.</div>
          <div className="state-action">
            <button className="btn btn-primary" onClick={openCreateModal}>Register Examination</button>
          </div>
        </div>
      ) : (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Examination</th>
                <th>Subject</th>
                <th>Session</th>
                <th>Scripts</th>
                <th>Evaluated</th>
                <th>Status</th>
                <th>Created</th>
                <th style={{ textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {exams.map((exam) => {
                const examBooks = answerBooks.filter((ab) => {
                  const eid = typeof ab.examId === 'object' ? (ab.examId as any)._id : ab.examId;
                  return eid === exam._id;
                });
                const totalScripts = examBooks.length;
                const evaluatedScripts = examBooks.filter(
                  (ab) => ab.status === 'SUBMITTED' || ab.status === 'APPROVED' || ab.status === 'FINALIZED'
                ).length;

                const isEvaluationOpen = exam.status === 'EVALUATION_OPEN';

                return (
                  <tr key={exam._id}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{exam.title}</div>
                      <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        Max {exam.maximumMarks} Marks · {exam.totalQuestions} Questions
                      </div>
                    </td>
                    <td>
                      <span className="data-table__code">{exam.subjectCode}</span>
                      <div style={{ fontSize: 12, marginTop: 2 }}>{exam.subjectName}</div>
                    </td>
                    <td>{exam.academicSession}</td>
                    <td className="label-mono" style={{ fontSize: 13 }}>{totalScripts}</td>
                    <td className="label-mono" style={{ fontSize: 13 }}>{evaluatedScripts}</td>
                    <td><StatusBadge status={exam.status} /></td>
                    <td className="label-mono" style={{ fontSize: 11 }}>
                      {new Date(exam.createdAt).toLocaleDateString()}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                        <Link to={`/exams/${exam._id}`} className="btn btn-ghost btn-sm">
                          Open
                        </Link>
                        <button className="btn btn-ghost btn-sm" onClick={() => openEditModal(exam)}>
                          Edit
                        </button>
                        {isEvaluationOpen ? (
                          <button
                            className="btn btn-secondary btn-sm"
                            disabled={statusMutation.isPending}
                            onClick={() => statusMutation.mutate({ id: exam._id, status: 'EVALUATION_CLOSED' })}
                          >
                            Close Evaluation
                          </button>
                        ) : (
                          <button
                            className="btn btn-secondary btn-sm"
                            disabled={statusMutation.isPending}
                            onClick={() => statusMutation.mutate({ id: exam._id, status: 'EVALUATION_OPEN' })}
                          >
                            Open Evaluation
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Create / Edit Exam Modal */}
      {showModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowModal(false)}>
          <div className="modal modal--lg">
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow">Examination Register</div>
                <div className="modal__title">
                  {editingExamId ? 'Edit Examination Record' : 'Register New Examination'}
                </div>
              </div>
              <button className="modal__close" onClick={() => setShowModal(false)}>✕</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal__body">
                <div className="form-grid" style={{ marginBottom: 'var(--space-4)' }}>
                  <div className="form-field form-field--full">
                    <label className="form-label">Examination Title <span className="required">*</span></label>
                    <input className="form-input" placeholder="e.g., Final Year Mathematics Paper I" required {...field('title')} />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Subject Code <span className="required">*</span></label>
                    <input className="form-input" placeholder="e.g., MATH301" required {...field('subjectCode')} />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Subject Name <span className="required">*</span></label>
                    <input className="form-input" placeholder="e.g., Advanced Calculus" required {...field('subjectName')} />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Academic Session <span className="required">*</span></label>
                    <input className="form-input" placeholder="e.g., 2024-25 Semester I" required {...field('academicSession')} />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Maximum Marks <span className="required">*</span></label>
                    <input className="form-input" type="number" min={1} placeholder="e.g., 100" required {...field('maximumMarks')} />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Total Questions <span className="required">*</span></label>
                    <input className="form-input" type="number" min={1} placeholder="e.g., 10" required {...field('totalQuestions')} />
                  </div>
                </div>
                {formError && (
                  <div className="form-error" style={{ padding: 'var(--space-3)', background: 'var(--status-returned-bg)', borderRadius: 'var(--radius-sm)' }}>
                    ⚠ {formError}
                  </div>
                )}
              </div>
              <div className="modal__footer">
                <button type="button" className="btn btn-secondary" onClick={() => { setShowModal(false); setEditingExamId(null); setForm(EMPTY_FORM); }}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={saveMutation.isPending}>
                  {saveMutation.isPending ? 'Saving Record…' : editingExamId ? 'Update Examination' : 'Register Examination'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
