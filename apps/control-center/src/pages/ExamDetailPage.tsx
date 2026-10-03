import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { Exam, AnswerBook, Question, ExamStatus } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';

const EXAM_STATUSES: ExamStatus[] = [
  'DRAFT', 'READY', 'EVALUATION_OPEN', 'EVALUATION_CLOSED', 'MODERATION', 'FINALIZED'
];

interface QuestionFormData {
  questionNumber: string;
  text: string;
  maximumMarks: string;
  criteriaList: { criterion: string; marks: string }[];
}

const EMPTY_QUESTION_FORM: QuestionFormData = {
  questionNumber: '1',
  text: '',
  maximumMarks: '10',
  criteriaList: [{ criterion: 'Core answer correctness', marks: '6' }, { criterion: 'Methodology and explanation', marks: '4' }],
};

export function ExamDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [newStatus, setNewStatus] = useState('');
  const [showEditExamModal, setShowEditExamModal] = useState(false);
  const [examForm, setExamForm] = useState({
    title: '', subjectCode: '', subjectName: '', academicSession: '', maximumMarks: '', totalQuestions: ''
  });

  // Question modals
  const [showQuestionModal, setShowQuestionModal] = useState(false);
  const [editingQuestionId, setEditingQuestionId] = useState<string | null>(null);
  const [questionForm, setQuestionForm] = useState<QuestionFormData>(EMPTY_QUESTION_FORM);
  const [questionError, setQuestionError] = useState('');

  const { data, isLoading, isError } = useQuery<{ exam: Exam; answerBooks: AnswerBook[] }>({
    queryKey: ['exam', id],
    queryFn: async () => {
      const { data } = await apiClient.get(`/exams/${id}`);
      return data.data;
    },
  });

  const { data: questions = [], isLoading: isLoadingQuestions } = useQuery<Question[]>({
    queryKey: ['exam-questions', id],
    queryFn: async () => {
      const { data } = await apiClient.get(`/exams/${id}/questions`);
      return data.data;
    },
    enabled: Boolean(id),
  });

  const updateStatusMutation = useMutation({
    mutationFn: async (status: string) => {
      await apiClient.patch(`/exams/${id}`, { status });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['exam', id] });
      queryClient.invalidateQueries({ queryKey: ['exams'] });
      setNewStatus('');
    },
  });

  const updateExamMutation = useMutation({
    mutationFn: async (payload: object) => {
      await apiClient.patch(`/exams/${id}`, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['exam', id] });
      queryClient.invalidateQueries({ queryKey: ['exams'] });
      setShowEditExamModal(false);
    },
  });

  const saveQuestionMutation = useMutation({
    mutationFn: async (payload: object) => {
      if (editingQuestionId) {
        await apiClient.patch(`/questions/${editingQuestionId}`, payload);
      } else {
        await apiClient.post(`/exams/${id}/questions`, payload);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['exam-questions', id] });
      setShowQuestionModal(false);
      setEditingQuestionId(null);
      setQuestionForm(EMPTY_QUESTION_FORM);
      setQuestionError('');
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || 'Failed to save question';
      setQuestionError(msg);
    },
  });

  const deleteQuestionMutation = useMutation({
    mutationFn: async (qId: string) => {
      await apiClient.delete(`/questions/${qId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['exam-questions', id] });
    },
  });

  if (isLoading) return <div className="state-container"><div className="spinner" /></div>;
  if (isError || !data) return (
    <div className="state-container">
      <div className="state-title">Examination Not Found</div>
      <Link to="/exams" className="btn btn-secondary state-action">← Back to Examinations</Link>
    </div>
  );

  const { exam, answerBooks } = data;

  // Real overview metrics
  const totalBooks = answerBooks.length;
  const readyBooks = answerBooks.filter((b) => b.status === 'READY').length;
  const assignedBooks = answerBooks.filter((b) => b.status === 'ASSIGNED').length;
  const inProgressBooks = answerBooks.filter((b) => b.status === 'IN_PROGRESS').length;
  const submittedBooks = answerBooks.filter((b) => b.status === 'SUBMITTED' || b.status === 'UNDER_REVIEW').length;
  const approvedBooks = answerBooks.filter((b) => b.status === 'APPROVED' || b.status === 'FINALIZED').length;

  const openAddQuestion = () => {
    setEditingQuestionId(null);
    const nextNum = questions.length + 1;
    setQuestionForm({
      ...EMPTY_QUESTION_FORM,
      questionNumber: String(nextNum),
    });
    setQuestionError('');
    setShowQuestionModal(true);
  };

  const openEditQuestion = (q: Question) => {
    setEditingQuestionId(q._id);
    setQuestionForm({
      questionNumber: String(q.questionNumber),
      text: q.text,
      maximumMarks: String(q.maximumMarks),
      criteriaList: q.rubric && q.rubric.length > 0
        ? q.rubric.map((r) => ({ criterion: r.criterion, marks: String(r.marks) }))
        : [{ criterion: 'Accuracy', marks: String(q.maximumMarks) }],
    });
    setQuestionError('');
    setShowQuestionModal(true);
  };

  const handleQuestionSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setQuestionError('');
    saveQuestionMutation.mutate({
      questionNumber: parseInt(questionForm.questionNumber),
      text: questionForm.text,
      maximumMarks: parseFloat(questionForm.maximumMarks),
      rubric: questionForm.criteriaList
        .filter((c) => c.criterion.trim())
        .map((c) => ({ criterion: c.criterion.trim(), marks: parseFloat(c.marks) || 0 })),
    });
  };

  return (
    <div>
      <div className="breadcrumbs">
        <Link to="/exams">Examinations</Link>
        <span className="breadcrumbs__sep">›</span>
        <span>{exam.subjectCode}</span>
      </div>

      {/* EXAM HEADER */}
      <div className="page-header" style={{ marginBottom: 'var(--space-6)' }}>
        <div className="page-header__eyebrow">Institutional Examination Record</div>
        <h1 className="page-header__title">{exam.title}</h1>
        <p className="page-header__subtitle">
          {exam.subjectName} ({exam.subjectCode}) · Session: {exam.academicSession} · Max Marks: {exam.maximumMarks} · Total Questions: {exam.totalQuestions}
        </p>
        <div className="page-header__actions">
          <StatusBadge status={exam.status} />
          <button
            className="btn btn-secondary"
            onClick={() => {
              setExamForm({
                title: exam.title,
                subjectCode: exam.subjectCode,
                subjectName: exam.subjectName,
                academicSession: exam.academicSession,
                maximumMarks: String(exam.maximumMarks),
                totalQuestions: String(exam.totalQuestions),
              });
              setShowEditExamModal(true);
            }}
          >
            Edit Examination
          </button>
          {exam.status === 'EVALUATION_OPEN' ? (
            <button
              className="btn btn-secondary"
              disabled={updateStatusMutation.isPending}
              onClick={() => updateStatusMutation.mutate('EVALUATION_CLOSED')}
            >
              Close Evaluation
            </button>
          ) : (
            <button
              className="btn btn-primary"
              disabled={updateStatusMutation.isPending}
              onClick={() => updateStatusMutation.mutate('EVALUATION_OPEN')}
            >
              Open Evaluation
            </button>
          )}
        </div>
      </div>

      {/* EXAM OVERVIEW METRIC STRIP */}
      <div className="stat-grid" style={{ marginBottom: 'var(--space-6)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Total Answer Books</div>
          <div className="stat-card__value">{totalBooks}</div>
          <div className="stat-card__sub">Enrolled scripts</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Ready</div>
          <div className="stat-card__value">{readyBooks}</div>
          <div className="stat-card__sub">Pending examiner assignment</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Assigned</div>
          <div className="stat-card__value">{assignedBooks}</div>
          <div className="stat-card__sub">Awaiting evaluation start</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">In Progress</div>
          <div className="stat-card__value" style={{ color: 'var(--status-review-text)' }}>
            {inProgressBooks}
          </div>
          <div className="stat-card__sub">Being evaluated</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Submitted</div>
          <div className="stat-card__value">{submittedBooks}</div>
          <div className="stat-card__sub">In moderation review</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__eyebrow">Approved</div>
          <div className="stat-card__value" style={{ color: 'var(--status-approved-text)' }}>
            {approvedBooks}
          </div>
          <div className="stat-card__sub">Quality verified</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 'var(--space-6)' }}>
        {/* QUESTIONS / RUBRICS SECTION */}
        <div>
          <div className="folio-card">
            <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <span className="folio-card__title">Question Register & Evaluation Rubrics</span>
                <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  Deterministic marking guide & future AI copilot reference evidence
                </div>
              </div>
              <button className="btn btn-primary btn-sm" onClick={openAddQuestion}>
                + Add Question
              </button>
            </div>
            <div className="folio-card__body">
              {isLoadingQuestions ? (
                <div className="state-container"><div className="spinner" /></div>
              ) : questions.length === 0 ? (
                <div className="state-container" style={{ padding: 'var(--space-8)' }}>
                  <div className="state-icon">📝</div>
                  <div className="state-title">No Questions Registered</div>
                  <div className="state-body">
                    Add examination questions and scoring rubrics. Examiners and AI copilot will evaluate scripts against these exact criteria.
                  </div>
                  <div className="state-action">
                    <button className="btn btn-primary btn-sm" onClick={openAddQuestion}>
                      Add First Question
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                  {questions.map((q) => (
                    <div
                      key={q._id}
                      style={{
                        padding: 'var(--space-4)',
                        border: '1px solid var(--parchment-border)',
                        background: 'rgba(255, 255, 255, 0.4)',
                        borderRadius: 'var(--radius-sm)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                          <span
                            className="label-mono"
                            style={{
                              background: 'var(--parchment-navy)',
                              color: '#fff',
                              padding: '2px 8px',
                              borderRadius: 2,
                              fontWeight: 700,
                              fontSize: 12,
                            }}
                          >
                            Q{q.questionNumber}
                          </span>
                          <span style={{ fontWeight: 600, fontSize: 14 }}>
                            Maximum Marks: {q.maximumMarks}
                          </span>
                        </div>
                        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                          <button className="btn btn-ghost btn-sm" onClick={() => openEditQuestion(q)}>
                            Edit
                          </button>
                          <button
                            className="btn btn-ghost btn-sm"
                            style={{ color: 'var(--status-returned-text)' }}
                            onClick={() => {
                              if (window.confirm(`Delete Question ${q.questionNumber}?`)) {
                                deleteQuestionMutation.mutate(q._id);
                              }
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </div>

                      <div style={{ fontFamily: 'var(--font-serif)', fontSize: '0.95rem', marginBottom: 'var(--space-3)' }}>
                        {q.text}
                      </div>

                      {q.rubric && q.rubric.length > 0 && (
                        <div style={{ marginTop: 'var(--space-2)' }}>
                          <div className="label-caps" style={{ fontSize: 10, marginBottom: 4 }}>Scoring Rubric Breakdown</div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            {q.rubric.map((r, rIdx) => (
                              <div
                                key={rIdx}
                                style={{
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  fontSize: 12,
                                  fontFamily: 'var(--font-mono)',
                                  background: 'rgba(14, 26, 43, 0.03)',
                                  padding: '4px 8px',
                                  borderRadius: 2,
                                }}
                              >
                                <span>• {r.criterion}</span>
                                <span style={{ fontWeight: 600 }}>{r.marks} pts</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT: Answer Books & Docket */}
        <div>
          <div className="folio-card" style={{ marginBottom: 'var(--space-6)' }}>
            <div className="folio-card__header">
              <span className="folio-card__title">Examination Lifecycle Docket</span>
            </div>
            <div className="folio-card__body">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {[
                  { label: 'Subject Code', value: exam.subjectCode },
                  { label: 'Subject Name', value: exam.subjectName },
                  { label: 'Academic Session', value: exam.academicSession },
                  { label: 'Maximum Marks', value: exam.maximumMarks },
                  { label: 'Total Questions', value: exam.totalQuestions },
                  { label: 'Evaluation Status', value: exam.status },
                  { label: 'Registration Date', value: new Date(exam.createdAt).toLocaleDateString() },
                ].map(({ label, value }) => (
                  <div key={label} style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dotted var(--parchment-border)', paddingBottom: 4 }}>
                    <span className="label-caps">{label}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 500 }}>{value}</span>
                  </div>
                ))}
              </div>

              <div className="divider" />

              <div>
                <div className="label-caps" style={{ marginBottom: 6 }}>Manual Status Override</div>
                <select
                  className="form-select"
                  value={newStatus}
                  onChange={(e) => setNewStatus(e.target.value)}
                >
                  <option value="">— Select transition —</option>
                  {EXAM_STATUSES.filter((s) => s !== exam.status).map((s) => (
                    <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
                  ))}
                </select>
                <button
                  className="btn btn-secondary btn-sm"
                  style={{ marginTop: 'var(--space-2)', width: '100%' }}
                  disabled={!newStatus || updateStatusMutation.isPending}
                  onClick={() => newStatus && updateStatusMutation.mutate(newStatus)}
                >
                  {updateStatusMutation.isPending ? 'Updating…' : 'Apply Transition'}
                </button>
              </div>
            </div>
          </div>

          <div className="folio-card">
            <div className="folio-card__header">
              <span className="folio-card__title">Associated Answer Books ({answerBooks.length})</span>
            </div>
            <div className="folio-card__body" style={{ padding: 0 }}>
              {answerBooks.length === 0 ? (
                <div className="state-container" style={{ padding: 'var(--space-6)' }}>
                  <div className="state-body">No answer books linked to this exam yet.</div>
                </div>
              ) : (
                <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Code</th>
                        <th>Student</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {answerBooks.slice(0, 10).map((ab) => (
                        <tr key={ab._id}>
                          <td><span className="data-table__code">{ab.answerBookCode}</span></td>
                          <td><span className="data-table__code">{ab.studentCode}</span></td>
                          <td><StatusBadge status={ab.status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {answerBooks.length > 10 && (
                    <div style={{ padding: 'var(--space-3)', textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>
                      + {answerBooks.length - 10} more scripts
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Edit Exam Modal */}
      {showEditExamModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowEditExamModal(false)}>
          <div className="modal modal--lg">
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow">Modify Docket</div>
                <div className="modal__title">Edit Examination Details</div>
              </div>
              <button className="modal__close" onClick={() => setShowEditExamModal(false)}>✕</button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                updateExamMutation.mutate({
                  ...examForm,
                  maximumMarks: parseInt(examForm.maximumMarks),
                  totalQuestions: parseInt(examForm.totalQuestions),
                });
              }}
            >
              <div className="modal__body">
                <div className="form-grid" style={{ marginBottom: 'var(--space-4)' }}>
                  <div className="form-field form-field--full">
                    <label className="form-label">Examination Title</label>
                    <input
                      className="form-input"
                      value={examForm.title}
                      onChange={(e) => setExamForm((f) => ({ ...f, title: e.target.value }))}
                      required
                    />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Subject Code</label>
                    <input
                      className="form-input"
                      value={examForm.subjectCode}
                      onChange={(e) => setExamForm((f) => ({ ...f, subjectCode: e.target.value }))}
                      required
                    />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Subject Name</label>
                    <input
                      className="form-input"
                      value={examForm.subjectName}
                      onChange={(e) => setExamForm((f) => ({ ...f, subjectName: e.target.value }))}
                      required
                    />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Academic Session</label>
                    <input
                      className="form-input"
                      value={examForm.academicSession}
                      onChange={(e) => setExamForm((f) => ({ ...f, academicSession: e.target.value }))}
                      required
                    />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Maximum Marks</label>
                    <input
                      className="form-input"
                      type="number"
                      value={examForm.maximumMarks}
                      onChange={(e) => setExamForm((f) => ({ ...f, maximumMarks: e.target.value }))}
                      required
                    />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Total Questions</label>
                    <input
                      className="form-input"
                      type="number"
                      value={examForm.totalQuestions}
                      onChange={(e) => setExamForm((f) => ({ ...f, totalQuestions: e.target.value }))}
                      required
                    />
                  </div>
                </div>
              </div>
              <div className="modal__footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowEditExamModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={updateExamMutation.isPending}>
                  {updateExamMutation.isPending ? 'Saving…' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add / Edit Question Modal */}
      {showQuestionModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowQuestionModal(false)}>
          <div className="modal modal--lg">
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow">Question & Rubric Builder</div>
                <div className="modal__title">
                  {editingQuestionId ? `Edit Question ${questionForm.questionNumber}` : 'Register Examination Question'}
                </div>
              </div>
              <button className="modal__close" onClick={() => setShowQuestionModal(false)}>✕</button>
            </div>
            <form onSubmit={handleQuestionSubmit}>
              <div className="modal__body">
                <div className="form-grid" style={{ marginBottom: 'var(--space-4)' }}>
                  <div className="form-field">
                    <label className="form-label">Question Number <span className="required">*</span></label>
                    <input
                      className="form-input"
                      type="number"
                      min={1}
                      required
                      value={questionForm.questionNumber}
                      onChange={(e) => setQuestionForm((f) => ({ ...f, questionNumber: e.target.value }))}
                    />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Maximum Marks <span className="required">*</span></label>
                    <input
                      className="form-input"
                      type="number"
                      step="0.5"
                      min={0.5}
                      required
                      value={questionForm.maximumMarks}
                      onChange={(e) => setQuestionForm((f) => ({ ...f, maximumMarks: e.target.value }))}
                    />
                  </div>
                  <div className="form-field form-field--full">
                    <label className="form-label">Question Text / Statement <span className="required">*</span></label>
                    <textarea
                      className="form-input"
                      rows={3}
                      placeholder="State the problem formulation or question statement..."
                      required
                      value={questionForm.text}
                      onChange={(e) => setQuestionForm((f) => ({ ...f, text: e.target.value }))}
                    />
                  </div>
                </div>

                <div className="divider" />

                {/* Rubrics Builder */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <div>
                      <div className="label-caps">Scoring Rubric Criteria</div>
                      <div className="form-hint">Define marking criteria breakdown for accurate evaluation</div>
                    </div>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() =>
                        setQuestionForm((f) => ({
                          ...f,
                          criteriaList: [...f.criteriaList, { criterion: '', marks: '2' }],
                        }))
                      }
                    >
                      + Add Criterion
                    </button>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                    {questionForm.criteriaList.map((crit, idx) => (
                      <div key={idx} style={{ display: 'grid', gridTemplateColumns: '1fr 100px auto', gap: 'var(--space-2)', alignItems: 'center' }}>
                        <input
                          className="form-input"
                          placeholder="Criterion description (e.g., Derivation steps)"
                          value={crit.criterion}
                          onChange={(e) => {
                            const val = e.target.value;
                            setQuestionForm((f) => ({
                              ...f,
                              criteriaList: f.criteriaList.map((c, i) => (i === idx ? { ...c, criterion: val } : c)),
                            }));
                          }}
                        />
                        <input
                          className="form-input"
                          type="number"
                          step="0.5"
                          placeholder="Marks"
                          value={crit.marks}
                          onChange={(e) => {
                            const val = e.target.value;
                            setQuestionForm((f) => ({
                              ...f,
                              criteriaList: f.criteriaList.map((c, i) => (i === idx ? { ...c, marks: val } : c)),
                            }));
                          }}
                        />
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          style={{ color: 'var(--status-returned-text)' }}
                          onClick={() =>
                            setQuestionForm((f) => ({
                              ...f,
                              criteriaList: f.criteriaList.filter((_, i) => i !== idx),
                            }))
                          }
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                {questionError && (
                  <div className="form-error" style={{ marginTop: 'var(--space-4)', padding: 'var(--space-3)', background: 'var(--status-returned-bg)', borderRadius: 'var(--radius-sm)' }}>
                    ⚠ {questionError}
                  </div>
                )}
              </div>
              <div className="modal__footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowQuestionModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={saveQuestionMutation.isPending}>
                  {saveQuestionMutation.isPending ? 'Saving Question…' : editingQuestionId ? 'Update Question' : 'Add Question'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
