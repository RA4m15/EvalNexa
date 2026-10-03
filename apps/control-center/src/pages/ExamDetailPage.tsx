import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { Exam, AnswerBook, Question, ExamStatus } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';
import { useSocketEvents } from '../hooks/useSocketEvents';

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
  criteriaList: [
    { criterion: 'Core conceptual clarity and definition', marks: '5' },
    { criterion: 'Analytical methodology & reasoning', marks: '5' },
  ],
};

export function ExamDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const [showEditExamModal, setShowEditExamModal] = useState(false);
  const [examForm, setExamForm] = useState({
    title: '',
    subjectCode: '',
    subjectName: '',
    academicSession: '',
    maximumMarks: '',
    totalQuestions: '',
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

  const handlers = useCallback(
    () => ({
      'exam.updated': () => queryClient.invalidateQueries({ queryKey: ['exam', id] }),
      'question.created': () => queryClient.invalidateQueries({ queryKey: ['exam-questions', id] }),
      'question.updated': () => queryClient.invalidateQueries({ queryKey: ['exam-questions', id] }),
      'answerbook.created': () => queryClient.invalidateQueries({ queryKey: ['exam', id] }),
      'answerbook.status.changed': () => queryClient.invalidateQueries({ queryKey: ['exam', id] }),
    }),
    [queryClient, id]
  );
  useSocketEvents(handlers());

  const updateStatusMutation = useMutation({
    mutationFn: async (status: string) => {
      await apiClient.patch(`/exams/${id}`, { status });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['exam', id] });
      queryClient.invalidateQueries({ queryKey: ['exams'] });
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
        const { data } = await apiClient.patch(`/exams/${id}/questions/${editingQuestionId}`, payload);
        return data;
      }
      const { data } = await apiClient.post(`/exams/${id}/questions`, payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['exam-questions', id] });
      queryClient.invalidateQueries({ queryKey: ['exam', id] });
      setShowQuestionModal(false);
      setEditingQuestionId(null);
      setQuestionForm(EMPTY_QUESTION_FORM);
      setQuestionError('');
    },
    onError: (err: any) => {
      setQuestionError(err.response?.data?.message || 'Failed to save question');
    },
  });

  const exam = data?.exam;
  const answerBooks = data?.answerBooks || [];

  useEffect(() => {
    if (exam) {
      setExamForm({
        title: exam.title,
        subjectCode: exam.subjectCode,
        subjectName: exam.subjectName,
        academicSession: exam.academicSession,
        maximumMarks: String(exam.maximumMarks),
        totalQuestions: String(exam.totalQuestions),
      });
    }
  }, [exam]);

  if (isLoading) {
    return <div className="state-container"><div className="spinner" /></div>;
  }

  if (isError || !exam) {
    return (
      <div className="state-container">
        <div className="state-title">Examination Dossier Not Found</div>
        <div className="state-body">The requested examination could not be loaded from MongoDB.</div>
        <Link to="/exams" className="btn btn-primary state-action">← Return to Examination Register</Link>
      </div>
    );
  }

  const isEvaluationOpen = exam.status === 'EVALUATION_OPEN';

  return (
    <div>
      {/* Header & Status (Section 18) */}
      <div className="page-header" style={{ marginBottom: 'var(--space-6)' }}>
        <div>
          <div className="page-header__eyebrow">
            <Link to="/exams" style={{ color: 'inherit', textDecoration: 'none' }}>Examinations</Link> · {exam.subjectCode}
          </div>
          <h1 className="page-header__title">{exam.title}</h1>
          <p className="page-header__subtitle">
            {exam.subjectName} · Academic Session: {exam.academicSession} · Maximum Marks: {exam.maximumMarks}
          </p>
        </div>
        <div className="page-header__actions" style={{ display: 'flex', gap: 'var(--space-3)' }}>
          <button className="btn btn-secondary" onClick={() => setShowEditExamModal(true)}>
            Edit Examination
          </button>
          <button
            className={`btn ${isEvaluationOpen ? 'btn-secondary' : 'btn-primary'}`}
            onClick={() => updateStatusMutation.mutate(isEvaluationOpen ? 'EVALUATION_CLOSED' : 'EVALUATION_OPEN')}
            disabled={updateStatusMutation.isPending}
          >
            {isEvaluationOpen ? 'Close Evaluation' : 'Open Evaluation'}
          </button>
        </div>
      </div>

      {/* Summary Strip: Maximum Marks, Questions, Digital Scripts */}
      <div className="folio-card" style={{ marginBottom: 'var(--space-6)', padding: 'var(--space-4) var(--space-6)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-4)', alignItems: 'center' }}>
          <div>
            <div className="label-caps" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Status</div>
            <StatusBadge status={exam.status} />
          </div>

          <div>
            <div className="label-caps" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Maximum Marks</div>
            <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>{exam.maximumMarks}</div>
          </div>

          <div>
            <div className="label-caps" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Questions Configured</div>
            <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>
              {questions.length} / {exam.totalQuestions}
            </div>
          </div>

          <div>
            <div className="label-caps" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Digital Scripts</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
              <span style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>{answerBooks.length}</span>
              <Link to={`/scan-center?examId=${exam._id}`} className="btn btn-primary btn-sm" style={{ textDecoration: 'none' }}>
                + Scan Scripts
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Questions & Scoring Rubrics Section (Section 18: Questions, Maximum Marks, Rubric) */}
      <div className="folio-card">
        <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="folio-card__title">Questions & Scoring Rubrics ({questions.length})</span>
            <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
              Scoring criteria used by examiners during digital marking
            </div>
          </div>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => {
              setEditingQuestionId(null);
              setQuestionForm({
                questionNumber: String(questions.length + 1),
                text: '',
                maximumMarks: '10',
                criteriaList: [
                  { criterion: 'Core answer correctness', marks: '6' },
                  { criterion: 'Methodology and explanation', marks: '4' },
                ],
              });
              setShowQuestionModal(true);
            }}
          >
            + Add Question & Rubric
          </button>
        </div>

        <div className="folio-card__body">
          {isLoadingQuestions ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : questions.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-8)' }}>
              <div className="state-icon">📋</div>
              <div className="state-title">No Questions Configured</div>
              <div className="state-body">
                Define questions and scoring criteria so examiners can mark student submissions accurately.
              </div>
              <div className="state-action">
                <button
                  className="btn btn-primary"
                  onClick={() => setShowQuestionModal(true)}
                >
                  + Add Question 1
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
                    background: 'var(--parchment-panel)',
                    border: '1px solid var(--parchment-border)',
                    borderRadius: 'var(--radius-sm)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-3)' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span
                          className="label-mono"
                          style={{
                            fontWeight: 700,
                            fontSize: '13px',
                            padding: '2px 8px',
                            background: 'rgba(14, 26, 43, 0.08)',
                            borderRadius: 2,
                            color: 'var(--parchment-navy)',
                          }}
                        >
                          QUESTION {q.questionNumber}
                        </span>
                        <span style={{ fontSize: 'var(--text-table)', fontWeight: 600, color: 'var(--text-primary)' }}>
                          Max Marks: {q.maximumMarks}
                        </span>
                      </div>
                      <div style={{ fontSize: 'var(--text-body)', marginTop: 8, color: 'var(--text-secondary)' }}>
                        {q.text}
                      </div>
                    </div>

                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        setEditingQuestionId(q._id);
                        setQuestionForm({
                          questionNumber: String(q.questionNumber),
                          text: q.text,
                          maximumMarks: String(q.maximumMarks),
                          criteriaList: (q.rubric || []).map((c: any) => ({
                            criterion: c.criterion,
                            marks: String(c.marks),
                          })),
                        });
                        setShowQuestionModal(true);
                      }}
                    >
                      Edit Rubric
                    </button>
                  </div>

                  {/* Rubric Criteria List */}
                  {q.rubric && q.rubric.length > 0 && (
                    <div style={{ marginTop: 'var(--space-3)', borderTop: '1px dashed var(--parchment-border)', paddingTop: 'var(--space-3)' }}>
                      <div className="label-caps" style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 6 }}>
                        Scoring Rubric Breakdown
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {q.rubric.map((crit: any, cIdx: number) => (
                          <div
                            key={cIdx}
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              fontSize: 'var(--text-metadata)',
                              padding: '4px 8px',
                              background: '#FCFAF6',
                              borderRadius: 2,
                            }}
                          >
                            <span>{crit.criterion}</span>
                            <strong className="label-mono">{crit.marks} pts</strong>
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

      {/* Edit Exam Modal */}
      {showEditExamModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowEditExamModal(false)}>
          <div className="modal">
            <div className="modal__header">
              <div className="modal__title">Edit Examination Configuration</div>
              <button className="modal__close" onClick={() => setShowEditExamModal(false)}>✕</button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                updateExamMutation.mutate({
                  ...examForm,
                  maximumMarks: parseInt(examForm.maximumMarks, 10) || 100,
                  totalQuestions: parseInt(examForm.totalQuestions, 10) || 5,
                });
              }}
            >
              <div className="modal__body">
                <div className="form-field" style={{ marginBottom: 'var(--space-4)' }}>
                  <label className="form-label">Examination Title</label>
                  <input
                    className="form-input"
                    value={examForm.title}
                    onChange={(e) => setExamForm((f) => ({ ...f, title: e.target.value }))}
                    required
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
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
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
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
                      type="number"
                      className="form-input"
                      value={examForm.maximumMarks}
                      onChange={(e) => setExamForm((f) => ({ ...f, maximumMarks: e.target.value }))}
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
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add / Edit Question Modal */}
      {showQuestionModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowQuestionModal(false)}>
          <div className="modal" style={{ maxWidth: 640 }}>
            <div className="modal__header">
              <div className="modal__title">
                {editingQuestionId ? `Edit Question ${questionForm.questionNumber}` : 'Add Question & Scoring Rubric'}
              </div>
              <button className="modal__close" onClick={() => setShowQuestionModal(false)}>✕</button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setQuestionError('');
                const maxMarks = parseInt(questionForm.maximumMarks, 10) || 10;
                saveQuestionMutation.mutate({
                  questionNumber: parseInt(questionForm.questionNumber, 10) || 1,
                  text: questionForm.text,
                  maximumMarks: maxMarks,
                  rubricCriteria: questionForm.criteriaList.map((c) => ({
                    criterion: c.criterion,
                    marks: parseInt(c.marks, 10) || 1,
                  })),
                });
              }}
            >
              <div className="modal__body">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
                  <div className="form-field">
                    <label className="form-label">Question Number <span className="required">*</span></label>
                    <input
                      type="number"
                      min="1"
                      className="form-input"
                      value={questionForm.questionNumber}
                      onChange={(e) => setQuestionForm((f) => ({ ...f, questionNumber: e.target.value }))}
                      required
                    />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Maximum Marks <span className="required">*</span></label>
                    <input
                      type="number"
                      min="1"
                      className="form-input"
                      value={questionForm.maximumMarks}
                      onChange={(e) => setQuestionForm((f) => ({ ...f, maximumMarks: e.target.value }))}
                      required
                    />
                  </div>
                </div>

                <div className="form-field" style={{ marginBottom: 'var(--space-4)' }}>
                  <label className="form-label">Question Text / Prompt <span className="required">*</span></label>
                  <textarea
                    className="form-input"
                    rows={3}
                    placeholder="Enter full question text or problem statement…"
                    value={questionForm.text}
                    onChange={(e) => setQuestionForm((f) => ({ ...f, text: e.target.value }))}
                    required
                  />
                </div>

                {/* Rubric Criteria Items */}
                <div className="label-caps" style={{ marginBottom: 'var(--space-2)' }}>Scoring Criteria Breakdown</div>
                {questionForm.criteriaList.map((crit, idx) => (
                  <div key={idx} style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-2)', alignItems: 'center' }}>
                    <input
                      className="form-input"
                      placeholder="e.g. Core definition, formula application, accuracy"
                      value={crit.criterion}
                      onChange={(e) => {
                        const val = e.target.value;
                        setQuestionForm((f) => {
                          const copy = [...f.criteriaList];
                          copy[idx].criterion = val;
                          return { ...f, criteriaList: copy };
                        });
                      }}
                      style={{ flex: 3 }}
                      required
                    />
                    <input
                      type="number"
                      min="1"
                      className="form-input"
                      placeholder="Marks"
                      value={crit.marks}
                      onChange={(e) => {
                        const val = e.target.value;
                        setQuestionForm((f) => {
                          const copy = [...f.criteriaList];
                          copy[idx].marks = val;
                          return { ...f, criteriaList: copy };
                        });
                      }}
                      style={{ width: 80 }}
                      required
                    />
                    {questionForm.criteriaList.length > 1 && (
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() =>
                          setQuestionForm((f) => ({
                            ...f,
                            criteriaList: f.criteriaList.filter((_, i) => i !== idx),
                          }))
                        }
                      >
                        ✕
                      </button>
                    )}
                  </div>
                ))}

                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  style={{ marginTop: 4 }}
                  onClick={() =>
                    setQuestionForm((f) => ({
                      ...f,
                      criteriaList: [...f.criteriaList, { criterion: '', marks: '2' }],
                    }))
                  }
                >
                  + Add Criterion Line
                </button>

                {questionError && (
                  <div className="attention-item attention-item--critical" style={{ marginTop: 'var(--space-3)' }}>
                    <div className="attention-item__icon">⚠</div>
                    <div className="attention-item__content">
                      <div className="attention-item__desc">{questionError}</div>
                    </div>
                  </div>
                )}
              </div>

              <div className="modal__footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowQuestionModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={saveQuestionMutation.isPending}>
                  {saveQuestionMutation.isPending ? 'Saving Rubric…' : 'Save Question & Rubric'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
