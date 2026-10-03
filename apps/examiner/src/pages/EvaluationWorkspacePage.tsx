import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Evaluation, Exam, Question, QuestionMarkItem, QuestionMarkStatus } from '@evalnexa/types';
import { getSocket } from '../lib/socket';

interface WorkspaceData {
  answerBook: AnswerBook;
  evaluation: Evaluation | null;
}

export function EvaluationWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Navigation & Zoom State
  const [activeQIndex, setActiveQIndex] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [zoomScale, setZoomScale] = useState(100);
  const [viewMode, setViewMode] = useState<'SCRIPT_ONLY' | 'SPLIT' | 'TEXT_ONLY'>('SCRIPT_ONLY');
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [saveStatus, setSaveStatus] = useState<'IDLE' | 'SAVING' | 'SAVED' | 'ERROR'>('IDLE');

  // Active question inputs
  const [currentMarkInput, setCurrentMarkInput] = useState('');
  const [currentCommentInput, setCurrentCommentInput] = useState('');
  const [evaluationRemarks, setEvaluationRemarks] = useState('');
  const [marksState, setMarksState] = useState<QuestionMarkItem[]>([]);

  // Real-time synchronization
  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;

    const handleUpdate = () => {
      queryClient.invalidateQueries({ queryKey: ['paper', id] });
      queryClient.invalidateQueries({ queryKey: ['my-papers'] });
    };

    socket.on('answerbook.status.changed', handleUpdate);
    socket.on('moderation.returned', handleUpdate);
    socket.on('moderation.approved', handleUpdate);

    return () => {
      socket.off('answerbook.status.changed', handleUpdate);
      socket.off('moderation.returned', handleUpdate);
      socket.off('moderation.approved', handleUpdate);
    };
  }, [id, queryClient]);

  // Load AnswerBook & Evaluation
  const { data, isLoading, isError, refetch } = useQuery<WorkspaceData>({
    queryKey: ['paper', id],
    queryFn: async () => {
      const res = await apiClient.get(`/answer-books/${id}`);
      return res.data.data;
    },
    enabled: Boolean(id),
  });

  const answerBook = data?.answerBook;
  const evaluation = data?.evaluation;
  const exam = answerBook && typeof answerBook.examId === 'object' ? (answerBook.examId as unknown as Exam) : null;
  const examId = exam?._id || (typeof answerBook?.examId === 'string' ? answerBook.examId : '');

  // Load Exam Questions
  const { data: questions = [] } = useQuery<Question[]>({
    queryKey: ['exam-questions', examId],
    queryFn: async () => {
      const res = await apiClient.get(`/exams/${examId}/questions`);
      return res.data.data;
    },
    enabled: Boolean(examId),
  });

  // Canonical question list
  const totalQuestionsCount = Math.max(questions.length, exam?.totalQuestions || 1);
  const activeQuestions: Question[] = useMemo(() => {
    if (questions.length > 0) return questions;
    return Array.from({ length: totalQuestionsCount }, (_, i) => ({
      _id: `q-${i + 1}`,
      examId: examId,
      questionNumber: i + 1,
      text: `Question ${i + 1} Examination Statement`,
      maximumMarks: exam?.maximumMarks ? Math.round((exam.maximumMarks / totalQuestionsCount) * 10) / 10 : 10,
      rubric: [
        { criterion: 'Conceptual understanding & method', marks: exam?.maximumMarks ? Math.round(exam.maximumMarks / totalQuestionsCount * 0.6) : 6 },
        { criterion: 'Execution & correctness', marks: exam?.maximumMarks ? Math.round(exam.maximumMarks / totalQuestionsCount * 0.4) : 4 },
      ],
      createdAt: '',
      updatedAt: '',
    }));
  }, [questions, totalQuestionsCount, examId, exam?.maximumMarks]);

  // Synchronize initial marks state from backend
  useEffect(() => {
    if (evaluation) {
      if (evaluation.remarks) setEvaluationRemarks(evaluation.remarks);
      if (evaluation.questionMarks && evaluation.questionMarks.length > 0) {
        setMarksState(evaluation.questionMarks);
      } else {
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
  }, [evaluation, activeQuestions]);

  const activeQuestion = activeQuestions[activeQIndex] || activeQuestions[0];
  const activeMarkItem = marksState.find((m) => m.questionNumber === activeQuestion?.questionNumber) || {
    questionNumber: activeQuestion?.questionNumber || 1,
    marks: 0,
    status: 'NOT_STARTED' as QuestionMarkStatus,
    comment: '',
  };

  // Sync inputs with active question selection
  useEffect(() => {
    if (activeMarkItem.status === 'NOT_STARTED') {
      setCurrentMarkInput('');
    } else {
      setCurrentMarkInput(String(activeMarkItem.marks));
    }
    setCurrentCommentInput(activeMarkItem.comment || '');
  }, [activeQIndex, activeMarkItem.status, activeMarkItem.marks, activeMarkItem.comment]);

  // Mutation: Begin evaluation session
  const startMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post(`/evaluations/${id}/start`);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper', id] });
      queryClient.invalidateQueries({ queryKey: ['my-papers'] });
    },
  });

  // Mutation: Save marks to backend
  const saveMarkMutation = useMutation({
    mutationFn: async (updatedList: QuestionMarkItem[]) => {
      if (!evaluation) return;
      setSaveStatus('SAVING');
      const total = updatedList
        .filter((q) => q.status === 'MARKED' || q.status === 'FLAGGED')
        .reduce((sum, q) => sum + (Number(q.marks) || 0), 0);

      await apiClient.patch(`/evaluations/${evaluation._id}`, {
        totalMarks: total,
        questionMarks: updatedList,
        remarks: evaluationRemarks,
      });
    },
    onSuccess: () => {
      setSaveStatus('SAVED');
      queryClient.invalidateQueries({ queryKey: ['paper', id] });
      setTimeout(() => setSaveStatus('IDLE'), 2500);
    },
    onError: () => {
      setSaveStatus('ERROR');
    },
  });

  // Mutation: Final submission
  const submitMutation = useMutation({
    mutationFn: async () => {
      if (!evaluation) throw new Error('No evaluation in progress');

      // Deterministic validation: Check all questions
      const unchecked = activeQuestions.filter((q) => {
        const item = marksState.find((m) => m.questionNumber === q.questionNumber);
        return !item || item.status === 'NOT_STARTED';
      });

      if (unchecked.length > 0) {
        throw new Error(
          `Cannot submit: Question ${unchecked.map((q) => `Q${q.questionNumber}`).join(', ')} has not been evaluated.`
        );
      }

      const total = marksState
        .filter((q) => q.status === 'MARKED' || q.status === 'FLAGGED')
        .reduce((sum, q) => sum + (Number(q.marks) || 0), 0);

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
    onError: (err: any) => {
      const msg = err.response?.data?.message || err.message || 'Submission failed';
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

  // Fetch page media from backend
  const { data: pagesList = [] } = useQuery<{ pageNumber: number; quality?: any; ocr?: any }[]>({
    queryKey: ['paper-pages-list', id],
    queryFn: async () => {
      try {
        const res = await apiClient.get(`/answer-books/${id}/pages`);
        return res.data.data.pages || [];
      } catch {
        return [];
      }
    },
    enabled: Boolean(id),
  });

  const totalPagesCount = Math.max(pagesList.length, answerBook?.pageCount || 1);

  const { data: pageMedia, isLoading: isPageMediaLoading, isError: isPageMediaError, refetch: refetchPageMedia } = useQuery<{
    pageNumber: number;
    secureUrl?: string;
    ocr?: { text?: string; confidence?: number | null; language?: string };
    quality?: { status?: string; score?: number | null };
    processingStatus?: string;
    format?: string;
  } | null>({
    queryKey: ['paper-page-media', id, currentPage],
    queryFn: async () => {
      try {
        const res = await apiClient.get(`/answer-books/${id}/pages/${currentPage}`);
        return res.data.data;
      } catch {
        return null;
      }
    },
    enabled: Boolean(id) && currentPage > 0,
  });

  if (isLoading) {
    return (
      <div style={{ padding: '80px 0', textAlign: 'center', fontFamily: 'Cambria', color: 'var(--navy)' }}>
        <div style={{ fontSize: 28, marginBottom: 12 }}>📖</div>
        <div style={{ fontSize: 20, fontWeight: 700 }}>Loading Digital Answer Script Docket…</div>
      </div>
    );
  }

  if (isError || !answerBook) {
    return (
      <div style={{ padding: '80px 0', textAlign: 'center', fontFamily: 'Cambria' }}>
        <div style={{ fontSize: 28, color: 'var(--burgundy)', marginBottom: 12 }}>⚠</div>
        <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--navy)', marginBottom: 8 }}>
          Answer Book Docket Not Found
        </div>
        <p style={{ fontSize: 16, color: 'var(--charcoal)', marginBottom: 20 }}>
          The requested script could not be loaded or is not assigned to your docket.
        </p>
        <Link to="/papers" className="btn btn-secondary" style={{ fontSize: 15, padding: '8px 20px' }}>
          ← Return to My Scripts
        </Link>
      </div>
    );
  }

  const isInProgress = answerBook.status === 'IN_PROGRESS';
  const isSubmitted = ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'FINALIZED'].includes(answerBook.status);
  const isReturned = answerBook.status === 'RETURNED';
  const canStart = ['ASSIGNED', 'RETURNED'].includes(answerBook.status);

  // Computed totals & progress
  const markedCount = marksState.filter((m) => m.status === 'MARKED').length;
  const notAttemptedCount = marksState.filter((m) => m.status === 'NOT_ATTEMPTED').length;
  const flaggedCount = marksState.filter((m) => m.status === 'FLAGGED').length;
  const notStartedQuestions = activeQuestions.filter((q) => {
    const item = marksState.find((m) => m.questionNumber === q.questionNumber);
    return !item || item.status === 'NOT_STARTED';
  });
  const allQuestionsAccounted = notStartedQuestions.length === 0;
  const totalCalculatedMarks = marksState
    .filter((m) => m.status === 'MARKED' || m.status === 'FLAGGED')
    .reduce((sum, q) => sum + (Number(q.marks) || 0), 0);

  return (
    <div style={{ margin: '-32px -48px -40px -48px', height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      {/* Top Header Strip */}
      <div
        style={{
          background: 'var(--parchment-card)',
          borderBottom: '1px solid var(--border)',
          padding: '10px 24px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <Link to="/papers" className="btn btn-secondary" style={{ fontSize: 13, padding: '4px 12px' }}>
            ← All Scripts
          </Link>
          <div style={{ height: 20, width: 1, background: 'var(--border)' }} />
          <div>
            <span style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--gold)', fontWeight: 700, marginRight: 8 }}>
              SCRIPT DOCKET
            </span>
            <strong style={{ fontSize: 18, color: 'var(--navy)' }}>{answerBook.answerBookCode}</strong>
            <span style={{ fontSize: 14, color: 'var(--charcoal)', marginLeft: 8 }}>
              (Roll: {answerBook.studentCode})
            </span>
          </div>
          <div style={{ height: 20, width: 1, background: 'var(--border)' }} />
          <div style={{ fontSize: 14, color: 'var(--charcoal)' }}>
            Exam: <strong>{exam ? exam.title : 'Examination'}</strong> ({exam?.subjectCode})
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {/* Subtle Workflow Tracker */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--gold)', fontWeight: 700 }}>
            <span>ASSIGNED</span>
            <span>→</span>
            <span style={{ color: 'var(--navy)' }}>READ</span>
            <span>→</span>
            <span style={{ color: 'var(--navy)' }}>MARK</span>
            <span>→</span>
            <span>SAVE</span>
            <span>→</span>
            <span>SUBMIT</span>
          </div>

          <span
            style={{
              padding: '4px 12px',
              fontSize: 12,
              fontWeight: 700,
              textTransform: 'uppercase',
              background:
                isSubmitted
                  ? 'rgba(21, 128, 61, 0.1)'
                  : isReturned
                  ? 'rgba(92, 29, 36, 0.1)'
                  : isInProgress
                  ? 'rgba(180, 83, 9, 0.1)'
                  : 'rgba(14, 26, 43, 0.08)',
              color:
                isSubmitted
                  ? '#15803d'
                  : isReturned
                  ? 'var(--burgundy)'
                  : isInProgress
                  ? '#b45309'
                  : 'var(--navy)',
              border: '1px solid var(--border)',
            }}
          >
            {answerBook.status.replace(/_/g, ' ')}
          </span>
        </div>
      </div>

      {/* Return Notice Banner (if returned by moderator) */}
      {isReturned && (
        <div
          style={{
            background: 'rgba(92, 29, 36, 0.1)',
            borderBottom: '1px solid var(--burgundy)',
            padding: '10px 24px',
            color: 'var(--burgundy)',
            fontSize: 15,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexShrink: 0,
          }}
        >
          <div>
            <strong>⚠ RETURNED FOR REVISION:</strong> The moderator returned this evaluation for review. Please inspect rubric adherence, amend question scores as appropriate, and resubmit.
          </div>
          {evaluation?.remarks && (
            <div style={{ fontStyle: 'italic', fontSize: 14 }}>
              Note: "{evaluation.remarks}"
            </div>
          )}
        </div>
      )}

      {/* THREE-COLUMN OSM WORKSPACE */}
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '22% 52% 26%', overflow: 'hidden' }}>
        {/* ============================================================ */}
        {/* LEFT COLUMN: Script & Question Navigation (22%) */}
        {/* ============================================================ */}
        <div
          style={{
            borderRight: '1px solid var(--border)',
            background: 'var(--parchment-card)',
            display: 'flex',
            flexDirection: 'column',
            overflowY: 'auto',
            padding: '16px',
          }}
        >
          {/* Progress Overview Card */}
          <div
            style={{
              padding: '14px',
              background: 'rgba(255,255,255,0.7)',
              border: '1px solid var(--border)',
              marginBottom: 16,
            }}
          >
            <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--gold)', fontWeight: 700 }}>
              EVALUATION PROGRESS
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--navy)', marginTop: 4 }}>
              {markedCount + notAttemptedCount} / {activeQuestions.length}
            </div>
            <div style={{ fontSize: 13, color: 'var(--charcoal)', marginTop: 2 }}>
              {activeQuestions.length - (markedCount + notAttemptedCount)} questions remaining
            </div>
          </div>

          {/* Question List */}
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--gold)', fontWeight: 700, marginBottom: 8 }}>
              QUESTIONS ROSTER
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {activeQuestions.map((q, idx) => {
                const item = marksState.find((m) => m.questionNumber === q.questionNumber);
                const qStatus = item?.status || 'NOT_STARTED';
                const isSelected = activeQIndex === idx;

                return (
                  <div
                    key={q._id || idx}
                    onClick={() => setActiveQIndex(idx)}
                    style={{
                      padding: '10px 14px',
                      background: isSelected ? 'var(--navy)' : '#ffffff',
                      color: isSelected ? '#ffffff' : 'var(--ink)',
                      border: isSelected ? '1px solid var(--navy)' : '1px solid var(--border)',
                      cursor: 'pointer',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 17, fontWeight: 700 }}>
                        Question {q.questionNumber}
                      </div>
                      <div style={{ fontSize: 12, opacity: isSelected ? 0.85 : 0.65 }}>
                        Max: {q.maximumMarks} Marks
                      </div>
                    </div>

                    <div>
                      {qStatus === 'MARKED' ? (
                        <span
                          style={{
                            padding: '3px 8px',
                            fontSize: 12,
                            fontWeight: 700,
                            background: isSelected ? 'rgba(255,255,255,0.2)' : 'rgba(21, 128, 61, 0.12)',
                            color: isSelected ? '#ffffff' : '#15803d',
                            border: '1px solid var(--border)',
                          }}
                        >
                          ✓ {item?.marks}m
                        </span>
                      ) : qStatus === 'NOT_ATTEMPTED' ? (
                        <span
                          style={{
                            padding: '3px 8px',
                            fontSize: 12,
                            fontWeight: 600,
                            background: isSelected ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.06)',
                            color: isSelected ? '#ffffff' : 'var(--charcoal)',
                            border: '1px solid var(--border)',
                          }}
                        >
                          Not Attempted
                        </span>
                      ) : qStatus === 'FLAGGED' ? (
                        <span
                          style={{
                            padding: '3px 8px',
                            fontSize: 12,
                            fontWeight: 700,
                            background: isSelected ? 'rgba(255,255,255,0.2)' : 'rgba(180, 83, 9, 0.12)',
                            color: isSelected ? '#ffffff' : '#b45309',
                            border: '1px solid var(--border)',
                          }}
                        >
                          Flagged
                        </span>
                      ) : (
                        <span
                          style={{
                            padding: '3px 8px',
                            fontSize: 12,
                            fontWeight: 600,
                            background: isSelected ? 'rgba(255,255,255,0.1)' : 'transparent',
                            color: isSelected ? '#ffffff' : 'var(--charcoal)',
                            border: '1px dashed var(--border)',
                          }}
                        >
                          Not Started
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* ============================================================ */}
        {/* CENTER COLUMN: Digital Answer Script Viewer (52%) */}
        {/* ============================================================ */}
        <div style={{ display: 'flex', flexDirection: 'column', background: '#252932', overflow: 'hidden' }}>
          {/* Viewer Toolbar */}
          <div
            style={{
              padding: '10px 16px',
              background: '#1d212a',
              borderBottom: '1px solid rgba(255,255,255,0.1)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              color: '#ffffff',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--gold)', fontWeight: 700 }}>
                DIGITAL SCRIPT
              </span>
              <span style={{ fontSize: 14, color: '#94a3b8' }}>
                Page {currentPage} of {totalPagesCount}
              </span>
            </div>

            {/* View Mode Controls */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button
                onClick={() => setViewMode('SCRIPT_ONLY')}
                style={{
                  fontFamily: 'Cambria',
                  fontSize: 12,
                  padding: '4px 10px',
                  background: viewMode === 'SCRIPT_ONLY' ? 'var(--navy)' : 'rgba(255,255,255,0.08)',
                  color: '#ffffff',
                  border: '1px solid rgba(255,255,255,0.2)',
                  cursor: 'pointer',
                }}
              >
                Script Only
              </button>
              <button
                onClick={() => setViewMode('SPLIT')}
                style={{
                  fontFamily: 'Cambria',
                  fontSize: 12,
                  padding: '4px 10px',
                  background: viewMode === 'SPLIT' ? 'var(--navy)' : 'rgba(255,255,255,0.08)',
                  color: '#ffffff',
                  border: '1px solid rgba(255,255,255,0.2)',
                  cursor: 'pointer',
                }}
              >
                Split View
              </button>
              <button
                onClick={() => setViewMode('TEXT_ONLY')}
                style={{
                  fontFamily: 'Cambria',
                  fontSize: 12,
                  padding: '4px 10px',
                  background: viewMode === 'TEXT_ONLY' ? 'var(--navy)' : 'rgba(255,255,255,0.08)',
                  color: '#ffffff',
                  border: '1px solid rgba(255,255,255,0.2)',
                  cursor: 'pointer',
                }}
              >
                Extracted Text
              </button>
            </div>

            {/* Page Navigation & Zoom */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                style={{
                  fontFamily: 'Cambria',
                  fontSize: 12,
                  padding: '4px 10px',
                  background: 'rgba(255,255,255,0.1)',
                  color: '#ffffff',
                  border: '1px solid rgba(255,255,255,0.2)',
                  cursor: currentPage <= 1 ? 'not-allowed' : 'pointer',
                  opacity: currentPage <= 1 ? 0.4 : 1,
                }}
              >
                ← Prev
              </button>
              <button
                disabled={currentPage >= totalPagesCount}
                onClick={() => setCurrentPage((p) => Math.min(totalPagesCount, p + 1))}
                style={{
                  fontFamily: 'Cambria',
                  fontSize: 12,
                  padding: '4px 10px',
                  background: 'rgba(255,255,255,0.1)',
                  color: '#ffffff',
                  border: '1px solid rgba(255,255,255,0.2)',
                  cursor: currentPage >= totalPagesCount ? 'not-allowed' : 'pointer',
                  opacity: currentPage >= totalPagesCount ? 0.4 : 1,
                }}
              >
                Next →
              </button>
              <div style={{ height: 16, width: 1, background: 'rgba(255,255,255,0.2)', margin: '0 4px' }} />
              <button
                onClick={() => setZoomScale((z) => Math.max(50, z - 15))}
                style={{
                  fontFamily: 'Cambria',
                  fontSize: 12,
                  padding: '4px 8px',
                  background: 'rgba(255,255,255,0.1)',
                  color: '#ffffff',
                  border: '1px solid rgba(255,255,255,0.2)',
                  cursor: 'pointer',
                }}
              >
                -
              </button>
              <span style={{ fontSize: 12, color: '#cbd5e1', minWidth: 36, textAlign: 'center' }}>
                {zoomScale}%
              </span>
              <button
                onClick={() => setZoomScale((z) => Math.min(200, z + 15))}
                style={{
                  fontFamily: 'Cambria',
                  fontSize: 12,
                  padding: '4px 8px',
                  background: 'rgba(255,255,255,0.1)',
                  color: '#ffffff',
                  border: '1px solid rgba(255,255,255,0.2)',
                  cursor: 'pointer',
                }}
              >
                +
              </button>
              <button
                onClick={() => setZoomScale(100)}
                style={{
                  fontFamily: 'Cambria',
                  fontSize: 12,
                  padding: '4px 8px',
                  background: 'rgba(255,255,255,0.1)',
                  color: '#ffffff',
                  border: '1px solid rgba(255,255,255,0.2)',
                  cursor: 'pointer',
                }}
              >
                Fit
              </button>
            </div>
          </div>

          {/* Viewer Canvas */}
          <div
            style={{
              flex: 1,
              overflow: 'auto',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              padding: '24px',
              position: 'relative',
            }}
          >
            {isPageMediaLoading ? (
              <div style={{ margin: 'auto', textAlign: 'center', color: '#cbd5e1', fontSize: 16 }}>
                <div>Loading digitized page {currentPage}…</div>
              </div>
            ) : isPageMediaError ? (
              <div style={{ margin: 'auto', textAlign: 'center', color: '#cbd5e1' }}>
                <div style={{ fontSize: 24, marginBottom: 8 }}>📄</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#ffffff', marginBottom: 4 }}>
                  Digital answer page unavailable.
                </div>
                <button
                  onClick={() => refetchPageMedia()}
                  style={{
                    fontFamily: 'Cambria',
                    fontSize: 14,
                    padding: '6px 16px',
                    background: 'var(--navy)',
                    color: '#ffffff',
                    border: '1px solid rgba(255,255,255,0.2)',
                    marginTop: 12,
                    cursor: 'pointer',
                  }}
                >
                  Retry
                </button>
              </div>
            ) : pageMedia?.secureUrl ? (
              <div
                style={{
                  width: `${zoomScale}%`,
                  maxWidth: zoomScale <= 100 ? 860 : 'none',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 16,
                  margin: '0 auto',
                  transition: 'width 0.15s ease',
                }}
              >
                {/* Main Script or Split View */}
                {viewMode !== 'TEXT_ONLY' && (
                  <div
                    style={{
                      background: '#ffffff',
                      boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
                      border: '1px solid rgba(255,255,255,0.1)',
                      overflow: 'hidden',
                    }}
                  >
                    {pageMedia.format === 'pdf' ? (
                      <iframe
                        src={pageMedia.secureUrl}
                        title={`Script Page ${currentPage}`}
                        style={{ width: '100%', height: '750px', border: 'none' }}
                      />
                    ) : (
                      <img
                        src={pageMedia.secureUrl}
                        alt={`Answer Script Page ${currentPage}`}
                        style={{ width: '100%', height: 'auto', display: 'block' }}
                      />
                    )}
                  </div>
                )}

                {/* Extracted Text Area */}
                {(viewMode === 'SPLIT' || viewMode === 'TEXT_ONLY') && (
                  <div
                    style={{
                      background: '#ffffff',
                      border: '1px solid var(--border)',
                      padding: '20px 24px',
                      boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                      <span style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--gold)', fontWeight: 700 }}>
                        RECOGNIZED ANSWER TEXT
                      </span>
                      {pageMedia.ocr?.confidence != null && (
                        <span style={{ fontSize: 13, color: 'var(--charcoal)' }}>
                          OCR Confidence: <strong>{(pageMedia.ocr.confidence * 100).toFixed(0)}%</strong>
                        </span>
                      )}
                    </div>
                    <div
                      style={{
                        fontSize: 17,
                        lineHeight: 1.6,
                        color: 'var(--ink)',
                        whiteSpace: 'pre-wrap',
                        maxHeight: viewMode === 'SPLIT' ? 240 : 600,
                        overflowY: 'auto',
                        background: 'rgba(0,0,0,0.02)',
                        padding: '16px',
                        border: '1px solid var(--border)',
                      }}
                    >
                      {pageMedia.ocr?.text || 'Text extraction unavailable.'}
                    </div>
                  </div>
                )}
              </div>
            ) : answerBook.pdfUrl ? (
              <div style={{ width: `${zoomScale}%`, height: '100%', maxWidth: 900 }}>
                <iframe
                  src={answerBook.pdfUrl}
                  title="Answer Script PDF"
                  style={{ width: '100%', height: '100%', border: 'none' }}
                />
              </div>
            ) : (
              <div style={{ margin: 'auto', textAlign: 'center', color: '#cbd5e1' }}>
                <div style={{ fontSize: 28, marginBottom: 8 }}>📄</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#ffffff', marginBottom: 4 }}>
                  Digital answer page unavailable.
                </div>
                <p style={{ fontSize: 14, color: '#94a3b8', maxWidth: 360, margin: '0 auto 16px auto', lineHeight: 1.5 }}>
                  No page scan record exists for page {currentPage} of script docket {answerBook.answerBookCode}.
                </p>
                <button
                  onClick={() => refetchPageMedia()}
                  style={{
                    fontFamily: 'Cambria',
                    fontSize: 14,
                    padding: '6px 16px',
                    background: 'var(--navy)',
                    color: '#ffffff',
                    border: '1px solid rgba(255,255,255,0.2)',
                    cursor: 'pointer',
                  }}
                >
                  Retry
                </button>
              </div>
            )}
          </div>
        </div>

        {/* ============================================================ */}
        {/* RIGHT COLUMN: Evaluation Docket (26%) */}
        {/* ============================================================ */}
        <div
          style={{
            borderLeft: '1px solid var(--border)',
            background: 'var(--parchment-card)',
            display: 'flex',
            flexDirection: 'column',
            overflowY: 'auto',
            padding: '20px',
          }}
        >
          {/* Header */}
          <div style={{ borderBottom: '1px solid var(--border)', paddingBottom: 12, marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--gold)', fontWeight: 700 }}>
                EVALUATION DOCKET
              </span>
              <span
                style={{
                  fontSize: 12,
                  padding: '2px 8px',
                  background: 'rgba(14,26,43,0.08)',
                  color: 'var(--navy)',
                  fontWeight: 700,
                  border: '1px solid var(--border)',
                }}
              >
                MAX {activeQuestion?.maximumMarks} MARKS
              </span>
            </div>
            <h3 style={{ fontSize: 24, fontWeight: 700, color: 'var(--navy)', margin: '4px 0 0 0' }}>
              Question {activeQuestion?.questionNumber} of {activeQuestions.length}
            </h3>
          </div>

          {/* Start Evaluation Action if Assigned */}
          {canStart && (
            <div style={{ marginBottom: 16 }}>
              <button
                className="btn btn-primary"
                style={{ width: '100%', fontSize: 16, padding: '10px 16px', justifyContent: 'center' }}
                disabled={startMutation.isPending}
                onClick={() => startMutation.mutate()}
              >
                {startMutation.isPending ? 'Starting Docket…' : '▶ Begin Evaluation'}
              </button>
            </div>
          )}

          {/* Question Text */}
          <div
            style={{
              background: '#ffffff',
              border: '1px solid var(--border)',
              padding: '16px',
              marginBottom: 16,
            }}
          >
            <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--gold)', fontWeight: 700, marginBottom: 6 }}>
              Question Statement
            </div>
            <div style={{ fontSize: 18, color: 'var(--ink)', lineHeight: 1.5 }}>
              {activeQuestion?.text}
            </div>

            {/* Real Rubric */}
            {activeQuestion?.rubric && activeQuestion.rubric.length > 0 && (
              <div style={{ marginTop: 14, paddingTop: 10, borderTop: '1px dashed var(--border)' }}>
                <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--gold)', fontWeight: 700, marginBottom: 6 }}>
                  Marking Rubric
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {activeQuestion.rubric.map((r, rIdx) => (
                    <div key={rIdx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, color: 'var(--charcoal)' }}>
                      <span>• {r.criterion}</span>
                      <strong style={{ color: 'var(--navy)' }}>{r.marks}m</strong>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Marks Input & Comment */}
          {(isInProgress || isSubmitted) && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--gold)', fontWeight: 700, marginBottom: 6 }}>
                  Marks Awarded (0 – {activeQuestion?.maximumMarks})
                </label>
                <input
                  type="number"
                  step="0.5"
                  min={0}
                  max={activeQuestion?.maximumMarks}
                  placeholder={`0 – ${activeQuestion?.maximumMarks}`}
                  disabled={isSubmitted}
                  value={currentMarkInput}
                  onChange={(e) => setCurrentMarkInput(e.target.value)}
                  style={{
                    fontFamily: 'Cambria',
                    fontSize: 24,
                    fontWeight: 700,
                    color: 'var(--navy)',
                    width: '100%',
                    padding: '8px 14px',
                    border: '2px solid var(--border)',
                    background: '#ffffff',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--gold)', fontWeight: 700, marginBottom: 6 }}>
                  Examiner Comment (Optional)
                </label>
                <textarea
                  rows={2}
                  disabled={isSubmitted}
                  placeholder="Record justification notes or methodology remarks..."
                  value={currentCommentInput}
                  onChange={(e) => setCurrentCommentInput(e.target.value)}
                  style={{
                    fontFamily: 'Cambria',
                    fontSize: 15,
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid var(--border)',
                    background: '#ffffff',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              {/* Autosave State Feedback */}
              <div style={{ fontSize: 13, minHeight: 18 }}>
                {saveStatus === 'SAVING' && (
                  <span style={{ color: 'var(--gold)', fontStyle: 'italic' }}>Saving mark to database…</span>
                )}
                {saveStatus === 'SAVED' && (
                  <span style={{ color: '#15803d', fontWeight: 600 }}>✓ Saved just now</span>
                )}
                {saveStatus === 'ERROR' && (
                  <span style={{ color: 'var(--burgundy)', fontWeight: 600 }}>⚠ Save failed — Retry</span>
                )}
              </div>

              {/* Action Buttons */}
              {isInProgress && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <button
                    className="btn btn-primary"
                    style={{ fontSize: 16, padding: '10px 16px', justifyContent: 'center' }}
                    onClick={() => handleSaveQuestionMark('MARKED')}
                    disabled={saveMarkMutation.isPending || currentMarkInput === ''}
                  >
                    SAVE MARK
                  </button>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: 14, padding: '8px 12px', justifyContent: 'center' }}
                      onClick={() => handleSaveQuestionMark('NOT_ATTEMPTED')}
                    >
                      NOT ATTEMPTED
                    </button>
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: 14, padding: '8px 12px', justifyContent: 'center' }}
                      onClick={() => handleSaveQuestionMark('FLAGGED')}
                    >
                      FLAG FOR REVIEW
                    </button>
                  </div>

                  <button
                    className="btn btn-secondary"
                    style={{ fontSize: 14, padding: '8px 16px', justifyContent: 'center', marginTop: 4 }}
                    onClick={handleNextQuestion}
                    disabled={activeQIndex >= activeQuestions.length - 1}
                  >
                    NEXT QUESTION →
                  </button>
                </div>
              )}
            </div>
          )}

          {/* EVALNEXA COPILOT Slot (Strictly prompt compliant: compact, no fake scores) */}
          <div
            style={{
              background: 'rgba(14,26,43,0.03)',
              border: '1px dashed var(--border)',
              padding: '12px 14px',
              marginBottom: 16,
            }}
          >
            <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--gold)', fontWeight: 700, marginBottom: 4 }}>
              EVALNEXA COPILOT
            </div>
            <div style={{ fontSize: 14, color: 'var(--charcoal)' }}>
              AI assistance not available.
            </div>
          </div>

          {/* Submission Roster & Calculation */}
          <div style={{ marginTop: 'auto', borderTop: '2px solid var(--border)', paddingTop: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
              <span style={{ fontSize: 14, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--charcoal)', fontWeight: 700 }}>
                TOTAL CALCULATED MARKS
              </span>
              <span style={{ fontSize: 26, fontWeight: 700, color: 'var(--navy)' }}>
                {totalCalculatedMarks}
                {exam && <span style={{ fontSize: 16, color: 'var(--charcoal)' }}> / {exam.maximumMarks}</span>}
              </span>
            </div>

            {isInProgress && (
              <button
                className="btn btn-primary"
                style={{ width: '100%', fontSize: 17, padding: '12px 20px', justifyContent: 'center' }}
                onClick={() => {
                  setSubmitError('');
                  setShowSubmitModal(true);
                }}
              >
                SUBMIT EVALUATION →
              </button>
            )}

            {isSubmitted && (
              <div
                style={{
                  textAlign: 'center',
                  padding: '10px',
                  background: 'rgba(21, 128, 61, 0.12)',
                  color: '#15803d',
                  fontSize: 14,
                  fontWeight: 700,
                  border: '1px solid rgba(21, 128, 61, 0.25)',
                }}
              >
                ✓ Evaluation Submitted to Moderation
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/* SUBMISSION REVIEW SUMMARY MODAL */}
      {/* ============================================================ */}
      {showSubmitModal && (
        <div
          className="modal-backdrop"
          onClick={(e) => e.target === e.currentTarget && setShowSubmitModal(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(14,26,43,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: '#ffffff',
              border: '2px solid var(--border)',
              padding: '24px 28px',
              maxWidth: 520,
              width: '90%',
              boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
            }}
          >
            <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--gold)', fontWeight: 700 }}>
              MARKING VERIFICATION
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--navy)', margin: '4px 0 16px 0' }}>
              Submission Review Summary
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dotted var(--border)', paddingBottom: 6 }}>
                <span style={{ fontSize: 15, color: 'var(--charcoal)' }}>Script Code:</span>
                <strong style={{ fontSize: 16, color: 'var(--navy)' }}>{answerBook.answerBookCode}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dotted var(--border)', paddingBottom: 6 }}>
                <span style={{ fontSize: 15, color: 'var(--charcoal)' }}>Examination:</span>
                <strong style={{ fontSize: 15, color: 'var(--navy)' }}>{exam ? exam.title : 'Examination'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dotted var(--border)', paddingBottom: 6 }}>
                <span style={{ fontSize: 15, color: 'var(--charcoal)' }}>Questions Evaluated:</span>
                <strong style={{ fontSize: 16, color: markedCount === activeQuestions.length ? '#15803d' : 'var(--navy)' }}>
                  {markedCount} / {activeQuestions.length}
                </strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dotted var(--border)', paddingBottom: 6 }}>
                <span style={{ fontSize: 15, color: 'var(--charcoal)' }}>Questions Not Attempted:</span>
                <strong style={{ fontSize: 16, color: 'var(--charcoal)' }}>{notAttemptedCount}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dotted var(--border)', paddingBottom: 6 }}>
                <span style={{ fontSize: 15, color: 'var(--charcoal)' }}>Flags Recorded:</span>
                <strong style={{ fontSize: 16, color: flaggedCount > 0 ? '#b45309' : 'var(--charcoal)' }}>
                  {flaggedCount}
                </strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '2px solid var(--border)', paddingBottom: 6 }}>
                <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--navy)' }}>Total Final Marks:</span>
                <strong style={{ fontSize: 22, fontWeight: 700, color: 'var(--navy)' }}>
                  {totalCalculatedMarks} {exam && `/ ${exam.maximumMarks}`}
                </strong>
              </div>
            </div>

            {/* Unchecked Question Protection */}
            {!allQuestionsAccounted && (
              <div
                style={{
                  background: 'rgba(92,29,36,0.08)',
                  border: '1px solid var(--burgundy)',
                  padding: '12px 16px',
                  color: 'var(--burgundy)',
                  fontSize: 14,
                  lineHeight: 1.5,
                  marginBottom: 16,
                }}
              >
                <div>
                  <strong>Evaluation cannot be submitted yet.</strong>
                </div>
                <div style={{ marginTop: 4 }}>
                  {notStartedQuestions.map((q) => `Q${q.questionNumber}`).join(', ')} has not been evaluated.
                </div>
                <button
                  className="btn btn-secondary"
                  style={{
                    fontSize: 13,
                    padding: '4px 12px',
                    marginTop: 8,
                    color: 'var(--burgundy)',
                    borderColor: 'var(--burgundy)',
                  }}
                  onClick={() => {
                    const firstUnchecked = notStartedQuestions[0];
                    if (firstUnchecked) {
                      const idx = activeQuestions.findIndex((q) => q.questionNumber === firstUnchecked.questionNumber);
                      if (idx !== -1) setActiveQIndex(idx);
                    }
                    setShowSubmitModal(false);
                  }}
                >
                  Go to {notStartedQuestions[0] ? `Q${notStartedQuestions[0].questionNumber}` : 'missing question'}
                </button>
              </div>
            )}

            {submitError && (
              <div
                style={{
                  background: 'rgba(92,29,36,0.08)',
                  border: '1px solid var(--burgundy)',
                  padding: '10px 14px',
                  color: 'var(--burgundy)',
                  fontSize: 14,
                  marginBottom: 16,
                }}
              >
                ⚠ {submitError}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button
                className="btn btn-secondary"
                onClick={() => setShowSubmitModal(false)}
                style={{ fontSize: 14, padding: '8px 16px' }}
              >
                GO BACK
              </button>
              <button
                className="btn btn-primary"
                disabled={!allQuestionsAccounted || submitMutation.isPending}
                onClick={() => submitMutation.mutate()}
                style={{ fontSize: 15, padding: '8px 20px', background: 'var(--navy)', color: '#ffffff' }}
              >
                {submitMutation.isPending ? 'Transmitting…' : 'SUBMIT EVALUATION'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
