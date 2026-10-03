import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Evaluation, Exam, Question, QuestionMarkItem, QuestionMarkStatus } from '@evalnexa/types';

interface WorkspaceData {
  answerBook: AnswerBook;
  evaluation: Evaluation | null;
}

export function EvaluationWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [activeQIndex, setActiveQIndex] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [zoomScale, setZoomScale] = useState(100);
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // Per-question marking state
  const [currentMarkInput, setCurrentMarkInput] = useState('');
  const [currentCommentInput, setCurrentCommentInput] = useState('');
  const [evaluationRemarks, setEvaluationRemarks] = useState('');
  const [marksState, setMarksState] = useState<QuestionMarkItem[]>([]);

  const { data, isLoading, isError } = useQuery<WorkspaceData>({
    queryKey: ['paper', id],
    queryFn: async () => {
      const { data } = await apiClient.get(`/answer-books/${id}`);
      return data.data;
    },
  });

  const answerBook = data?.answerBook;
  const evaluation = data?.evaluation;
  const exam = answerBook && typeof answerBook.examId === 'object' ? (answerBook.examId as unknown as Exam) : null;
  const examId = exam?._id || (typeof answerBook?.examId === 'string' ? answerBook.examId : '');

  // Fetch questions for this exam
  const { data: questions = [] } = useQuery<Question[]>({
    queryKey: ['exam-questions', examId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/exams/${examId}/questions`);
      return data.data;
    },
    enabled: Boolean(examId),
  });

  // Construct active question list (fall back to totalQuestions if questions haven't been seeded)
  const totalQuestionsCount = Math.max(questions.length, exam?.totalQuestions || 1);
  const activeQuestions: Question[] = questions.length > 0
    ? questions
    : Array.from({ length: totalQuestionsCount }, (_, i) => ({
        _id: `q-${i + 1}`,
        examId: examId,
        questionNumber: i + 1,
        text: `Question ${i + 1} Problem Statement`,
        maximumMarks: exam?.maximumMarks ? Math.round((exam.maximumMarks / totalQuestionsCount) * 10) / 10 : 10,
        rubric: [{ criterion: 'Accuracy & methodology', marks: exam?.maximumMarks ? Math.round(exam.maximumMarks / totalQuestionsCount) : 10 }],
        createdAt: '',
        updatedAt: '',
      }));

  // Synchronize initial marks state from backend evaluation
  useEffect(() => {
    if (evaluation) {
      if (evaluation.remarks) setEvaluationRemarks(evaluation.remarks);
      if (evaluation.questionMarks && evaluation.questionMarks.length > 0) {
        setMarksState(evaluation.questionMarks);
      } else {
        // Initialize default empty state for each question
        const init = activeQuestions.map((q) => ({
          questionNumber: q.questionNumber,
          marks: 0,
          status: 'NOT_STARTED' as QuestionMarkStatus,
          comment: '',
        }));
        setMarksState(init);
      }
    } else {
      const init = activeQuestions.map((q) => ({
        questionNumber: q.questionNumber,
        marks: 0,
        status: 'NOT_STARTED' as QuestionMarkStatus,
        comment: '',
      }));
      setMarksState(init);
    }
  }, [evaluation, activeQuestions.length]);

  const activeQuestion = activeQuestions[activeQIndex] || activeQuestions[0];
  const activeMarkItem = marksState.find((m) => m.questionNumber === activeQuestion?.questionNumber) || {
    questionNumber: activeQuestion?.questionNumber || 1,
    marks: 0,
    status: 'NOT_STARTED' as QuestionMarkStatus,
    comment: '',
  };

  // Sync inputs with active question
  useEffect(() => {
    if (activeMarkItem.status === 'NOT_STARTED') {
      setCurrentMarkInput('');
    } else {
      setCurrentMarkInput(String(activeMarkItem.marks));
    }
    setCurrentCommentInput(activeMarkItem.comment || '');
  }, [activeQIndex, activeMarkItem.status, activeMarkItem.marks, activeMarkItem.comment]);

  const startMutation = useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post(`/evaluations/${id}/start`);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper', id] });
      queryClient.invalidateQueries({ queryKey: ['my-papers'] });
    },
  });

  const saveMarkMutation = useMutation({
    mutationFn: async (updatedList: QuestionMarkItem[]) => {
      if (!evaluation) return;
      const total = updatedList.reduce((acc, q) => acc + (q.marks || 0), 0);
      await apiClient.patch(`/evaluations/${evaluation._id}`, {
        totalMarks: total,
        questionMarks: updatedList,
        remarks: evaluationRemarks,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper', id] });
    },
  });

  const submitMutation = useMutation({
    mutationFn: async () => {
      if (!evaluation) throw new Error('No evaluation in progress');

      // Deterministic validation: Every question must be marked or not attempted
      const unattemptedQuestions = activeQuestions.filter((q) => {
        const item = marksState.find((m) => m.questionNumber === q.questionNumber);
        return !item || item.status === 'NOT_STARTED';
      });

      if (unattemptedQuestions.length > 0) {
        throw new Error(
          `Cannot submit: Question(s) ${unattemptedQuestions.map((q) => `Q${q.questionNumber}`).join(', ')} have not been evaluated. Mark all questions or flag them as Not Attempted.`
        );
      }

      const total = marksState.reduce((acc, q) => acc + (q.marks || 0), 0);
      if (exam && total > exam.maximumMarks) {
        throw new Error(`Total marks (${total}) cannot exceed examination maximum (${exam.maximumMarks}).`);
      }

      await apiClient.post(`/evaluations/${evaluation._id}/submit`, {
        totalMarks: total,
        questionMarks: marksState,
        remarks: evaluationRemarks,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper', id] });
      queryClient.invalidateQueries({ queryKey: ['my-papers'] });
      setShowSubmitModal(false);
      navigate('/papers');
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || (err as Error).message || 'Submission failed';
      setSubmitError(msg);
    },
  });

  const handleSaveQuestionMark = (status: QuestionMarkStatus = 'MARKED') => {
    const numericMarks = status === 'NOT_ATTEMPTED' ? 0 : parseFloat(currentMarkInput) || 0;

    if (numericMarks < 0) {
      alert('Marks cannot be negative.');
      return;
    }
    if (activeQuestion && numericMarks > activeQuestion.maximumMarks) {
      alert(`Marks cannot exceed question maximum (${activeQuestion.maximumMarks}).`);
      return;
    }

    const updatedItem: QuestionMarkItem = {
      questionNumber: activeQuestion.questionNumber,
      marks: numericMarks,
      status,
      comment: currentCommentInput,
    };

    const updatedList = marksState.map((m) =>
      m.questionNumber === activeQuestion.questionNumber ? updatedItem : m
    );

    // If item was not in list, add it
    if (!marksState.some((m) => m.questionNumber === activeQuestion.questionNumber)) {
      updatedList.push(updatedItem);
    }

    setMarksState(updatedList);
    saveMarkMutation.mutate(updatedList);
  };

  const handleNextQuestion = () => {
    if (activeQIndex < activeQuestions.length - 1) {
      setActiveQIndex(activeQIndex + 1);
    }
  };

  if (isLoading) {
    return <div className="state-container"><div className="spinner" /></div>;
  }

  if (isError || !data || !answerBook) {
    return (
      <div className="state-container">
        <div className="state-title">Answer Book Not Found</div>
        <Link to="/papers" className="btn btn-secondary state-action">← Return to Papers</Link>
      </div>
    );
  }

  const isInProgress = answerBook.status === 'IN_PROGRESS';
  const isSubmitted = ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'FINALIZED'].includes(answerBook.status);
  const canStart = ['ASSIGNED', 'RETURNED'].includes(answerBook.status);

  // Derived progress stats
  const markedCount = marksState.filter((m) => m.status === 'MARKED').length;
  const notAttemptedCount = marksState.filter((m) => m.status === 'NOT_ATTEMPTED').length;
  const flaggedCount = marksState.filter((m) => m.status === 'FLAGGED').length;
  const totalCalculatedMarks = marksState.reduce((acc, q) => acc + (q.marks || 0), 0);
  const allQuestionsAccounted = activeQuestions.every((q) => {
    const item = marksState.find((m) => m.questionNumber === q.questionNumber);
    return item && (item.status === 'MARKED' || item.status === 'NOT_ATTEMPTED');
  });

  return (
    <div style={{ margin: '-40px', display: 'grid', gridTemplateColumns: '220px 1fr 320px', height: 'calc(100vh - 52px)', background: 'var(--parchment-bg)' }}>
      {/* ============================================================ */}
      {/* LEFT COLUMN: Question & Script Navigation */}
      {/* ============================================================ */}
      <div className="eval-sidebar" style={{ borderRight: '1px solid var(--parchment-border)', overflowY: 'auto', background: 'rgba(255,255,255,0.4)', padding: 'var(--space-4)' }}>
        <div style={{ marginBottom: 'var(--space-4)', paddingBottom: 'var(--space-3)', borderBottom: '1px solid var(--parchment-border)' }}>
          <div className="label-caps" style={{ color: 'var(--parchment-gold)', marginBottom: 2 }}>SCRIPT DOCKET</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700, color: 'var(--parchment-navy)' }}>
            {answerBook.answerBookCode}
          </div>
          <div className="label-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>
            Roll: {answerBook.studentCode} · {answerBook.pageCount} Pages
          </div>
        </div>

        {/* Examination metadata */}
        <div style={{ marginBottom: 'var(--space-4)', paddingBottom: 'var(--space-3)', borderBottom: '1px dashed var(--parchment-border)' }}>
          <div className="label-caps" style={{ fontSize: 9 }}>Examination</div>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 13, fontWeight: 600 }}>{exam?.subjectCode}</div>
          <div className="label-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>
            Max {exam?.maximumMarks || '—'} Marks · {activeQuestions.length} Questions
          </div>
        </div>

        {/* Question List */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span className="label-caps">Questions</span>
            <span className="label-mono" style={{ fontSize: 10 }}>
              {markedCount + notAttemptedCount} / {activeQuestions.length}
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {activeQuestions.map((q, idx) => {
              const item = marksState.find((m) => m.questionNumber === q.questionNumber);
              const qStatus = item?.status || 'NOT_STARTED';
              const isSelected = activeQIndex === idx;

              return (
                <div
                  key={q._id}
                  onClick={() => setActiveQIndex(idx)}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 10px',
                    borderRadius: 'var(--radius-sm)',
                    border: isSelected ? '1px solid var(--parchment-navy)' : '1px solid var(--parchment-border)',
                    background: isSelected ? 'rgba(14, 26, 43, 0.08)' : 'rgba(255, 255, 255, 0.5)',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 12 }}>
                      Q{q.questionNumber}
                    </span>
                    <span className="label-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                      /{q.maximumMarks}m
                    </span>
                  </div>

                  <span
                    className="label-mono"
                    style={{
                      fontSize: 9,
                      padding: '2px 5px',
                      borderRadius: 2,
                      fontWeight: 600,
                      background:
                        qStatus === 'MARKED'
                          ? 'var(--status-approved-bg)'
                          : qStatus === 'FLAGGED'
                          ? 'var(--status-review-bg)'
                          : qStatus === 'NOT_ATTEMPTED'
                          ? 'rgba(0,0,0,0.06)'
                          : 'var(--parchment-border)',
                      color:
                        qStatus === 'MARKED'
                          ? 'var(--status-approved-text)'
                          : qStatus === 'FLAGGED'
                          ? 'var(--status-review-text)'
                          : qStatus === 'NOT_ATTEMPTED'
                          ? 'var(--text-muted)'
                          : 'var(--text-faint)',
                    }}
                  >
                    {qStatus === 'MARKED'
                      ? `${item?.marks} pts`
                      : qStatus === 'NOT_ATTEMPTED'
                      ? 'N/A'
                      : qStatus === 'FLAGGED'
                      ? 'FLAG'
                      : 'PENDING'}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        <div style={{ marginTop: 'var(--space-6)', borderTop: '1px solid var(--parchment-border)', paddingTop: 'var(--space-3)' }}>
          <Link to="/papers" className="btn btn-ghost btn-sm" style={{ width: '100%', justifyContent: 'center' }}>
            ← Back to My Scripts
          </Link>
        </div>
      </div>

      {/* ============================================================ */}
      {/* CENTER: Digital Answer Script Viewer */}
      {/* ============================================================ */}
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
        {/* Viewer Toolbar */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '10px 16px',
            borderBottom: '1px solid var(--parchment-border)',
            background: 'rgba(255, 255, 255, 0.7)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <span className="label-caps" style={{ color: 'var(--parchment-gold)' }}>DIGITAL SCRIPT VIEWER</span>
            <span className="label-mono" style={{ fontSize: 11 }}>
              Page {currentPage} of {answerBook.pageCount || 1}
            </span>
          </div>

          {/* Navigation & Zoom controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <button
              className="btn btn-ghost btn-sm"
              disabled={currentPage <= 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            >
              ← Prev Page
            </button>
            <button
              className="btn btn-ghost btn-sm"
              disabled={currentPage >= (answerBook.pageCount || 1)}
              onClick={() => setCurrentPage((p) => Math.min(answerBook.pageCount || 1, p + 1))}
            >
              Next Page →
            </button>
            <span style={{ height: 16, width: 1, background: 'var(--parchment-border)', margin: '0 4px' }} />
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setZoomScale((z) => Math.max(50, z - 15))}
            >
              Zoom -
            </button>
            <span className="label-mono" style={{ fontSize: 11, minWidth: 40, textAlign: 'center' }}>
              {zoomScale}%
            </span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setZoomScale((z) => Math.min(200, z + 15))}
            >
              Zoom +
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setZoomScale(100)}
            >
              Fit Width
            </button>
          </div>
        </div>

        {/* Script Display Frame */}
        <div
          style={{
            flex: 1,
            overflow: 'auto',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            padding: 'var(--space-6)',
            background: 'radial-gradient(circle, rgba(14,26,43,0.03) 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }}
        >
          {answerBook.pdfUrl ? (
            <div style={{ width: `${zoomScale}%`, height: '100%', maxWidth: '1000px' }}>
              <iframe
                src={answerBook.pdfUrl}
                title="Answer Script PDF"
                style={{ width: '100%', height: '100%', border: '1px solid var(--parchment-border)', borderRadius: 'var(--radius-sm)' }}
              />
            </div>
          ) : (
            <div
              style={{
                width: `${Math.min(100, zoomScale)}%`,
                maxWidth: '680px',
                aspectRatio: '1 / 1.35',
                background: '#FFFFFF',
                boxShadow: '0 4px 20px rgba(0,0,0,0.06)',
                border: '1px solid var(--parchment-border)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                alignItems: 'center',
                padding: 'var(--space-8)',
                textAlign: 'center',
                position: 'relative',
              }}
            >
              {/* Archival folio frame border */}
              <div
                style={{
                  position: 'absolute',
                  inset: 12,
                  border: '1px solid rgba(14,26,43,0.12)',
                  pointerEvents: 'none',
                }}
              />

              <div style={{ fontSize: 36, marginBottom: 12 }}>📜</div>
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 20, fontWeight: 700, color: 'var(--parchment-navy)', marginBottom: 6 }}>
                Digital Answer Script
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>
                Waiting for script imaging pipeline
              </div>
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 13, color: 'var(--text-muted)', maxWidth: '400px', lineHeight: 1.6 }}>
                When actual page images are connected, this exact viewport displays the scanned student response pages for page-by-page marking and annotation.
              </div>

              <div style={{ marginTop: 'var(--space-6)', display: 'flex', gap: 'var(--space-2)' }}>
                <span className="label-mono" style={{ fontSize: 10, padding: '3px 8px', background: 'rgba(14,26,43,0.04)', borderRadius: 2 }}>
                  Script: {answerBook.answerBookCode}
                </span>
                <span className="label-mono" style={{ fontSize: 10, padding: '3px 8px', background: 'rgba(14,26,43,0.04)', borderRadius: 2 }}>
                  Page {currentPage} / {answerBook.pageCount}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ============================================================ */}
      {/* RIGHT COLUMN: Evaluation Docket */}
      {/* ============================================================ */}
      <div
        className="eval-docket"
        style={{
          borderLeft: '1px solid var(--parchment-border)',
          overflowY: 'auto',
          background: 'rgba(255, 255, 255, 0.4)',
          padding: 'var(--space-4)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
        }}
      >
        <div>
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-3)' }}>
            <div>
              <div className="label-caps" style={{ color: 'var(--parchment-gold)' }}>EVALUATION DOCKET</div>
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 16, fontWeight: 700 }}>
                Question {activeQuestion?.questionNumber} of {activeQuestions.length}
              </div>
            </div>
            <span
              className="label-mono"
              style={{
                fontSize: 10,
                padding: '2px 6px',
                borderRadius: 2,
                background: 'var(--parchment-border)',
                fontWeight: 600,
              }}
            >
              MAX {activeQuestion?.maximumMarks} MARKS
            </span>
          </div>

          {canStart && (
            <div style={{ marginBottom: 'var(--space-4)' }}>
              <button
                className="btn btn-primary"
                style={{ width: '100%', justifyContent: 'center' }}
                disabled={startMutation.isPending}
                onClick={() => startMutation.mutate()}
              >
                {startMutation.isPending ? 'Starting Docket…' : '▶ Begin Evaluation'}
              </button>
            </div>
          )}

          {/* Question Text & Rubrics */}
          <div
            style={{
              padding: 'var(--space-3)',
              background: 'rgba(255,255,255,0.7)',
              border: '1px solid var(--parchment-border)',
              borderRadius: 'var(--radius-sm)',
              marginBottom: 'var(--space-4)',
            }}
          >
            <div className="label-caps" style={{ fontSize: 9, marginBottom: 4 }}>Question Statement</div>
            <div style={{ fontFamily: 'var(--font-serif)', fontSize: 13, marginBottom: 8, lineHeight: 1.5 }}>
              {activeQuestion?.text}
            </div>

            {activeQuestion?.rubric && activeQuestion.rubric.length > 0 && (
              <div style={{ borderTop: '1px dashed var(--parchment-border)', paddingTop: 6 }}>
                <div className="label-caps" style={{ fontSize: 8.5, marginBottom: 4 }}>Rubric Criteria</div>
                {activeQuestion.rubric.map((r, rIdx) => (
                  <div key={rIdx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                    <span>• {r.criterion}</span>
                    <span style={{ fontWeight: 600 }}>{r.marks}m</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Controls: Marks Input & Comments */}
          {(isInProgress || isSubmitted) && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
              <div>
                <label className="form-label" style={{ fontSize: 11 }}>
                  Marks Awarded (Max: {activeQuestion?.maximumMarks})
                </label>
                <input
                  className="form-input"
                  type="number"
                  step="0.5"
                  min={0}
                  max={activeQuestion?.maximumMarks}
                  placeholder={`0 - ${activeQuestion?.maximumMarks}`}
                  disabled={isSubmitted}
                  value={currentMarkInput}
                  onChange={(e) => setCurrentMarkInput(e.target.value)}
                  style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700 }}
                />
              </div>

              <div>
                <label className="form-label" style={{ fontSize: 11 }}>Examiner Comment / Justification</label>
                <textarea
                  className="form-input"
                  rows={2}
                  disabled={isSubmitted}
                  placeholder="Notes on step correctness or missing work..."
                  value={currentCommentInput}
                  onChange={(e) => setCurrentCommentInput(e.target.value)}
                  style={{ fontSize: 12 }}
                />
              </div>

              {isInProgress && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)' }}>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => handleSaveQuestionMark('MARKED')}
                      disabled={saveMarkMutation.isPending || !currentMarkInput}
                    >
                      ✓ Save Mark
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => handleSaveQuestionMark('NOT_ATTEMPTED')}
                    >
                      Not Attempted
                    </button>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)' }}>
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ border: '1px solid var(--parchment-border)' }}
                      onClick={() => handleSaveQuestionMark('FLAGGED')}
                    >
                      Flag for Review
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ border: '1px solid var(--parchment-border)' }}
                      onClick={handleNextQuestion}
                      disabled={activeQIndex >= activeQuestions.length - 1}
                    >
                      Next Q →
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* AI COPILOT FUTURE SLOT (Strictly matching prompt) */}
          <div
            style={{
              padding: 'var(--space-3)',
              border: '1px dashed var(--parchment-border)',
              background: 'rgba(14,26,43,0.02)',
              borderRadius: 'var(--radius-sm)',
              marginBottom: 'var(--space-4)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span className="label-caps" style={{ color: 'var(--parchment-gold)', letterSpacing: '0.12em' }}>
                EVALNEXA COPILOT
              </span>
              <span className="label-mono" style={{ fontSize: 9, color: 'var(--text-muted)' }}>
                INTEGRATION SLOT
              </span>
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
              AI assistance not yet available.
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, color: 'var(--text-faint)', marginTop: 4, lineHeight: 1.4 }}>
              Later slot: Suggested Range · Confidence · Rubric Evidence · Missing Concepts · Explanations
            </div>
          </div>
        </div>

        {/* BOTTOM: Submission Roster & Summary */}
        <div style={{ borderTop: '1px solid var(--parchment-border)', paddingTop: 'var(--space-3)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
            <span className="label-caps">Total Computed Marks</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 700, color: 'var(--parchment-navy)' }}>
              {totalCalculatedMarks}
              {exam && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}> / {exam.maximumMarks}</span>}
            </span>
          </div>

          {isInProgress && (
            <button
              className="btn btn-primary"
              style={{ width: '100%', justifyContent: 'center' }}
              onClick={() => {
                setSubmitError('');
                setShowSubmitModal(true);
              }}
            >
              Submit Evaluation →
            </button>
          )}

          {isSubmitted && (
            <div
              style={{
                textAlign: 'center',
                padding: '8px',
                background: 'var(--status-approved-bg)',
                color: 'var(--status-approved-text)',
                borderRadius: 'var(--radius-sm)',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: 600,
              }}
            >
              ✓ Evaluation Submitted to Moderation
            </div>
          )}
        </div>
      </div>

      {/* ============================================================ */}
      {/* SUBMISSION REVIEW SUMMARY MODAL */}
      {/* ============================================================ */}
      {showSubmitModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowSubmitModal(false)}>
          <div className="modal">
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow">Marking Verification</div>
                <div className="modal__title">Review Summary Before Submission</div>
              </div>
              <button className="modal__close" onClick={() => setShowSubmitModal(false)}>✕</button>
            </div>
            <div className="modal__body">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dotted var(--parchment-border)', paddingBottom: 4 }}>
                  <span className="label-caps">Questions Marked</span>
                  <span className="label-mono" style={{ fontWeight: 600 }}>{markedCount}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dotted var(--parchment-border)', paddingBottom: 4 }}>
                  <span className="label-caps">Questions Not Attempted</span>
                  <span className="label-mono" style={{ fontWeight: 600 }}>{notAttemptedCount}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dotted var(--parchment-border)', paddingBottom: 4 }}>
                  <span className="label-caps">Flags Recorded</span>
                  <span className="label-mono" style={{ fontWeight: 600, color: flaggedCount > 0 ? 'var(--status-review-text)' : 'inherit' }}>
                    {flaggedCount}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--parchment-border)', paddingBottom: 4 }}>
                  <span className="label-caps" style={{ fontWeight: 700 }}>Total Final Marks</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--parchment-navy)' }}>
                    {totalCalculatedMarks} {exam && `/ ${exam.maximumMarks}`}
                  </span>
                </div>
              </div>

              {!allQuestionsAccounted && (
                <div
                  style={{
                    padding: 'var(--space-3)',
                    background: 'var(--status-returned-bg)',
                    color: 'var(--status-returned-text)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: 12,
                    marginBottom: 'var(--space-3)',
                  }}
                >
                  ⚠ Mandatory Evaluation Check: Every question must have an explicit status (Marked or Not Attempted). Submission is blocked until all questions are completed.
                </div>
              )}

              {submitError && (
                <div
                  style={{
                    padding: 'var(--space-3)',
                    background: 'var(--status-returned-bg)',
                    color: 'var(--status-returned-text)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: 12,
                  }}
                >
                  ⚠ {submitError}
                </div>
              )}
            </div>
            <div className="modal__footer">
              <button className="btn btn-secondary" onClick={() => setShowSubmitModal(false)}>
                Back to Marking
              </button>
              <button
                className="btn btn-primary"
                disabled={!allQuestionsAccounted || submitMutation.isPending}
                onClick={() => submitMutation.mutate()}
              >
                {submitMutation.isPending ? 'Transmitting…' : 'Confirm & Submit to Moderation'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
