import React, { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { Evaluation, AnswerBook, Exam, User, Question, QuestionMarkItem } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';

interface ModerationDetailResponse {
  evaluation: Evaluation;
  moderationHistory: Array<{
    _id: string;
    decision: 'APPROVE' | 'RETURN';
    reason?: string;
    createdAt: string;
    moderatorId?: { name: string; email: string };
  }>;
  secondEvaluation?: {
    _id: string;
    totalMarks: number;
    examinerId?: { name: string; email: string };
    questionMarks?: QuestionMarkItem[];
  } | null;
}

export function ReviewDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // State
  const [selectedQuestionNumber, setSelectedQuestionNumber] = useState<number | null>(null);
  const [viewingPage, setViewingPage] = useState<number>(1);
  const [zoomScale, setZoomScale] = useState<number>(100);
  const [viewMode, setViewMode] = useState<'SCRIPT_ONLY' | 'SCRIPT_AND_TEXT'>('SCRIPT_ONLY');
  const [showApproveModal, setShowApproveModal] = useState<boolean>(false);
  const [showReturnModal, setShowReturnModal] = useState<boolean>(false);
  const [returnReason, setReturnReason] = useState<string>('');
  const [actionError, setActionError] = useState<string>('');
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  // 1. Fetch Evaluation and Moderation Details
  const { data: detailData, isLoading, isError } = useQuery<ModerationDetailResponse>({
    queryKey: ['moderation-detail', id],
    queryFn: async () => {
      const { data } = await apiClient.get(`/moderation/${id}`);
      return {
        evaluation: data.data,
        moderationHistory: data.history || [],
        secondEvaluation: data.secondEvaluation || null,
      };
    },
  });

  const evaluation = detailData?.evaluation;
  const moderationHistory = detailData?.moderationHistory || [];
  const secondEvaluation = detailData?.secondEvaluation;

  const ab = typeof evaluation?.answerBookId === 'object' ? (evaluation.answerBookId as unknown as AnswerBook) : null;
  const exam = ab && typeof ab.examId === 'object' ? (ab.examId as unknown as Exam) : null;
  const examiner = typeof evaluation?.examinerId === 'object' ? (evaluation.examinerId as unknown as User) : null;
  const examId = exam?._id || (typeof ab?.examId === 'string' ? ab.examId : '');

  // 2. Fetch Questions & Rubrics for context
  const { data: questions = [] } = useQuery<Question[]>({
    queryKey: ['exam-questions', examId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/exams/${examId}/questions`);
      return data.data;
    },
    enabled: Boolean(examId),
  });

  // 3. Fetch Answer Book Pages list
  const { data: pagesList = [] } = useQuery<{ pageNumber: number }[]>({
    queryKey: ['mod-paper-pages', ab?._id],
    queryFn: async () => {
      if (!ab?._id) return [];
      try {
        const { data } = await apiClient.get(`/answer-books/${ab._id}/pages`);
        return data.data.pages || [];
      } catch {
        return [];
      }
    },
    enabled: Boolean(ab?._id),
  });

  const totalPages = Math.max(pagesList.length, ab?.pageCount || 1);

  // 4. Fetch Secure Page Media
  const { data: pageMedia, isLoading: isPageLoading } = useQuery<{
    pageNumber: number;
    secureUrl?: string;
    ocr?: { text?: string; confidence?: number | null };
    quality?: { status?: string; blurScore?: number };
    format?: string;
  } | null>({
    queryKey: ['mod-paper-page-media', ab?._id, viewingPage],
    queryFn: async () => {
      if (!ab?._id) return null;
      try {
        const { data } = await apiClient.get(`/answer-books/${ab._id}/pages/${viewingPage}`);
        return data.data;
      } catch {
        return null;
      }
    },
    enabled: Boolean(ab?._id),
  });

  // Approval Mutation
  const approveMutation = useMutation({
    mutationFn: async () => {
      await apiClient.post(`/moderation/${id}/approve`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['moderation-queue'] });
      queryClient.invalidateQueries({ queryKey: ['moderation-stats'] });
      setShowApproveModal(false);
      navigate('/review');
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || 'Approval failed';
      setActionError(msg);
      setShowApproveModal(false);
    },
  });

  // Return Mutation
  const returnMutation = useMutation({
    mutationFn: async (reason: string) => {
      await apiClient.post(`/moderation/${id}/return`, { reason });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['moderation-queue'] });
      queryClient.invalidateQueries({ queryKey: ['moderation-stats'] });
      setShowReturnModal(false);
      navigate('/review');
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || 'Return failed';
      setActionError(msg);
      setShowReturnModal(false);
    },
  });

  if (isLoading) {
    return (
      <div className="state-container" style={{ padding: 'var(--space-12)' }}>
        <div className="spinner" />
        <div style={{ marginTop: 'var(--space-3)', fontSize: 16 }}>Loading evaluation docket…</div>
      </div>
    );
  }

  if (isError || !evaluation) {
    return (
      <div className="state-container" style={{ padding: 'var(--space-10)' }}>
        <div className="state-title" style={{ fontSize: 22, fontFamily: 'Cambria, serif' }}>Evaluation Not Found</div>
        <div className="state-body" style={{ fontSize: 14, color: 'var(--text-muted)', marginTop: 4 }}>
          The requested evaluation docket could not be retrieved from MongoDB.
        </div>
        <Link to="/review" className="btn btn-secondary state-action" style={{ marginTop: 'var(--space-4)', fontSize: 14 }}>
          ← Return to Review Queue
        </Link>
      </div>
    );
  }

  const canAct = ['SUBMITTED', 'UNDER_REVIEW'].includes(evaluation.status);

  // ============================================================
  // Deterministic Quality Gates (Section 17 & 44)
  // ============================================================
  const totalExpectedQuestions = exam?.totalQuestions || questions.length || 0;
  const questionMarksMap = new Map<number, QuestionMarkItem>();
  (evaluation.questionMarks || []).forEach((q) => questionMarksMap.set(q.questionNumber, q));

  const deterministicIssues: string[] = [];

  // Check every expected question coverage
  if (totalExpectedQuestions > 0) {
    for (let i = 1; i <= totalExpectedQuestions; i++) {
      const qm = questionMarksMap.get(i);
      if (!qm || qm.status === 'NOT_STARTED') {
        deterministicIssues.push(`Question ${i} has not been evaluated.`);
      }
    }
  }

  // Arithmetic and bounds check
  let computedSum = 0;
  (evaluation.questionMarks || []).forEach((qm) => {
    computedSum += qm.marks || 0;
    const matchQ = questions.find((q) => q.questionNumber === qm.questionNumber);
    if (matchQ && qm.marks > matchQ.maximumMarks) {
      deterministicIssues.push(`Q${qm.questionNumber} mark (${qm.marks}) exceeds rubric maximum (${matchQ.maximumMarks}).`);
    }
  });

  if (exam?.maximumMarks !== undefined && (evaluation.totalMarks ?? 0) > exam.maximumMarks) {
    deterministicIssues.push(`Total awarded marks (${evaluation.totalMarks}) exceeds examination maximum (${exam.maximumMarks}).`);
  }

  if (Math.abs(computedSum - (evaluation.totalMarks ?? 0)) > 0.01) {
    deterministicIssues.push(`Arithmetic discrepancy: Question sum (${computedSum}) ≠ Awarded total (${evaluation.totalMarks}).`);
  }

  if (ab?.qualityStatus === 'RESCAN_REQUIRED') {
    deterministicIssues.push('Digital answer book is marked RESCAN_REQUIRED by scanning quality pipeline.');
  }

  const isDeterministicValid = deterministicIssues.length === 0;

  // Selected question mark details
  const selectedQuestionMarks = selectedQuestionNumber !== null ? questionMarksMap.get(selectedQuestionNumber) : null;
  const selectedQuestionRubric = selectedQuestionNumber !== null ? questions.find((q) => q.questionNumber === selectedQuestionNumber) : null;

  return (
    <div style={{ maxWidth: 1600, margin: '0 auto' }}>
      {/* Breadcrumb & Flow Indicator Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-3)', flexWrap: 'wrap', gap: 8 }}>
        <div className="breadcrumbs" style={{ fontSize: 13, margin: 0 }}>
          <Link to="/review">Review Queue</Link>
          <span className="breadcrumbs__sep">›</span>
          <span style={{ fontWeight: 700, color: 'var(--parchment-navy)' }}>{ab?.answerBookCode || id}</span>
        </div>

        {/* Top Workflow Bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>FLOW:</span>
          <span className="label-mono" style={{ fontSize: 12, fontWeight: 700, color: 'var(--parchment-navy)' }}>1. SUBMITTED</span>
          <span style={{ color: 'var(--parchment-border)' }}>→</span>
          <span className="label-mono" style={{ fontSize: 12, fontWeight: 700, color: 'var(--parchment-gold)' }}>2. REVIEW (Active)</span>
          <span style={{ color: 'var(--parchment-border)' }}>→</span>
          <span className="label-mono" style={{ fontSize: 12, fontWeight: 700, color: isDeterministicValid ? 'var(--status-approved-text)' : 'var(--status-returned-text)' }}>
            3. VERIFY ({isDeterministicValid ? 'VALID' : 'ISSUES'})
          </span>
          <span style={{ color: 'var(--parchment-border)' }}>→</span>
          <span className="label-mono" style={{ fontSize: 12, fontWeight: 700, color: 'var(--parchment-navy)' }}>4. DECISION</span>
        </div>
      </div>

      {/* Main Header Banner */}
      <div
        className="page-header"
        style={{
          marginBottom: 'var(--space-4)',
          background: 'rgba(255,255,255,0.7)',
          padding: 'var(--space-4) var(--space-5)',
          borderRadius: 'var(--radius-sm)',
          border: '1px solid var(--parchment-border)',
        }}
      >
        <div>
          <div className="page-header__eyebrow" style={{ fontSize: 12, letterSpacing: '0.08em', color: 'var(--parchment-gold)' }}>
            MODERATION & QUALITY CENTER · OFFICIAL EXAMINATION REVIEW DESK
          </div>
          <h1 className="page-header__title" style={{ fontSize: 32, fontWeight: 700, margin: '4px 0', fontFamily: 'Cambria, serif' }}>
            {exam?.title || 'Examination Review'}
          </h1>
          <p className="page-header__subtitle" style={{ fontSize: 15, color: 'var(--text-muted)', margin: 0 }}>
            Subject: <strong style={{ color: 'var(--parchment-navy)' }}>{exam?.subjectCode} · {exam?.subjectName}</strong> | Academic Session: {exam?.academicSession || 'Current'}
          </p>
        </div>
        <div className="page-header__actions" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ textAlign: 'right' }}>
            <div className="label-caps" style={{ fontSize: 10, color: 'var(--text-muted)' }}>Status</div>
            <StatusBadge status={evaluation.status} />
          </div>
        </div>
      </div>

      {actionError && (
        <div
          style={{
            padding: 'var(--space-3) var(--space-4)',
            background: 'var(--status-returned-bg)',
            color: 'var(--status-returned-text)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid rgba(180,40,40,0.3)',
            marginBottom: 'var(--space-4)',
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          ⚠ {actionError}
        </div>
      )}

      {/* ============================================================ */}
      {/* THREE-COLUMN MODERATION WORKSPACE (22% / 52% / 26%) */}
      {/* ============================================================ */}
      <div className="mod-workspace-grid">
        {/* ============================================================ */}
        {/* LEFT COLUMN: Review Navigation (Section 13) */}
        {/* ============================================================ */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {/* Script Dossier Card */}
          <div className="folio-card">
            <div className="folio-card__header">
              <span className="folio-card__title" style={{ fontSize: 16, fontFamily: 'Cambria, serif' }}>
                Script Information
              </span>
            </div>
            <div className="folio-card__body" style={{ padding: 'var(--space-4)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                <div>
                  <div className="label-caps" style={{ fontSize: 10, color: 'var(--text-muted)' }}>Script Code</div>
                  <div style={{ fontFamily: 'Cambria, serif', fontSize: 18, fontWeight: 700, color: 'var(--parchment-navy)' }}>
                    {ab?.answerBookCode}
                  </div>
                  {ab?.studentCode && (
                    <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      Student Ref: {ab.studentCode}
                    </div>
                  )}
                </div>

                <div>
                  <div className="label-caps" style={{ fontSize: 10, color: 'var(--text-muted)' }}>Examiner</div>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{examiner?.name || 'Unassigned'}</div>
                  <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{examiner?.email}</div>
                </div>

                <div>
                  <div className="label-caps" style={{ fontSize: 10, color: 'var(--text-muted)' }}>Submitted At</div>
                  <div className="label-mono" style={{ fontSize: 11 }}>
                    {evaluation.submittedAt ? new Date(evaluation.submittedAt).toLocaleString() : '—'}
                  </div>
                </div>

                <div>
                  <div className="label-caps" style={{ fontSize: 10, color: 'var(--text-muted)' }}>Document Custody</div>
                  <div style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
                    <span>{ab?.pageCount || 1} Scanned Pages</span>
                    <span
                      className="label-mono"
                      style={{
                        fontSize: 9.5,
                        fontWeight: 700,
                        padding: '1px 5px',
                        borderRadius: 2,
                        background: ab?.qualityStatus === 'RESCAN_REQUIRED' ? 'var(--status-returned-bg)' : 'var(--status-approved-bg)',
                        color: ab?.qualityStatus === 'RESCAN_REQUIRED' ? 'var(--status-returned-text)' : 'var(--status-approved-text)',
                      }}
                    >
                      {ab?.qualityStatus || 'VERIFIED'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Question List Card (Q1, Q2, Q3...) */}
          <div className="folio-card">
            <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="folio-card__title" style={{ fontSize: 16, fontFamily: 'Cambria, serif' }}>
                Question Navigation
              </span>
              <span className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                {questionMarksMap.size} / {totalExpectedQuestions || questionMarksMap.size} EVALUATED
              </span>
            </div>

            <div className="folio-card__body" style={{ padding: 'var(--space-2)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {Array.from({ length: totalExpectedQuestions || Math.max(questionMarksMap.size, 1) }).map((_, idx) => {
                  const qNum = idx + 1;
                  const qm = questionMarksMap.get(qNum);
                  const rubric = questions.find((q) => q.questionNumber === qNum);
                  const isSelected = selectedQuestionNumber === qNum;

                  // State label and color
                  const status = qm?.status || 'NOT_STARTED';
                  const isMarked = status === 'MARKED';
                  const isFlagged = status === 'FLAGGED';
                  const isNotAttempted = status === 'NOT_ATTEMPTED';
                  const isNotEvaluated = status === 'NOT_STARTED';

                  const badgeBg = isMarked
                    ? 'var(--status-approved-bg)'
                    : isFlagged
                    ? 'var(--status-returned-bg)'
                    : isNotAttempted
                    ? 'rgba(14,26,43,0.06)'
                    : 'rgba(255,100,50,0.12)';

                  const badgeColor = isMarked
                    ? 'var(--status-approved-text)'
                    : isFlagged
                    ? 'var(--status-returned-text)'
                    : isNotAttempted
                    ? 'var(--text-muted)'
                    : 'rgb(200,60,20)';

                  return (
                    <button
                      key={qNum}
                      type="button"
                      onClick={() => setSelectedQuestionNumber(isSelected ? null : qNum)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '8px 10px',
                        background: isSelected ? 'rgba(14,26,43,0.08)' : 'transparent',
                        border: isSelected ? '1px solid var(--parchment-navy)' : '1px solid transparent',
                        borderRadius: 'var(--radius-sm)',
                        cursor: 'pointer',
                        textAlign: 'left',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontFamily: 'Cambria, serif', fontWeight: 700, fontSize: 14 }}>
                          Q{qNum}
                        </span>
                        {rubric && (
                          <span className="label-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                            /{rubric.maximumMarks}m
                          </span>
                        )}
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontFamily: 'Cambria, serif', fontSize: 14, fontWeight: 700 }}>
                          {qm ? `${qm.marks}m` : '—'}
                        </span>
                        <span
                          className="label-mono"
                          style={{
                            fontSize: 9.5,
                            fontWeight: 700,
                            padding: '2px 5px',
                            borderRadius: 2,
                            background: badgeBg,
                            color: badgeColor,
                          }}
                        >
                          {isNotEvaluated ? 'NOT EVALUATED' : status}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>

              {selectedQuestionNumber !== null && selectedQuestionRubric && (
                <div
                  style={{
                    marginTop: 'var(--space-3)',
                    padding: 'var(--space-3)',
                    background: 'rgba(255,255,255,0.8)',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--parchment-border)',
                  }}
                >
                  <div className="label-caps" style={{ fontSize: 10, color: 'var(--parchment-gold)', marginBottom: 2 }}>
                    Q{selectedQuestionNumber} Rubric Details
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, fontFamily: 'Cambria, serif', marginBottom: 4 }}>
                    {selectedQuestionRubric.text}
                  </div>
                  {selectedQuestionMarks?.comment && (
                    <div style={{ marginTop: 4, fontSize: 12, background: 'rgba(14,26,43,0.03)', padding: 6, borderRadius: 2 }}>
                      <strong style={{ fontSize: 11 }}>Examiner Note:</strong> {selectedQuestionMarks.comment}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ============================================================ */}
        {/* CENTER COLUMN: Digital Answer Script Viewer (Section 14 & 15) */}
        {/* ============================================================ */}
        <div className="folio-card" style={{ display: 'flex', flexDirection: 'column', minHeight: 740, border: '1px solid var(--parchment-border)' }}>
          {/* Viewer Toolbar */}
          <div
            className="folio-card__header"
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 8,
              background: 'rgba(14,26,43,0.04)',
              padding: '8px 14px',
            }}
          >
            {/* Page Navigation */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={viewingPage <= 1}
                onClick={() => setViewingPage((p) => Math.max(1, p - 1))}
                style={{ fontSize: 12, padding: '4px 10px' }}
              >
                ← Prev
              </button>
              <span className="label-mono" style={{ fontSize: 12, fontWeight: 700, padding: '0 4px' }}>
                Page {viewingPage} of {totalPages}
              </span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={viewingPage >= totalPages}
                onClick={() => setViewingPage((p) => Math.min(totalPages, p + 1))}
                style={{ fontSize: 12, padding: '4px 10px' }}
              >
                Next →
              </button>
            </div>

            {/* View Mode Toggle: SCRIPT ONLY vs SCRIPT + TEXT */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'rgba(0,0,0,0.06)', padding: 2, borderRadius: 4 }}>
              <button
                type="button"
                onClick={() => setViewMode('SCRIPT_ONLY')}
                style={{
                  padding: '3px 8px',
                  fontSize: 11,
                  fontFamily: 'Cambria, serif',
                  fontWeight: viewMode === 'SCRIPT_ONLY' ? 700 : 500,
                  background: viewMode === 'SCRIPT_ONLY' ? '#fff' : 'transparent',
                  border: 'none',
                  borderRadius: 3,
                  cursor: 'pointer',
                  boxShadow: viewMode === 'SCRIPT_ONLY' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                }}
              >
                SCRIPT ONLY
              </button>
              <button
                type="button"
                onClick={() => setViewMode('SCRIPT_AND_TEXT')}
                style={{
                  padding: '3px 8px',
                  fontSize: 11,
                  fontFamily: 'Cambria, serif',
                  fontWeight: viewMode === 'SCRIPT_AND_TEXT' ? 700 : 500,
                  background: viewMode === 'SCRIPT_AND_TEXT' ? '#fff' : 'transparent',
                  border: 'none',
                  borderRadius: 3,
                  cursor: 'pointer',
                  boxShadow: viewMode === 'SCRIPT_AND_TEXT' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                }}
              >
                SCRIPT + OCR
              </button>
            </div>

            {/* Zoom & Fullscreen Controls */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setZoomScale((z) => Math.max(60, z - 15))}
                style={{ fontSize: 12, padding: '3px 8px' }}
                title="Zoom Out"
              >
                –
              </button>
              <span className="label-mono" style={{ fontSize: 11 }}>{zoomScale}%</span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setZoomScale((z) => Math.min(200, z + 15))}
                style={{ fontSize: 12, padding: '3px 8px' }}
                title="Zoom In"
              >
                +
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setZoomScale(100)}
                style={{ fontSize: 11, padding: '3px 6px' }}
              >
                Reset
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setIsFullscreen(!isFullscreen)}
                style={{ fontSize: 11, padding: '3px 6px' }}
              >
                {isFullscreen ? 'Exit Full' : 'Fit'}
              </button>
            </div>
          </div>

          {/* Viewer Canvas Area (Solid neutral background, zero watermark interference) */}
          <div
            className="folio-card__body"
            style={{
              flex: 1,
              background: '#2b2e33',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'flex-start',
              padding: 'var(--space-4)',
              overflowY: 'auto',
              maxHeight: isFullscreen ? '85vh' : '650px',
              position: 'relative',
            }}
          >
            {isPageLoading ? (
              <div className="state-container" style={{ color: '#fff', margin: 'auto' }}>
                <div className="spinner" />
                <div style={{ marginTop: 8, fontSize: 14 }}>Loading authenticated page scan…</div>
              </div>
            ) : pageMedia?.secureUrl ? (
              <div
                style={{
                  width: `${zoomScale}%`,
                  maxWidth: zoomScale <= 100 ? '760px' : 'none',
                  background: '#fff',
                  boxShadow: '0 6px 24px rgba(0,0,0,0.6)',
                  borderRadius: 2,
                  overflow: 'hidden',
                  transition: 'width 0.15s ease',
                }}
              >
                {pageMedia.format === 'pdf' ? (
                  <iframe
                    src={pageMedia.secureUrl}
                    title={`Page ${viewingPage}`}
                    style={{ width: '100%', height: '600px', border: 'none' }}
                  />
                ) : (
                  <img
                    src={pageMedia.secureUrl}
                    alt={`Scanned Answer Sheet Page ${viewingPage}`}
                    style={{ width: '100%', height: 'auto', display: 'block' }}
                  />
                )}
              </div>
            ) : ab?.pdfUrl ? (
              <div style={{ width: '100%', height: 600 }}>
                <iframe src={ab.pdfUrl} title="Script PDF" style={{ width: '100%', height: '100%', border: 'none' }} />
              </div>
            ) : (
              <div className="state-container" style={{ color: '#94a3b8', margin: 'auto' }}>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#f1f5f9', marginBottom: 4, fontFamily: 'Cambria, serif' }}>
                  Digital answer script scan unavailable.
                </div>
                <div style={{ fontSize: 13, maxWidth: 360 }}>
                  No authenticated page images currently mapped for Page {viewingPage}.
                </div>
              </div>
            )}

            {/* OCR / Extracted Text Drawer (Section 15) */}
            {viewMode === 'SCRIPT_AND_TEXT' && (
              <div
                style={{
                  marginTop: 'var(--space-4)',
                  width: '100%',
                  maxWidth: '760px',
                  background: '#1e2227',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: 4,
                  padding: 'var(--space-3)',
                  color: '#e2e8f0',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <div className="label-caps" style={{ fontSize: 10, color: 'var(--parchment-gold)' }}>
                    OCR & HANDWRITING TEXT EXTRACTION (ASSISTANCE ONLY)
                  </div>
                  {pageMedia?.ocr?.confidence !== undefined && pageMedia?.ocr?.confidence !== null ? (
                    <span className="label-mono" style={{ fontSize: 10, color: '#94a3b8' }}>
                      Confidence: {Math.round(pageMedia.ocr.confidence * 100)}%
                    </span>
                  ) : null}
                </div>
                <div
                  style={{
                    fontFamily: 'Cambria, serif',
                    fontSize: 14,
                    lineHeight: 1.6,
                    maxHeight: 160,
                    overflowY: 'auto',
                    whiteSpace: 'pre-wrap',
                    color: pageMedia?.ocr?.text ? '#f1f5f9' : '#94a3b8',
                  }}
                >
                  {pageMedia?.ocr?.text || 'Text extraction unavailable for this page.'}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ============================================================ */}
        {/* RIGHT COLUMN: Moderation Decision Docket (Sections 16 - 23) */}
        {/* ============================================================ */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {/* Mark Summary Card */}
          <div className="folio-card">
            <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="folio-card__title" style={{ fontSize: 16, fontFamily: 'Cambria, serif' }}>
                Mark Summary
              </span>
              <span className="label-caps" style={{ fontSize: 10, color: 'var(--text-muted)' }}>Score Formulation</span>
            </div>

            <div className="folio-card__body" style={{ padding: 'var(--space-4)' }}>
              <div style={{ textAlign: 'center', marginBottom: 'var(--space-4)', padding: 'var(--space-3)', background: 'rgba(14,26,43,0.03)', borderRadius: 'var(--radius-sm)' }}>
                <div className="label-caps" style={{ fontSize: 11, color: 'var(--text-muted)' }}>Total Awarded Marks</div>
                <div style={{ fontSize: 34, fontWeight: 700, fontFamily: 'Cambria, serif', color: 'var(--parchment-navy)', marginTop: 2 }}>
                  {evaluation.totalMarks ?? 0}
                  {exam && <span style={{ fontSize: 16, color: 'var(--text-muted)', fontWeight: 400 }}> / {exam.maximumMarks}</span>}
                </div>
              </div>

              {/* Question breakdown list */}
              <div className="label-caps" style={{ fontSize: 10, marginBottom: 6 }}>Question Marks Breakdown</div>
              <div style={{ maxHeight: 150, overflowY: 'auto', border: '1px solid var(--parchment-border)', borderRadius: 2 }}>
                <table className="data-table" style={{ width: '100%', fontSize: 12, margin: 0 }}>
                  <tbody>
                    {(evaluation.questionMarks || []).map((qm) => {
                      const matchQ = questions.find((q) => q.questionNumber === qm.questionNumber);
                      return (
                        <tr key={qm.questionNumber}>
                          <td style={{ fontWeight: 600 }}>Q{qm.questionNumber}</td>
                          <td style={{ fontFamily: 'Cambria, serif', fontWeight: 700 }}>
                            {qm.marks}
                            {matchQ && <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>/{matchQ.maximumMarks}</span>}
                          </td>
                          <td style={{ textAlign: 'right' }}>
                            <span className="label-mono" style={{ fontSize: 9 }}>{qm.status}</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Completeness & Deterministic Quality Gates (Section 17 & 44) */}
          <div className="folio-card">
            <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="folio-card__title" style={{ fontSize: 15, fontFamily: 'Cambria, serif' }}>
                Deterministic Quality Gate
              </span>
              <span
                className="label-mono"
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  padding: '2px 6px',
                  borderRadius: 2,
                  background: isDeterministicValid ? 'var(--status-approved-bg)' : 'var(--status-returned-bg)',
                  color: isDeterministicValid ? 'var(--status-approved-text)' : 'var(--status-returned-text)',
                }}
              >
                {isDeterministicValid ? '✓ PASSED' : '⚠ BLOCKING'}
              </span>
            </div>

            <div className="folio-card__body" style={{ padding: 'var(--space-3)' }}>
              {isDeterministicValid ? (
                <div style={{ fontSize: 13, color: 'var(--status-approved-text)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <div>✓ All questions evaluated</div>
                  <div>✓ Marks within maximum boundaries</div>
                  <div>✓ Arithmetic total sum verified</div>
                  <div>✓ Digital script custody confirmed</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--status-returned-text)' }}>
                    Approval blocked due to {deterministicIssues.length} rule violation(s):
                  </div>
                  {deterministicIssues.map((issue, idx) => (
                    <div key={idx} style={{ fontSize: 12, color: 'var(--status-returned-text)', background: 'rgba(180,40,40,0.06)', padding: '4px 6px', borderRadius: 2 }}>
                      • {issue}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Examiner Flags & Comments (Section 19 & 20) */}
          <div className="folio-card">
            <div className="folio-card__header">
              <span className="folio-card__title" style={{ fontSize: 15, fontFamily: 'Cambria, serif' }}>
                Examiner Commentary & Flags
              </span>
            </div>
            <div className="folio-card__body" style={{ padding: 'var(--space-3)' }}>
              {/* Flagged questions if any */}
              {evaluation.questionMarks?.some((q) => q.status === 'FLAGGED') ? (
                <div style={{ marginBottom: 'var(--space-3)' }}>
                  <div className="label-caps" style={{ fontSize: 10, color: 'var(--status-returned-text)' }}>EXAMINER FLAGS</div>
                  {evaluation.questionMarks.filter((q) => q.status === 'FLAGGED').map((q) => (
                    <div key={q.questionNumber} style={{ fontSize: 12, background: 'var(--status-returned-bg)', color: 'var(--status-returned-text)', padding: 6, borderRadius: 2, marginTop: 4 }}>
                      <strong>Q{q.questionNumber}:</strong> {q.comment || 'Flagged for moderation review'}
                    </div>
                  ))}
                </div>
              ) : null}

              {/* Concluding remarks */}
              <div>
                <div className="label-caps" style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>General Remarks</div>
                <div style={{ fontSize: 13, fontFamily: 'Cambria, serif', background: 'rgba(255,255,255,0.7)', padding: 8, borderRadius: 2, border: '1px solid var(--parchment-border)' }}>
                  {evaluation.remarks || 'No general commentary recorded by examiner.'}
                </div>
              </div>
            </div>
          </div>

          {/* Double Evaluation Section (Section 21 - Real data only) */}
          <div className="folio-card">
            <div className="folio-card__header">
              <span className="folio-card__title" style={{ fontSize: 14, fontFamily: 'Cambria, serif' }}>
                Double Evaluation Comparison
              </span>
            </div>
            <div className="folio-card__body" style={{ padding: 'var(--space-3)' }}>
              {secondEvaluation ? (
                <div style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div><strong>Examiner 1 ({examiner?.name || 'Primary'}):</strong> {evaluation.totalMarks ?? 0}m</div>
                  <div><strong>Examiner 2 ({secondEvaluation.examinerId?.name || 'Second'}):</strong> {secondEvaluation.totalMarks}m</div>
                  <div style={{ fontWeight: 700, color: Math.abs((evaluation.totalMarks ?? 0) - secondEvaluation.totalMarks) > 5 ? 'var(--status-returned-text)' : 'inherit' }}>
                    Score Discrepancy: {Math.abs((evaluation.totalMarks ?? 0) - secondEvaluation.totalMarks)} marks
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  Single evaluation — no second evaluation available.
                </div>
              )}
            </div>
          </div>

          {/* EvalNexa Copilot Section (Section 22 - Advisory only) */}
          <div className="folio-card" style={{ background: 'rgba(14,26,43,0.02)' }}>
            <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="folio-card__title" style={{ fontSize: 13, fontFamily: 'Cambria, serif', color: 'var(--parchment-gold)' }}>
                EvalNexa Copilot
              </span>
              <span className="label-mono" style={{ fontSize: 9, color: 'var(--text-muted)' }}>ADVISORY</span>
            </div>
            <div className="folio-card__body" style={{ padding: 'var(--space-3)' }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                AI moderation assistance is not available.
              </div>
            </div>
          </div>

          {/* Decision Area (Section 23 - Approve / Return) */}
          <div className="folio-card" style={{ border: '2px solid var(--parchment-border)', background: 'rgba(255,255,255,0.7)' }}>
            <div className="folio-card__header">
              <span className="folio-card__title" style={{ fontSize: 16, fontFamily: 'Cambria, serif' }}>
                Moderation Decision
              </span>
            </div>

            <div className="folio-card__body" style={{ padding: 'var(--space-4)' }}>
              {canAct ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                  {/* Primary: Approve Evaluation */}
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={!isDeterministicValid || approveMutation.isPending}
                    onClick={() => setShowApproveModal(true)}
                    style={{
                      width: '100%',
                      justifyContent: 'center',
                      fontSize: 15,
                      fontWeight: 700,
                      fontFamily: 'Cambria, serif',
                      padding: '11px',
                    }}
                  >
                    ✓ APPROVE EVALUATION
                  </button>

                  {!isDeterministicValid && (
                    <div style={{ fontSize: 11, color: 'var(--status-returned-text)', textAlign: 'center' }}>
                      ⚠ Resolve deterministic quality gate issues before approval can be granted.
                    </div>
                  )}

                  {/* Secondary: Return for Revision */}
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setShowReturnModal(true)}
                    style={{
                      width: '100%',
                      justifyContent: 'center',
                      fontSize: 14,
                      fontWeight: 600,
                      padding: '9px',
                      color: 'var(--status-returned-text)',
                      borderColor: 'rgba(180,40,40,0.4)',
                    }}
                  >
                    ↩ RETURN FOR REVISION
                  </button>

                  <div className="form-hint" style={{ fontSize: 11, textAlign: 'center', color: 'var(--text-muted)' }}>
                    Returns unlock the evaluation on the examiner's workspace with your documented feedback.
                  </div>
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: 'var(--space-2) 0' }}>
                  <div style={{ fontSize: 28, marginBottom: 4 }}>
                    {evaluation.status === 'APPROVED' ? '✓' : '↩'}
                  </div>
                  <div style={{ fontFamily: 'Cambria, serif', fontSize: 16, fontWeight: 700 }}>
                    {evaluation.status === 'APPROVED' ? 'Evaluation Certified & Approved' : 'Evaluation Remanded to Examiner'}
                  </div>
                  <div className="label-mono" style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                    Recorded in permanent MongoDB ledger.
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Decision History Log (Section 26) */}
          {moderationHistory.length > 0 && (
            <div className="folio-card">
              <div className="folio-card__header">
                <span className="folio-card__title" style={{ fontSize: 13, fontFamily: 'Cambria, serif' }}>
                  Docket Decision History
                </span>
              </div>
              <div className="folio-card__body" style={{ padding: 'var(--space-3)' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {moderationHistory.map((h) => (
                    <div key={h._id} style={{ fontSize: 11, borderBottom: '1px solid var(--parchment-border)', paddingBottom: 4 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                        <span>{h.decision === 'APPROVE' ? '✓ Approved' : '↩ Returned'} by {h.moderatorId?.name || 'Moderator'}</span>
                        <span className="label-mono">{new Date(h.createdAt).toLocaleDateString()}</span>
                      </div>
                      {h.reason && <div style={{ color: 'var(--text-muted)', marginTop: 2 }}>{h.reason}</div>}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ============================================================ */}
      {/* APPROVE CONFIRMATION MODAL */}
      {/* ============================================================ */}
      {showApproveModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowApproveModal(false)}>
          <div className="modal" style={{ maxWidth: 500 }}>
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow" style={{ fontSize: 11, color: 'var(--parchment-gold)' }}>BINDING CERTIFICATION</div>
                <div className="modal__title" style={{ fontSize: 20, fontFamily: 'Cambria, serif', fontWeight: 700 }}>
                  Approve this evaluation?
                </div>
              </div>
              <button className="modal__close" onClick={() => setShowApproveModal(false)}>✕</button>
            </div>
            <div className="modal__body">
              <p style={{ fontSize: 14, color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
                Approving this evaluation will certify the awarded marks, finalize custody in MongoDB, and synchronize with the University Control Center and Results ledger.
              </p>

              <div style={{ background: 'rgba(14,26,43,0.04)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)', display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
                <div><strong>Script Code:</strong> {ab?.answerBookCode}</div>
                <div><strong>Examiner:</strong> {examiner?.name}</div>
                <div><strong>Total Certified Marks:</strong> {evaluation.totalMarks ?? 0} {exam?.maximumMarks ? `/ ${exam.maximumMarks}` : ''}</div>
                <div><strong>Integrity Status:</strong> <span style={{ color: 'var(--status-approved-text)', fontWeight: 600 }}>✓ All deterministic quality checks passed</span></div>
              </div>
            </div>
            <div className="modal__footer">
              <button type="button" className="btn btn-secondary" onClick={() => setShowApproveModal(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={approveMutation.isPending}
                onClick={() => approveMutation.mutate()}
                style={{ fontWeight: 700, fontFamily: 'Cambria, serif' }}
              >
                {approveMutation.isPending ? 'Certifying…' : 'CONFIRM APPROVAL'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* RETURN FOR REVISION MODAL (Reason Required) */}
      {/* ============================================================ */}
      {showReturnModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowReturnModal(false)}>
          <div className="modal" style={{ maxWidth: 540 }}>
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow" style={{ fontSize: 11, color: 'var(--status-returned-text)' }}>REMAND EVALUATION</div>
                <div className="modal__title" style={{ fontSize: 20, fontFamily: 'Cambria, serif', fontWeight: 700 }}>
                  Return Evaluation to Examiner
                </div>
              </div>
              <button className="modal__close" onClick={() => setShowReturnModal(false)}>✕</button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!returnReason.trim()) return;
                returnMutation.mutate(returnReason);
              }}
            >
              <div className="modal__body">
                <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 'var(--space-3)' }}>
                  State the specific discrepancy, missing question coverage, or scoring clarification required from {examiner?.name || 'the examiner'}.
                </p>

                {/* Preset Quick Reasons */}
                <div style={{ marginBottom: 'var(--space-3)' }}>
                  <div className="label-caps" style={{ fontSize: 10, marginBottom: 4 }}>Quick Preset Reasons</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {[
                      'Incomplete evaluation — questions missing',
                      'Question requires scoring review against rubric',
                      'Arithmetic discrepancy in total marks',
                      'Script or page clarification required',
                      'Examiner feedback requires elaboration',
                    ].map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => setReturnReason(preset)}
                        style={{
                          fontSize: 11,
                          padding: '3px 8px',
                          background: returnReason === preset ? 'rgba(14,26,43,0.1)' : 'rgba(255,255,255,0.8)',
                          border: '1px solid var(--parchment-border)',
                          borderRadius: 3,
                          cursor: 'pointer',
                        }}
                      >
                        {preset}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="form-field">
                  <label className="form-label" style={{ fontSize: 12 }}>
                    Return Justification Reason <span className="required">*</span>
                  </label>
                  <textarea
                    className="form-input"
                    rows={4}
                    required
                    placeholder="Enter explicit review reason for examiner…"
                    value={returnReason}
                    onChange={(e) => setReturnReason(e.target.value)}
                    style={{ fontSize: 13, fontFamily: 'Cambria, serif' }}
                  />
                </div>
              </div>
              <div className="modal__footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowReturnModal(false)}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!returnReason.trim() || returnMutation.isPending}
                  style={{ background: 'var(--status-returned-text)', borderColor: 'var(--status-returned-text)' }}
                >
                  {returnMutation.isPending ? 'Remanding…' : 'CONFIRM RETURN FOR REVISION'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
