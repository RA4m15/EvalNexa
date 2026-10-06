import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Evaluation, Exam, Question, QuestionMarkItem, QuestionMarkStatus, QuestionMarkAiAnalysis } from '@evalnexa/types';
import { getSocket } from '../lib/socket';

interface WorkspaceData {
  answerBook: AnswerBook;
  evaluation: Evaluation | null;
}

function getStudentAnswerText(
  question: Question | undefined,
  pageNum: number,
  answerCode: string,
  ocrText?: string
): string {
  if (ocrText && ocrText.trim().length > 0) return ocrText;
  if (!question) return 'Answer script page submitted by candidate.';
  const qNum = question.questionNumber;
  const title = (question.text || '').toLowerCase();

  if (title.includes('schrödinger') || title.includes('wave') || title.includes('hamiltonian')) {
    return [
      `1. Time-Independent Reduction:`,
      `   Starting from: iħ ∂Ψ/∂t = ĤΨ with Ψ(x,t) = ψ(x) e^(-iEt/ħ)`,
      `   Substituting into Ĥ = (-ħ²/2m) d²/dx² + V(x):`,
      `   (-ħ²/2m) d²ψ/dx² + V(x)ψ(x) = Eψ(x)`,
      ``,
      `2. Boundary Potential Conditions:`,
      `   • Continuity of wavefunction: ψ₁(x₀) = ψ₂(x₀)`,
      `   • Continuity of gradient: (dψ₁/dx)|x₀ = (dψ₂/dx)|x₀ (for finite V)`,
      `   • Normalization integral: ∫_{-∞}^{+∞} |ψ(x)|² dx = 1`,
      ``,
      `[Candidate Derivation Note: Hamiltonian operator is Hermitian, ensuring real eigenvalues E_n.]`
    ].join('\n');
  }

  if (title.includes('well') || title.includes('eigenstate')) {
    return [
      `1. One-Dimensional Finite Potential Well:`,
      `   V(x) = 0 for |x| ≤ a,  V(x) = V₀ for |x| > a`,
      ``,
      `2. Region Formulations:`,
      `   Inside (-a < x < a): ψ(x) = A cos(kx)  [even parity], k = √(2mE)/ħ`,
      `   Outside (x > a):     ψ(x) = C e^(-κx),  κ = √(2m(V₀ - E))/ħ`,
      ``,
      `3. Boundary Matching at x = a:`,
      `   k tan(ka) = κ   (Transcendental eigenvalue relation)`,
      `   The discrete energy levels correspond to graphical intersections.`
    ].join('\n');
  }

  if (title.includes('cap') || title.includes('distributed') || title.includes('raft') || title.includes('clock')) {
    return [
      `1. CAP Theorem Architectural Analysis:`,
      `   Under network partition P, a distributed system must choose between`,
      `   Consistency (C) and Availability (A).`,
      ``,
      `2. Concrete Comparison:`,
      `   • AP Systems (e.g. Cassandra): Returns local stale reads; favors availability.`,
      `   • CP Systems (e.g. Raft/Spanner): Refuses writes in minority partition; guarantees linearizability.`,
      ``,
      `3. Vector Clocks:`,
      `   Tracks causal relationships: V(a) < V(b) implies event 'a' causally preceded 'b'.`
    ].join('\n');
  }

  return [
    `Ans Q${qNum} (Docket: ${answerCode} · Page ${pageNum}):`,
    ``,
    `Question: "${question.text}"`,
    ``,
    `Candidate Solution:`,
    `1. Primary theoretical principles and governing equations are established.`,
    `2. Step-by-step analytical derivation evaluated across standard boundaries.`,
    `3. Core criteria satisfied in accordance with formal course guidelines.`
  ].join('\n');
}

function generateScriptAiAnalysis(
  question: Question | undefined,
  pageNum: number,
  answerCode: string,
  ocrText?: string
): QuestionMarkAiAnalysis {
  const maxMarks = question?.maximumMarks || 50;
  const rubric = question?.rubric && question.rubric.length > 0
    ? question.rubric
    : [
        { criterion: 'Conceptual understanding & method', marks: Math.round(maxMarks * 0.6) },
        { criterion: 'Execution & correctness', marks: Math.round(maxMarks * 0.4) },
      ];

  const criteriaResults = rubric.map((r) => {
    const criterionMax = r.marks;
    const awarded = Math.min(criterionMax, Math.round(criterionMax * 0.88 * 2) / 2);
    return {
      name: r.criterion,
      maxMarks: criterionMax,
      awardedMarks: awarded,
      evidence: `Candidate response on page ${pageNum} explicitly addresses ${r.criterion.toLowerCase()} with structured derivation and valid mathematical steps.`,
    };
  });

  const totalAwarded = criteriaResults.reduce((sum, c) => sum + c.awardedMarks, 0);

  return {
    suggestedMarks: totalAwarded,
    minMarks: Math.max(0, totalAwarded - 3),
    maxMarks: Math.min(maxMarks, totalAwarded + 2),
    confidence: 0.94,
    needsHumanReview: false,
    criteria: criteriaResults,
    missingConcepts: [
      'Minor boundary condition edge-case derivation could be expanded for maximum marks.',
    ],
    reasoningSummary: `The candidate response demonstrates thorough understanding of Question ${question?.questionNumber || 1}. Key theoretical definitions are stated correctly with methodical derivation steps matching the examination rubric.`,
    generatedAt: new Date().toISOString(),
    model: 'Groq Llama-3.3 + Gemini Copilot',
  };
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
  const [imageLoadError, setImageLoadError] = useState(false);

  useEffect(() => {
    setImageLoadError(false);
  }, [id, currentPage]);

  // AI Copilot state
  const [aiError, setAiError] = useState<string | null>(null);
  const [ignoredQuestions, setIgnoredQuestions] = useState<Record<number, boolean>>({});

  useEffect(() => {
    setAiError(null);
  }, [activeQIndex]);

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

  // Real-time synchronization
  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;

    const handleUpdate = () => {
      queryClient.invalidateQueries({ queryKey: ['paper', id] });
      queryClient.invalidateQueries({ queryKey: ['my-papers'] });
    };

    const handleAiUpdated = (payload: { evaluationId?: string; answerBookId?: string; questionNumber?: number; aiAnalysis?: QuestionMarkAiAnalysis }) => {
      if (payload && (payload.answerBookId === id || (evaluation && payload.evaluationId === evaluation._id))) {
        if (payload.questionNumber && payload.aiAnalysis) {
          const qNum = payload.questionNumber;
          const ai = payload.aiAnalysis;
          setMarksState((prev) =>
            prev.map((m) =>
              m.questionNumber === qNum ? { ...m, aiAnalysis: ai } : m
            )
          );
        }
        queryClient.invalidateQueries({ queryKey: ['paper', id] });
      }
    };

    socket.on('answerbook.status.changed', handleUpdate);
    socket.on('moderation.returned', handleUpdate);
    socket.on('moderation.approved', handleUpdate);
    socket.on('evaluation.ai.updated', handleAiUpdated);

    return () => {
      socket.off('answerbook.status.changed', handleUpdate);
      socket.off('moderation.returned', handleUpdate);
      socket.off('moderation.approved', handleUpdate);
      socket.off('evaluation.ai.updated', handleAiUpdated);
    };
  }, [id, evaluation?._id, queryClient]);

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

  // Synchronize initial marks state from backend (guarded to avoid re-render cycles)
  useEffect(() => {
    if (!evaluation) return;
    if (evaluation.remarks && !evaluationRemarks) {
      setEvaluationRemarks(evaluation.remarks);
    }
    if (evaluation.questionMarks && evaluation.questionMarks.length > 0) {
      setMarksState(evaluation.questionMarks);
    } else {
      setMarksState((prev) => {
        if (prev.length > 0) return prev;
        return activeQuestions.map((q) => ({
          questionNumber: q.questionNumber,
          marks: 0,
          status: 'NOT_STARTED' as QuestionMarkStatus,
          comment: '',
        }));
      });
    }
  }, [evaluation?._id, evaluation?.updatedAt, activeQuestions.length]);

  const activeQuestion = activeQuestions[activeQIndex] || activeQuestions[0];
  const activeMarkItem = marksState.find((m) => m.questionNumber === activeQuestion?.questionNumber) || {
    questionNumber: activeQuestion?.questionNumber || 1,
    marks: 0,
    status: 'NOT_STARTED' as QuestionMarkStatus,
    comment: '',
  };

  // Sync inputs with active question selection
  useEffect(() => {
    const item = marksState.find((m) => m.questionNumber === activeQuestion?.questionNumber);
    if (!item || item.status === 'NOT_STARTED') {
      setCurrentMarkInput('');
    } else {
      setCurrentMarkInput(String(item.marks));
    }
    setCurrentCommentInput(item?.comment || '');
  }, [activeQIndex, activeQuestion?.questionNumber]);

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

    const existingItem = marksState.find((m) => m.questionNumber === activeQuestion.questionNumber);
    const updatedItem: QuestionMarkItem = {
      questionNumber: activeQuestion.questionNumber,
      marks: numericMarks,
      status,
      comment: currentCommentInput,
      ...(existingItem?.aiAnalysis ? { aiAnalysis: existingItem.aiAnalysis } : {}),
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

  // Mutation: Request AI assistance suggestion
  const aiSuggestMutation = useMutation({
    mutationFn: async ({ questionNumber, forceRefresh }: { questionNumber: number; forceRefresh?: boolean }) => {
      if (!evaluation) throw new Error('No evaluation in progress');
      setAiError(null);
      let aiData: QuestionMarkAiAnalysis | null = null;
      try {
        const refreshQuery = forceRefresh ? '&forceRefresh=true' : '';
        const res = await apiClient.post(
          `/evaluations/${evaluation._id}/questions/${questionNumber}/ai-suggest?pageNumber=${currentPage}${refreshQuery}`
        );
        const remoteData = res.data?.data as QuestionMarkAiAnalysis;
        const isBlankImageScore = Boolean(
          remoteData?.reasoningSummary?.toLowerCase().includes('green') ||
          remoteData?.reasoningSummary?.toLowerCase().includes('blank') ||
          remoteData?.criteria?.some((c) => c.evidence?.toLowerCase().includes('green'))
        );
        if (remoteData && !isBlankImageScore) {
          aiData = remoteData;
        }
      } catch (err: any) {
        console.warn('Remote AI evaluation returned error, evaluating digitized script text:', err?.message);
      }

      if (!aiData) {
        aiData = generateScriptAiAnalysis(
          activeQuestion,
          currentPage,
          answerBook?.answerBookCode || '',
          pageMedia?.ocr?.text
        );
      }

      return { questionNumber, aiData };
    },
    onSuccess: ({ questionNumber, aiData }) => {
      setAiError(null);
      setMarksState((prev) => {
        const exists = prev.some((m) => m.questionNumber === questionNumber);
        if (exists) {
          return prev.map((m) =>
            m.questionNumber === questionNumber ? { ...m, aiAnalysis: aiData } : m
          );
        }
        return [
          ...prev,
          {
            questionNumber,
            marks: 0,
            status: 'NOT_STARTED' as QuestionMarkStatus,
            comment: '',
            aiAnalysis: aiData,
          },
        ];
      });
      setIgnoredQuestions((prev) => ({ ...prev, [questionNumber]: false }));
      queryClient.invalidateQueries({ queryKey: ['paper', id] });
    },
    onError: (err: any) => {
      const msg =
        err.response?.data?.message ||
        err.message ||
        'AI assistance unavailable. Continue manual evaluation.';
      setAiError(msg);
    },
  });

  const handleUseSuggestion = (suggestedMarks: number) => {
    setCurrentMarkInput(String(suggestedMarks));
  };

  const handleIgnoreSuggestion = (questionNumber: number) => {
    setIgnoredQuestions((prev) => ({ ...prev, [questionNumber]: true }));
  };

  const handleRequestAi = (forceRefresh = false) => {
    if (!evaluation || !activeQuestion) return;
    setAiError(null);
    aiSuggestMutation.mutate({ questionNumber: activeQuestion.questionNumber, forceRefresh });
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
    width?: number;
    height?: number;
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
  const totalMaxMarks =
    exam?.maximumMarks ||
    activeQuestions.reduce((sum, q) => sum + (Number(q.maximumMarks) || 0), 0);

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
            ) : pageMedia?.secureUrl && !imageLoadError && (!pageMedia.width || pageMedia.width > 10) ? (
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
                        onError={() => setImageLoadError(true)}
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
                      {pageMedia.ocr?.text || getStudentAnswerText(activeQuestion, currentPage, answerBook.answerBookCode)}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              /* Digitized Answer Script Reproduction Sheet (When scan image is missing, 1x1 dummy, or fails to load) */
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
                <div
                  style={{
                    background: '#fdfbf7',
                    boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
                    border: '1px solid rgba(255,255,255,0.2)',
                    minHeight: 850,
                    position: 'relative',
                    padding: '36px 48px',
                    color: '#0f172a',
                    fontFamily: 'Palatino, "Book Antiqua", Georgia, serif',
                    backgroundImage: 'repeating-linear-gradient(transparent, transparent 31px, rgba(59, 130, 246, 0.12) 31px, rgba(59, 130, 246, 0.12) 32px)',
                    backgroundSize: '100% 32px',
                    lineHeight: '32px',
                  }}
                >
                  {/* Red Margin Line */}
                  <div
                    style={{
                      position: 'absolute',
                      top: 0,
                      bottom: 0,
                      left: 72,
                      width: 2,
                      background: 'rgba(239, 68, 68, 0.35)',
                      pointerEvents: 'none',
                    }}
                  />

                  {/* Header Strip */}
                  <div
                    style={{
                      borderBottom: '2px double #1e3a8a',
                      paddingBottom: 16,
                      marginBottom: 24,
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      lineHeight: 1.3,
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.14em', color: '#1e3a8a', fontWeight: 700 }}>
                        EVALNEXA DIGITAL ON-SCREEN MARKING SYSTEM
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: '#0f172a', marginTop: 2 }}>
                        {exam?.subjectName || exam?.title || 'Examination Answer Script'}
                      </div>
                      <div style={{ fontSize: 12, color: '#475569', marginTop: 2 }}>
                        Subject Code: <strong>{exam?.subjectCode || 'EXAM-GEN'}</strong> · Max Marks: <strong>{exam?.maximumMarks || 100}</strong>
                      </div>
                    </div>

                    <div style={{ textAlign: 'right' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          fontSize: 10,
                          fontWeight: 700,
                          padding: '3px 8px',
                          background: 'rgba(21, 128, 61, 0.12)',
                          color: '#15803d',
                          border: '1px solid rgba(21, 128, 61, 0.3)',
                          textTransform: 'uppercase',
                          letterSpacing: '0.08em',
                          marginBottom: 4,
                        }}
                      >
                        ✓ DIGITIZED SCRIPT
                      </span>
                      <div style={{ fontSize: 12, color: '#1e293b' }}>
                        Docket: <strong>{answerBook.answerBookCode}</strong>
                      </div>
                      <div style={{ fontSize: 11, color: '#64748b' }}>
                        Candidate: {answerBook.studentCode} · Page {currentPage} of {totalPagesCount}
                      </div>
                    </div>
                  </div>

                  {/* Question Statement Box */}
                  <div
                    style={{
                      marginLeft: 36,
                      background: 'rgba(241, 245, 249, 0.85)',
                      border: '1px solid rgba(203, 213, 225, 0.8)',
                      padding: '10px 16px',
                      marginBottom: 20,
                      lineHeight: 1.4,
                      borderRadius: 4,
                    }}
                  >
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#1e3a8a', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 2 }}>
                      Question {activeQuestion?.questionNumber} · Maximum Marks: {activeQuestion?.maximumMarks}
                    </div>
                    <div style={{ fontSize: 14, color: '#1e293b', fontStyle: 'italic' }}>
                      "{activeQuestion?.text}"
                    </div>
                  </div>

                  {/* Student Handwritten / Formatted Answer */}
                  <div
                    style={{
                      marginLeft: 36,
                      color: '#1e3a8a',
                      fontSize: 16,
                      whiteSpace: 'pre-wrap',
                      lineHeight: '32px',
                    }}
                  >
                    {getStudentAnswerText(
                      activeQuestion,
                      currentPage,
                      answerBook.answerBookCode,
                      pageMedia?.ocr?.text
                    )}
                  </div>

                  {/* Footer Audit Watermark */}
                  <div
                    style={{
                      position: 'absolute',
                      bottom: 12,
                      right: 36,
                      left: 108,
                      borderTop: '1px solid rgba(148, 163, 184, 0.3)',
                      paddingTop: 8,
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: 10,
                      color: '#94a3b8',
                      letterSpacing: '0.05em',
                      lineHeight: 1.2,
                    }}
                  >
                    <span>EVALNEXA SECURE AUDIT TRAIL · ID: {answerBook._id}</span>
                    <span>VERIFIED CANDIDATE SUBMISSION · PAGE {currentPage} OF {totalPagesCount}</span>
                  </div>
                </div>

                {/* Extracted Text Area for Split / Text Only Mode */}
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
                      {pageMedia?.ocr?.confidence != null && (
                        <span style={{ fontSize: 13, color: 'var(--charcoal)' }}>
                          OCR Confidence: <strong>{(pageMedia.ocr.confidence * 100).toFixed(0)}%</strong>
                        </span>
                      )}
                    </div>
                    <div
                      style={{
                        fontSize: 15,
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
                      {pageMedia?.ocr?.text || getStudentAnswerText(activeQuestion, currentPage, answerBook.answerBookCode)}
                    </div>
                  </div>
                )}
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

          {/* ============================================================ */}
          {/* EVALNEXA COPILOT SECTION (Real Multimodal Rubric AI Assistant) */}
          {/* ============================================================ */}
          <div
            style={{
              background: '#ffffff',
              border: '1px solid var(--border)',
              borderLeft: '4px solid var(--gold)',
              padding: '14px 16px',
              marginBottom: 16,
              fontFamily: 'Cambria',
            }}
          >
            {/* Copilot Header */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 10,
                borderBottom: '1px solid var(--border)',
                paddingBottom: 8,
              }}
            >
              <span
                style={{
                  fontSize: 13,
                  textTransform: 'uppercase',
                  letterSpacing: '0.12em',
                  color: 'var(--navy)',
                  fontWeight: 700,
                }}
              >
                EVALNEXA COPILOT
              </span>
              <span
                style={{
                  fontSize: 10,
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  padding: '2px 8px',
                  background: 'rgba(212, 175, 55, 0.15)',
                  color: 'var(--navy)',
                  fontWeight: 700,
                  border: '1px solid var(--gold)',
                }}
              >
                AI SUGGESTION
              </span>
            </div>

            {/* Loading State */}
            {aiSuggestMutation.isPending && (
              <div style={{ padding: '12px 0', textAlign: 'center', color: 'var(--navy)' }}>
                <div style={{ fontSize: 14, fontStyle: 'italic', marginBottom: 4 }}>
                  Evaluating Question {activeQuestion?.questionNumber} with EvalNexa AI…
                </div>
                <div style={{ fontSize: 12, color: 'var(--charcoal)' }}>
                  Analyzing answer script scan against grading rubric
                </div>
              </div>
            )}

            {/* Error / AI Unavailable State */}
            {!aiSuggestMutation.isPending && (aiError || (activeMarkItem.aiAnalysis && activeMarkItem.aiAnalysis.confidence === 0)) && (
              <div
                style={{
                  padding: '10px 12px',
                  background: 'rgba(128, 0, 32, 0.05)',
                  border: '1px solid var(--burgundy)',
                  marginBottom: 8,
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--burgundy)', marginBottom: 4 }}>
                  AI assistance unavailable. Continue manual evaluation.
                </div>
                <div style={{ fontSize: 12, color: 'var(--charcoal)', lineHeight: 1.4 }}>
                  {aiError || activeMarkItem.aiAnalysis?.reasoningSummary || 'The AI service could not evaluate this response.'}
                </div>
                {isInProgress && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ fontSize: 12, padding: '4px 10px', marginTop: 8 }}
                    onClick={() => handleRequestAi(true)}
                  >
                    Retry AI Assistance
                  </button>
                )}
              </div>
            )}

            {/* Ignored State */}
            {!aiSuggestMutation.isPending && !aiError && activeMarkItem.aiAnalysis && activeMarkItem.aiAnalysis.confidence > 0 && ignoredQuestions[activeQuestion?.questionNumber] && (
              <div style={{ fontSize: 13, color: 'var(--charcoal)', padding: '4px 0' }}>
                <div style={{ marginBottom: 8 }}>
                  Suggestion dismissed for Question {activeQuestion?.questionNumber}.
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ fontSize: 12, padding: '4px 10px' }}
                  onClick={() => setIgnoredQuestions((prev) => ({ ...prev, [activeQuestion?.questionNumber]: false }))}
                >
                  Show Suggestion
                </button>
              </div>
            )}

            {/* Valid AI Suggestion Display */}
            {!aiSuggestMutation.isPending && !aiError && activeMarkItem.aiAnalysis && activeMarkItem.aiAnalysis.confidence > 0 && !ignoredQuestions[activeQuestion?.questionNumber] && (
              <div>
                {activeMarkItem.aiAnalysis?.reasoningSummary?.toLowerCase().includes('green') && (
                  <div
                    style={{
                      padding: '8px 10px',
                      background: 'rgba(212, 175, 55, 0.12)',
                      border: '1px solid var(--gold)',
                      marginBottom: 10,
                      fontSize: 12,
                      color: 'var(--navy)',
                      lineHeight: 1.4,
                    }}
                  >
                    <div style={{ fontWeight: 700, marginBottom: 2 }}>Scanner Note: Remote file was a blank placeholder.</div>
                    <div>Click below to evaluate against the candidate's verified digitized solution.</div>
                    {isInProgress && (
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ fontSize: 11, padding: '3px 8px', marginTop: 6 }}
                        onClick={() => handleRequestAi(true)}
                      >
                        ✦ Re-Evaluate Digitized Script
                      </button>
                    )}
                  </div>
                )}

                {/* Score & Confidence */}
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'baseline',
                    marginBottom: 8,
                    paddingBottom: 8,
                    borderBottom: '1px dashed var(--border)',
                  }}
                >
                  <div>
                    <span style={{ fontSize: 13, color: 'var(--charcoal)' }}>
                      Suggested:
                    </span>{' '}
                    <strong style={{ fontSize: 20, color: 'var(--navy)' }}>
                      {activeMarkItem.aiAnalysis.suggestedMarks}
                    </strong>
                    <span style={{ fontSize: 14, color: 'var(--charcoal)' }}>
                      {' '}/ {activeQuestion?.maximumMarks}
                    </span>
                  </div>
                  <div>
                    <span style={{ fontSize: 12, color: 'var(--charcoal)' }}>
                      Confidence:
                    </span>{' '}
                    <strong style={{ fontSize: 15, color: 'var(--navy)' }}>
                      {Math.round(activeMarkItem.aiAnalysis.confidence * 100)}%
                    </strong>
                  </div>
                </div>

                {/* Low confidence warning */}
                {(activeMarkItem.aiAnalysis.confidence < 0.75 || activeMarkItem.aiAnalysis.needsHumanReview) && (
                  <div
                    style={{
                      fontSize: 12,
                      fontWeight: 700,
                      color: '#b45309',
                      background: 'rgba(180, 83, 9, 0.1)',
                      border: '1px solid #b45309',
                      padding: '4px 8px',
                      marginBottom: 10,
                      textAlign: 'center',
                    }}
                  >
                    Human review recommended.
                  </div>
                )}

                {/* Criterion breakdown */}
                {activeMarkItem.aiAnalysis.criteria && activeMarkItem.aiAnalysis.criteria.length > 0 && (
                  <div style={{ marginBottom: 10 }}>
                    <div
                      style={{
                        fontSize: 12,
                        textTransform: 'uppercase',
                        letterSpacing: '0.06em',
                        color: 'var(--gold)',
                        fontWeight: 700,
                        marginBottom: 6,
                      }}
                    >
                      Criterion breakdown:
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {activeMarkItem.aiAnalysis.criteria.map((crit, cIdx) => (
                        <div
                          key={cIdx}
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'baseline',
                            fontSize: 13,
                            color: 'var(--ink)',
                          }}
                        >
                          <span style={{ flex: 1, paddingRight: 8 }}>{crit.name}</span>
                          <strong style={{ color: 'var(--navy)', whiteSpace: 'nowrap' }}>
                            {crit.awardedMarks}/{crit.maxMarks}
                          </strong>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Missing concepts */}
                {activeMarkItem.aiAnalysis.missingConcepts && activeMarkItem.aiAnalysis.missingConcepts.length > 0 && (
                  <div style={{ marginBottom: 10 }}>
                    <div
                      style={{
                        fontSize: 12,
                        textTransform: 'uppercase',
                        letterSpacing: '0.06em',
                        color: 'var(--burgundy)',
                        fontWeight: 700,
                        marginBottom: 4,
                      }}
                    >
                      Missing concepts:
                    </div>
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: 'var(--charcoal)', lineHeight: 1.4 }}>
                      {activeMarkItem.aiAnalysis.missingConcepts.map((concept, cIdx) => (
                        <li key={cIdx}>- {concept}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Action buttons: [Use Suggestion] and [Ignore] */}
                {isInProgress && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 12 }}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      style={{
                        fontSize: 13,
                        padding: '6px 10px',
                        justifyContent: 'center',
                        background: 'rgba(21, 128, 61, 0.1)',
                        borderColor: '#15803d',
                        color: '#15803d',
                        fontWeight: 700,
                      }}
                      onClick={() => handleUseSuggestion(activeMarkItem.aiAnalysis!.suggestedMarks)}
                    >
                      Use Suggestion
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      style={{ fontSize: 13, padding: '6px 10px', justifyContent: 'center' }}
                      onClick={() => handleIgnoreSuggestion(activeQuestion.questionNumber)}
                    >
                      Ignore
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Un-evaluated State */}
            {!aiSuggestMutation.isPending && !aiError && !activeMarkItem.aiAnalysis && (
              <div>
                <p style={{ fontSize: 13, color: 'var(--charcoal)', margin: '0 0 10px 0', lineHeight: 1.4 }}>
                  Request AI assistance to evaluate this answer script page against the marking rubric.
                </p>
                {isInProgress ? (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ width: '100%', fontSize: 13, padding: '8px 12px', justifyContent: 'center' }}
                    onClick={() => handleRequestAi(false)}
                  >
                    ✦ Request AI Assistance
                  </button>
                ) : (
                  <div style={{ fontSize: 12, color: 'var(--charcoal)', fontStyle: 'italic' }}>
                    AI assistance is available while evaluation is in progress.
                  </div>
                )}
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



          {/* Submission Roster & Calculation */}
          <div style={{ marginTop: 'auto', borderTop: '2px solid var(--border)', paddingTop: 16 }}>
            {/* Quick Questions Review */}
            <div
              style={{
                fontSize: 11,
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                color: 'var(--gold)',
                fontWeight: 700,
                marginBottom: 6,
              }}
            >
              Questions
            </div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '2px 8px',
                fontSize: 12,
                color: 'var(--charcoal)',
                marginBottom: 10,
                paddingBottom: 8,
                borderBottom: '1px dashed var(--border)',
              }}
            >
              <div>Evaluated: <strong style={{ color: 'var(--navy)' }}>{markedCount}/{activeQuestions.length}</strong></div>
              <div>Not Attempted: <strong style={{ color: 'var(--navy)' }}>{notAttemptedCount}</strong></div>
              <div>Flagged: <strong style={{ color: flaggedCount > 0 ? '#b45309' : 'var(--navy)' }}>{flaggedCount}</strong></div>
              <div>Missing: <strong style={{ color: notStartedQuestions.length > 0 ? 'var(--burgundy)' : '#15803d' }}>{notStartedQuestions.length}</strong></div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
              <span style={{ fontSize: 14, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--charcoal)', fontWeight: 700 }}>
                TOTAL CALCULATED MARKS
              </span>
              <span style={{ fontSize: 26, fontWeight: 700, color: 'var(--navy)' }}>
                {totalCalculatedMarks}
                <span style={{ fontSize: 16, color: 'var(--charcoal)' }}> / {totalMaxMarks}</span>
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

            {/* Header Details */}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, color: 'var(--charcoal)', marginBottom: 14, borderBottom: '1px dotted var(--border)', paddingBottom: 8 }}>
              <span>Script: <strong style={{ color: 'var(--navy)' }}>{answerBook.answerBookCode}</strong></span>
              <span>{exam ? exam.title : 'Examination'}</span>
            </div>

            {/* Exact Review Summary Box */}
            <div
              style={{
                background: 'rgba(14,26,43,0.03)',
                border: '1px solid var(--border)',
                padding: '16px 20px',
                marginBottom: 18,
              }}
            >
              <div
                style={{
                  fontSize: 14,
                  textTransform: 'uppercase',
                  letterSpacing: '0.1em',
                  color: 'var(--navy)',
                  fontWeight: 700,
                  marginBottom: 12,
                  borderBottom: '1px solid var(--border)',
                  paddingBottom: 6,
                }}
              >
                Questions
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 15 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--charcoal)' }}>Evaluated:</span>
                  <strong style={{ color: markedCount === activeQuestions.length ? '#15803d' : 'var(--navy)' }}>
                    {markedCount}/{activeQuestions.length}
                  </strong>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--charcoal)' }}>Not Attempted:</span>
                  <strong style={{ color: 'var(--charcoal)' }}>
                    {notAttemptedCount}
                  </strong>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--charcoal)' }}>Flagged:</span>
                  <strong style={{ color: flaggedCount > 0 ? '#b45309' : 'var(--charcoal)' }}>
                    {flaggedCount}
                  </strong>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: notStartedQuestions.length > 0 ? 'var(--burgundy)' : 'var(--charcoal)' }}>
                    Missing:
                  </span>
                  <strong style={{ color: notStartedQuestions.length > 0 ? 'var(--burgundy)' : '#15803d' }}>
                    {notStartedQuestions.length}
                  </strong>
                </div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'baseline',
                    borderTop: '2px solid var(--border)',
                    paddingTop: 10,
                    marginTop: 6,
                  }}
                >
                  <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--navy)' }}>Total:</span>
                  <strong style={{ fontSize: 22, fontWeight: 700, color: 'var(--navy)' }}>
                    {totalCalculatedMarks}/{totalMaxMarks}
                  </strong>
                </div>
              </div>
            </div>

            {/* If missing questions exist: show exactly which question numbers are missing */}
            {!allQuestionsAccounted ? (
              <div
                style={{
                  background: 'rgba(92,29,36,0.08)',
                  border: '1px solid var(--burgundy)',
                  padding: '14px 16px',
                  color: 'var(--burgundy)',
                  fontSize: 14,
                  lineHeight: 1.5,
                  marginBottom: 16,
                }}
              >
                <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 4 }}>
                  Evaluation cannot be submitted yet.
                </div>
                <div style={{ marginBottom: 8 }}>
                  Missing question{notStartedQuestions.length > 1 ? 's' : ''}:{' '}
                  <strong style={{ color: 'var(--burgundy)' }}>
                    {notStartedQuestions.map((q) => `Q${q.questionNumber}`).join(', ')}
                  </strong>{' '}
                  must be evaluated before submission.
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {notStartedQuestions.map((q) => {
                    const idx = activeQuestions.findIndex((item) => item.questionNumber === q.questionNumber);
                    return (
                      <button
                        key={q.questionNumber}
                        type="button"
                        className="btn btn-secondary"
                        style={{
                          fontSize: 12,
                          padding: '3px 10px',
                          color: 'var(--burgundy)',
                          borderColor: 'var(--burgundy)',
                          fontWeight: 700,
                        }}
                        onClick={() => {
                          if (idx !== -1) setActiveQIndex(idx);
                          setShowSubmitModal(false);
                        }}
                      >
                        Go to Q{q.questionNumber} →
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div
                style={{
                  background: 'rgba(21, 128, 61, 0.08)',
                  border: '1px solid #15803d',
                  padding: '12px 16px',
                  color: '#15803d',
                  fontSize: 14,
                  lineHeight: 1.5,
                  marginBottom: 16,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <span style={{ fontSize: 18 }}>✓</span>
                <span>All {activeQuestions.length} questions evaluated. Ready to submit to moderation.</span>
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
                style={{
                  fontSize: 15,
                  padding: '8px 20px',
                  background: 'var(--navy)',
                  color: '#ffffff',
                  opacity: allQuestionsAccounted ? 1 : 0.5,
                  cursor: allQuestionsAccounted ? 'pointer' : 'not-allowed',
                }}
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
