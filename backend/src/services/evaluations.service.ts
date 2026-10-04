import mongoose from 'mongoose';
import { Evaluation, IEvaluation, IEvaluationQuestionMark } from '../models/Evaluation';
import { AnswerBook } from '../models/AnswerBook';
import { AnswerPage } from '../models/AnswerPage';
import { Question } from '../models/Question';
import { Exam } from '../models/Exam';
import { validateStateTransition } from './answerBooks.service';
import { logAuditAction } from './audit.service';
import { emitToAll, emitToRole } from '../sockets';
import { generateAuthorizedMediaUrl } from './media.service';
import { EvaluationAssistantService } from './EvaluationAssistantService';

export interface IAuthoritativeQuestion {
  questionNumber: number;
  maximumMarks: number;
  text?: string;
}

/**
 * Fetches official exam questions from MongoDB.
 * Falls back to Exam metadata if individual Question records are not populated.
 */
export async function fetchAuthoritativeQuestions(
  examId: string | mongoose.Types.ObjectId
): Promise<Map<number, IAuthoritativeQuestion>> {
  const officialQuestions = await Question.find({ examId }).sort({ questionNumber: 1 });
  const questionMap = new Map<number, IAuthoritativeQuestion>();

  if (officialQuestions.length > 0) {
    for (const q of officialQuestions) {
      questionMap.set(q.questionNumber, {
        questionNumber: q.questionNumber,
        maximumMarks: q.maximumMarks,
        text: q.text,
      });
    }
    return questionMap;
  }

  // Fallback to exam metadata if individual Question records are not populated
  const exam = await Exam.findById(examId);
  if (exam && exam.totalQuestions > 0) {
    const defaultMaxMarks = exam.maximumMarks
      ? Math.round((exam.maximumMarks / exam.totalQuestions) * 100) / 100
      : 100;
    for (let i = 1; i <= exam.totalQuestions; i++) {
      questionMap.set(i, {
        questionNumber: i,
        maximumMarks: defaultMaxMarks,
        text: `Question ${i}`,
      });
    }
  }

  return questionMap;
}

/**
 * Authoritative question mark validator and total calculator.
 * Strictly verifies against official database questions:
 * - Rejects duplicate question numbers
 * - Rejects unknown question numbers
 * - Validates marks are between 0 and maximumMarks
 * - Ensures NOT_ATTEMPTED has zero marks
 * - Rejects invalid statuses
 * - On submit, ensures every expected question is present and evaluated (no NOT_STARTED)
 * - Returns the authoritative backend-computed total
 */
export interface QuestionMarksValidationSummary {
  totalExpected: number;
  evaluatedQuestions: number;
  notAttemptedQuestions: number;
  flaggedQuestions: number;
  unansweredQuestions: number;
  missingQuestionNumbers: number[];
}

export function computeQuestionMarksSummary(
  questionMarks: IEvaluationQuestionMark[],
  authoritativeQuestions: Map<number, IAuthoritativeQuestion>
): QuestionMarksValidationSummary {
  const seenQuestions = new Set<number>();
  let evaluatedQuestions = 0;
  let notAttemptedQuestions = 0;
  let flaggedQuestions = 0;
  let unansweredQuestions = 0;
  const missingQuestionNumbers: number[] = [];

  for (const qm of questionMarks) {
    seenQuestions.add(qm.questionNumber);
    if (qm.status === 'MARKED') {
      evaluatedQuestions++;
    } else if (qm.status === 'NOT_ATTEMPTED') {
      notAttemptedQuestions++;
    } else if (qm.status === 'FLAGGED') {
      flaggedQuestions++;
    } else if (qm.status === 'NOT_STARTED') {
      unansweredQuestions++;
      if (!missingQuestionNumbers.includes(qm.questionNumber)) {
        missingQuestionNumbers.push(qm.questionNumber);
      }
    }
  }

  // Also check if any authoritative questions were not included in questionMarks at all
  if (authoritativeQuestions.size > 0) {
    for (const qNum of authoritativeQuestions.keys()) {
      if (!seenQuestions.has(qNum)) {
        unansweredQuestions++;
        if (!missingQuestionNumbers.includes(qNum)) {
          missingQuestionNumbers.push(qNum);
        }
      }
    }
  }

  const totalExpected = authoritativeQuestions.size > 0
    ? authoritativeQuestions.size
    : Math.max(questionMarks.length, 1);

  missingQuestionNumbers.sort((a, b) => a - b);

  return {
    totalExpected,
    evaluatedQuestions,
    notAttemptedQuestions,
    flaggedQuestions,
    unansweredQuestions,
    missingQuestionNumbers,
  };
}

/**
 * Validates question marks list against authoritative questions and examination rules:
 * - Determines total expected, evaluated, not-attempted, flagged, unanswered, and invalid marks
 * - Rejects duplicate question numbers
 * - Rejects unknown question numbers
 * - Rejects marks out of bounds [0, maxMarks]
 * - Rejects non-zero marks for NOT_ATTEMPTED or NOT_STARTED
 * - Rejects invalid statuses
 * - On submit, ensures every expected question is present and evaluated (no NOT_STARTED)
 * - Returns the authoritative backend-computed total and summary
 */
export function validateQuestionMarksList(
  questionMarks: IEvaluationQuestionMark[],
  authoritativeQuestions: Map<number, IAuthoritativeQuestion>,
  isSubmitting = false
): {
  validatedList: IEvaluationQuestionMark[];
  computedTotal: number;
  summary: QuestionMarksValidationSummary;
} {
  const summary = computeQuestionMarksSummary(questionMarks, authoritativeQuestions);
  const seenQuestions = new Set<number>();
  const VALID_STATUSES = ['NOT_STARTED', 'MARKED', 'FLAGGED', 'NOT_ATTEMPTED'] as const;

  for (const qm of questionMarks) {
    // 1. Check duplicate question number
    if (seenQuestions.has(qm.questionNumber)) {
      const error: any = new Error(
        `Duplicate question number detected: Q${qm.questionNumber}. Each question must only appear once.`
      );
      error.status = 400;
      error.code = 'DUPLICATE_QUESTION_NUMBER';
      throw error;
    }
    seenQuestions.add(qm.questionNumber);

    // 2. Check unknown question number
    if (authoritativeQuestions.size > 0 && !authoritativeQuestions.has(qm.questionNumber)) {
      const error: any = new Error(
        `Unknown question number: Q${qm.questionNumber}. This question is not part of the examination specifications.`
      );
      error.status = 400;
      error.code = 'UNKNOWN_QUESTION_NUMBER';
      throw error;
    }

    // 3. Check invalid status
    if (!VALID_STATUSES.includes(qm.status as any)) {
      const error: any = new Error(
        `Invalid status '${qm.status}' for question Q${qm.questionNumber}. Allowed statuses: ${VALID_STATUSES.join(', ')}.`
      );
      error.status = 400;
      error.code = 'INVALID_QUESTION_STATUS';
      throw error;
    }

    // 4. Validate marks is a number
    const marksNum = Number(qm.marks);
    if (typeof qm.marks !== 'number' || isNaN(marksNum)) {
      const error: any = new Error(
        `Invalid marks value for question Q${qm.questionNumber}: Marks must be a valid number.`
      );
      error.status = 400;
      error.code = 'INVALID_MARKS';
      throw error;
    }

    // 5. Ensure marks are not negative
    if (marksNum < 0) {
      const error: any = new Error(
        `Negative marks detected for question Q${qm.questionNumber} (${marksNum}). Marks cannot be negative.`
      );
      error.status = 400;
      error.code = 'INVALID_MARKS_NEGATIVE';
      throw error;
    }

    // 6. Ensure marks do not exceed question maximumMarks
    const officialQ = authoritativeQuestions.get(qm.questionNumber);
    if (officialQ && marksNum > officialQ.maximumMarks) {
      const error: any = new Error(
        `Question Q${qm.questionNumber} marks (${marksNum}) exceed the maximum allowed marks (${officialQ.maximumMarks}).`
      );
      error.status = 400;
      error.code = 'MARKS_EXCEED_MAXIMUM';
      throw error;
    }

    // 7. Ensure NOT_ATTEMPTED has zero marks
    if (qm.status === 'NOT_ATTEMPTED' && marksNum !== 0) {
      const error: any = new Error(
        `Question Q${qm.questionNumber} is marked as NOT_ATTEMPTED but has non-zero marks (${marksNum}). Questions not attempted must have 0 marks.`
      );
      error.status = 400;
      error.code = 'INVALID_NOT_ATTEMPTED_MARKS';
      throw error;
    }

    // 8. Ensure NOT_STARTED has zero marks
    if (qm.status === 'NOT_STARTED' && marksNum !== 0) {
      const error: any = new Error(
        `Question Q${qm.questionNumber} is marked as NOT_STARTED but has non-zero marks (${marksNum}). Questions not started must have 0 marks.`
      );
      error.status = 400;
      error.code = 'INVALID_NOT_STARTED_MARKS';
      throw error;
    }
  }

  // 9. On SUBMIT: Every expected question must have exactly one valid evaluation state
  if (isSubmitting && authoritativeQuestions.size > 0) {
    const missingKeys: number[] = [];
    for (const [qNum] of authoritativeQuestions.entries()) {
      if (!seenQuestions.has(qNum)) {
        missingKeys.push(qNum);
      }
    }
    if (missingKeys.length > 0) {
      const error: any = new Error(
        `Missing question entry: Question ${missingKeys.map(k => `Q${k}`).join(', ')} is required but missing from the submission.`
      );
      error.status = 400;
      error.code = 'MISSING_QUESTION_EVALUATION';
      error.details = { summary, missingQuestions: missingKeys };
      throw error;
    }

    // Also ensure no question remains in NOT_STARTED state upon submission
    const unstartedKeys: number[] = [];
    for (const qm of questionMarks) {
      if (qm.status === 'NOT_STARTED') {
        unstartedKeys.push(qm.questionNumber);
      }
    }
    if (unstartedKeys.length > 0) {
      const error: any = new Error(
        `Question ${unstartedKeys.map(k => `Q${k}`).join(', ')} has not been evaluated. Every question must have an explicit evaluated status (MARKED, FLAGGED, or NOT_ATTEMPTED) before submission.`
      );
      error.status = 400;
      error.code = 'QUESTION_UNMARKED';
      error.details = { summary, unstartedQuestions: unstartedKeys };
      throw error;
    }
  }

  // Authoritative total marks calculation:
  // only MARKED and FLAGGED statuses contribute marks
  const computedTotal = questionMarks
    .filter((q) => q.status === 'MARKED' || q.status === 'FLAGGED')
    .reduce((sum, q) => sum + (Number(q.marks) || 0), 0);

  return { validatedList: questionMarks, computedTotal, summary };
}

export async function fetchEvaluations(
  query: { status?: string },
  userRole: string,
  userId: string
) {
  const filter: Record<string, unknown> = {};

  // Examiners can only see their own evaluations
  if (userRole === 'EXAMINER') {
    filter.examinerId = userId;
  }

  if (query.status) {
    filter.status = query.status;
  }

  return Evaluation.find(filter)
    .populate({
      path: 'answerBookId',
      populate: { path: 'examId', select: 'title subjectCode subjectName maximumMarks' },
    })
    .populate('examinerId', 'name email')
    .sort({ createdAt: -1 });
}

export async function fetchEvaluationById(id: string, userRole: string, userId: string) {
  const evaluation = await Evaluation.findById(id)
    .populate({
      path: 'answerBookId',
      populate: { path: 'examId', select: 'title subjectCode subjectName maximumMarks totalQuestions' },
    })
    .populate('examinerId', 'name email');

  if (!evaluation) {
    const error: any = new Error('Evaluation not found');
    error.status = 404;
    error.code = 'EVALUATION_NOT_FOUND';
    throw error;
  }

  if (userRole === 'EXAMINER' && evaluation.examinerId._id?.toString() !== userId && (evaluation.examinerId as any).toString() !== userId) {
    const error: any = new Error('Access denied: Evaluation is not assigned to you');
    error.status = 403;
    error.code = 'ACCESS_DENIED';
    throw error;
  }

  return evaluation;
}

export async function beginEvaluation(id: string, examinerId: string) {
  // Support either answerBookId or evaluationId
  let answerBook = await AnswerBook.findById(id);
  let evaluation: IEvaluation | null = null;

  if (!answerBook) {
    evaluation = await Evaluation.findById(id);
    if (evaluation) {
      answerBook = await AnswerBook.findById(evaluation.answerBookId);
    }
  }

  if (!answerBook) {
    const error: any = new Error('Answer book not found');
    error.status = 404;
    error.code = 'ANSWER_BOOK_NOT_FOUND';
    throw error;
  }

  if (answerBook.assignedExaminerId?.toString() !== examinerId) {
    const error: any = new Error('You are not assigned to this answer book');
    error.status = 403;
    error.code = 'NOT_ASSIGNED';
    throw error;
  }

  if (!['ASSIGNED', 'RETURNED'].includes(answerBook.status)) {
    const error: any = new Error(
      `Cannot start evaluation for answer book with status: ${answerBook.status}. Must be ASSIGNED or RETURNED.`
    );
    error.status = 400;
    error.code = 'INVALID_STATUS';
    throw error;
  }

  // Validate state transition
  validateStateTransition(answerBook.status, 'IN_PROGRESS');

  if (!evaluation) {
    evaluation = await Evaluation.findOne({ answerBookId: answerBook._id });
  }

  if (!evaluation) {
    evaluation = await Evaluation.create({
      answerBookId: answerBook._id,
      examinerId,
      status: 'IN_PROGRESS',
      startedAt: new Date(),
    });
  } else {
    evaluation.status = 'IN_PROGRESS';
    evaluation.startedAt = evaluation.startedAt || new Date();
    await evaluation.save();
  }

  answerBook.status = 'IN_PROGRESS';
  await answerBook.save();

  await evaluation.populate({
    path: 'answerBookId',
    populate: { path: 'examId', select: 'title subjectCode subjectName maximumMarks totalQuestions' },
  });
  await evaluation.populate('examinerId', 'name email');

  await logAuditAction({
    actorId: examinerId,
    action: 'EVALUATION_STARTED',
    entityType: 'Evaluation',
    entityId: evaluation._id.toString(),
    metadata: { answerBookId: answerBook._id.toString() },
  });

  emitToAll('evaluation.started', { evaluation, answerBook });

  return { evaluation, answerBook };
}

export async function updateEvaluationMarks(
  id: string,
  data: { totalMarks?: number; remarks?: string; questionMarks?: IEvaluationQuestionMark[] },
  examinerId: string
) {
  const evaluation = await Evaluation.findById(id);
  if (!evaluation) {
    const error: any = new Error('Evaluation not found');
    error.status = 404;
    error.code = 'EVALUATION_NOT_FOUND';
    throw error;
  }

  if (
    evaluation.examinerId.toString() !== examinerId &&
    (evaluation.examinerId as any)._id?.toString() !== examinerId
  ) {
    const error: any = new Error('Access denied: You do not own this evaluation');
    error.status = 403;
    error.code = 'ACCESS_DENIED';
    throw error;
  }

  if (evaluation.status !== 'IN_PROGRESS') {
    const error: any = new Error('Can only update in-progress evaluations');
    error.status = 400;
    error.code = 'EVALUATION_NOT_IN_PROGRESS';
    throw error;
  }

  const answerBook = await AnswerBook.findById(evaluation.answerBookId);
  if (!answerBook) {
    const error: any = new Error('Associated answer book not found');
    error.status = 404;
    error.code = 'ANSWER_BOOK_NOT_FOUND';
    throw error;
  }

  const examId =
    typeof answerBook.examId === 'object' && answerBook.examId !== null && '_id' in (answerBook.examId as any)
      ? (answerBook.examId as any)._id
      : answerBook.examId;

  // 1. Fetch authoritative questions for this exam from MongoDB
  const authoritativeQuestions = await fetchAuthoritativeQuestions(examId);

  // 2. Validate and calculate authoritative total
  if (data.questionMarks && Array.isArray(data.questionMarks)) {
    const { validatedList, computedTotal } = validateQuestionMarksList(
      data.questionMarks,
      authoritativeQuestions,
      false // draft update
    );

    evaluation.questionMarks = validatedList;
    // Discard any frontend-provided data.totalMarks; authoritative calculation only
    evaluation.totalMarks = computedTotal;
  } else {
    // If only remarks were updated, recalculate total from existing question marks
    const { computedTotal } = validateQuestionMarksList(
      evaluation.questionMarks || [],
      authoritativeQuestions,
      false
    );
    evaluation.totalMarks = computedTotal;
  }

  if (data.remarks !== undefined) evaluation.remarks = data.remarks;
  await evaluation.save();

  await logAuditAction({
    actorId: examinerId,
    action: 'EVALUATION_UPDATED',
    entityType: 'Evaluation',
    entityId: evaluation._id.toString(),
    metadata: {
      totalMarks: evaluation.totalMarks,
      questionCount: evaluation.questionMarks.length,
      answerBookId: evaluation.answerBookId.toString(),
      timestamp: new Date().toISOString(),
    },
  });

  emitToAll('evaluation.updated', { evaluationId: evaluation._id });

  return evaluation;
}

export async function submitEvaluationFinal(
  id: string,
  data: { totalMarks?: number; remarks?: string; questionMarks?: IEvaluationQuestionMark[] },
  examinerId: string
) {
  const evaluation = await Evaluation.findById(id);
  if (!evaluation) {
    const error: any = new Error('Evaluation not found');
    error.status = 404;
    error.code = 'EVALUATION_NOT_FOUND';
    throw error;
  }

  if (
    evaluation.examinerId.toString() !== examinerId &&
    (evaluation.examinerId as any)._id?.toString() !== examinerId
  ) {
    const error: any = new Error('Access denied: You do not own this evaluation');
    error.status = 403;
    error.code = 'ACCESS_DENIED';
    throw error;
  }

  if (evaluation.status !== 'IN_PROGRESS') {
    const error: any = new Error('Can only submit in-progress evaluations');
    error.status = 400;
    error.code = 'EVALUATION_NOT_IN_PROGRESS';
    throw error;
  }

  const answerBook = await AnswerBook.findById(evaluation.answerBookId);
  if (!answerBook) {
    const error: any = new Error('Associated answer book not found');
    error.status = 404;
    error.code = 'ANSWER_BOOK_NOT_FOUND';
    throw error;
  }

  const examId =
    typeof answerBook.examId === 'object' && answerBook.examId !== null && '_id' in (answerBook.examId as any)
      ? (answerBook.examId as any)._id
      : answerBook.examId;

  // 1. Fetch official questions for the exam from MongoDB
  const authoritativeQuestions = await fetchAuthoritativeQuestions(examId);

  // 2. Build target question marks from submission payload or already saved state
  const targetQuestionMarks =
    data.questionMarks && Array.isArray(data.questionMarks) && data.questionMarks.length > 0
      ? data.questionMarks
      : evaluation.questionMarks;

  if (!targetQuestionMarks || targetQuestionMarks.length === 0) {
    const error: any = new Error('Cannot submit evaluation: No question marks provided or saved');
    error.status = 400;
    error.code = 'NO_QUESTION_MARKS';
    throw error;
  }

  // 3. Strict submission validation against authoritative questions:
  // - reject duplicate question numbers
  // - reject unknown question numbers
  // - reject missing required question entries
  // - validate every question against official question
  // - ensure marks between 0 and maximumMarks
  // - ensure NOT_ATTEMPTED has zero marks
  // - ensure invalid statuses are rejected
  // - every expected question must have exactly one valid evaluation state
  const { validatedList, computedTotal, summary } = validateQuestionMarksList(
    targetQuestionMarks,
    authoritativeQuestions,
    true // isSubmitting = true
  );

  // 4. Validate against examination maximumMarks if available
  const exam = await Exam.findById(examId);
  if (exam && exam.maximumMarks && computedTotal > exam.maximumMarks) {
    const error: any = new Error(
      `Total calculated marks (${computedTotal}) exceed examination maximum allowed (${exam.maximumMarks}).`
    );
    error.status = 400;
    error.code = 'TOTAL_EXCEEDS_EXAM_MAXIMUM';
    throw error;
  }

  // 5. Store ONLY the backend-calculated total
  evaluation.questionMarks = validatedList;
  evaluation.totalMarks = computedTotal;

  // Validate state transition
  validateStateTransition(answerBook.status, 'SUBMITTED');

  if (data.remarks !== undefined) evaluation.remarks = data.remarks;
  evaluation.status = 'SUBMITTED';
  evaluation.submittedAt = new Date();
  await evaluation.save();

  answerBook.status = 'SUBMITTED';
  await answerBook.save();

  await answerBook.populate('examId', 'title subjectCode subjectName');
  await evaluation.populate({
    path: 'answerBookId',
    populate: { path: 'examId', select: 'title subjectCode subjectName' },
  });
  await evaluation.populate('examinerId', 'name email');

  await logAuditAction({
    actorId: examinerId,
    action: 'EVALUATION_SUBMITTED',
    entityType: 'Evaluation',
    entityId: evaluation._id.toString(),
    metadata: {
      totalMarks: evaluation.totalMarks,
      maximumMarks: exam?.maximumMarks,
      answerBookId: evaluation.answerBookId.toString(),
      totalExpected: summary.totalExpected,
      evaluatedQuestions: summary.evaluatedQuestions,
      notAttemptedQuestions: summary.notAttemptedQuestions,
      flaggedQuestions: summary.flaggedQuestions,
      unansweredQuestions: summary.unansweredQuestions,
      questionCount: evaluation.questionMarks.length,
      timestamp: new Date().toISOString(),
    },
  });

  emitToAll('answerbook.status.changed', {
    answerBookId: answerBook._id,
    status: 'SUBMITTED',
  });
  emitToAll('evaluation.submitted', { evaluation, answerBook, summary });
  emitToRole('MODERATOR', 'evaluation.submitted', { evaluation, answerBook, summary });

  return { evaluation, answerBook, summary };
}

/**
 * Requests AI-assisted evaluation for a question.
 * Fetches authoritative data, secures media through signed delivery, invokes EvaluationAssistantService,
 * stores aiAnalysis in the evaluation model, and emits real-time socket events.
 * AI analysis remains completely separate from final examiner marks.
 */
export async function requestAISuggestionForQuestion(
  evaluationId: string,
  questionNumber: number,
  options: {
    pageNumber?: number;
    forceRefresh?: boolean;
    userRole: string;
    userId: string;
    userName?: string;
  }
) {
  // 1. Authenticate user & RBAC
  const evaluation = await Evaluation.findById(evaluationId);
  if (!evaluation) {
    const error: any = new Error('Evaluation not found');
    error.status = 404;
    error.code = 'EVALUATION_NOT_FOUND';
    throw error;
  }

  // 2. Only assigned examiner can request suggestion, unless privileged role (ADMIN, MODERATOR)
  if (options.userRole === 'EXAMINER') {
    const examinerId =
      typeof evaluation.examinerId === 'object' &&
      evaluation.examinerId !== null &&
      '_id' in (evaluation.examinerId as any)
        ? (evaluation.examinerId as any)._id.toString()
        : evaluation.examinerId.toString();

    if (examinerId !== options.userId) {
      const error: any = new Error(
        'Access denied: You are not the assigned examiner for this evaluation'
      );
      error.status = 403;
      error.code = 'UNAUTHORIZED_EXAMINER_ACCESS';
      throw error;
    }
  }

  // 3. Check for existing cached analysis to avoid redundant duplicate AI generation
  const existingIndex = evaluation.questionMarks.findIndex(
    (q) => q.questionNumber === questionNumber
  );
  const existingQm = existingIndex >= 0 ? evaluation.questionMarks[existingIndex] : null;

  if (existingQm?.aiAnalysis?.generatedAt && !options.forceRefresh) {
    return {
      cached: true,
      aiAnalysis: existingQm.aiAnalysis,
      evaluationId: evaluation._id.toString(),
      questionNumber,
    };
  }

  // 4. Fetch authoritative AnswerBook, Exam, Question, Rubric, Reference Answer
  const answerBook = await AnswerBook.findById(evaluation.answerBookId);
  if (!answerBook) {
    const error: any = new Error('Associated answer book not found');
    error.status = 404;
    error.code = 'ANSWER_BOOK_NOT_FOUND';
    throw error;
  }

  const examId =
    typeof answerBook.examId === 'object' &&
    answerBook.examId !== null &&
    '_id' in (answerBook.examId as any)
      ? (answerBook.examId as any)._id
      : answerBook.examId;

  const exam = await Exam.findById(examId);
  if (!exam) {
    const error: any = new Error('Associated exam not found');
    error.status = 404;
    error.code = 'EXAM_NOT_FOUND';
    throw error;
  }

  const question = await Question.findOne({ examId, questionNumber });
  if (!question) {
    const error: any = new Error(`Question Q${questionNumber} not found for this examination`);
    error.status = 404;
    error.code = 'QUESTION_NOT_FOUND';
    throw error;
  }

  // 5. Fetch relevant AnswerPage and secure media through existing secure media layer
  let answerPage = null;
  if (options.pageNumber) {
    answerPage = await AnswerPage.findOne({
      answerBookId: answerBook._id,
      pageNumber: options.pageNumber,
    });
  } else {
    // Look for page matching questionNumber, or page 1
    answerPage =
      (await AnswerPage.findOne({ answerBookId: answerBook._id, pageNumber: questionNumber })) ||
      (await AnswerPage.findOne({ answerBookId: answerBook._id }).sort({ pageNumber: 1 }));
  }

  let signedMediaUrl: string | undefined = undefined;
  if (answerPage?.cloudinary?.publicId) {
    // Generate secure time-limited signed URL through existing secure media layer
    const signed = generateAuthorizedMediaUrl(answerPage.cloudinary.publicId, {
      resourceType: answerPage.cloudinary.resourceType,
      deliveryType: answerPage.cloudinary.deliveryType,
      format: answerPage.cloudinary.format,
      expiresInSeconds: 3600,
    });
    signedMediaUrl = signed.secureUrl;

    // Audit media access
    await logAuditAction({
      actorId: options.userId,
      actorName: options.userName || 'Assigned Examiner',
      actorRole: options.userRole,
      action: 'MEDIA_ACCESSED_BY_AI_COPILOT',
      entityType: 'AnswerPage',
      entityId: answerPage._id.toString(),
      metadata: {
        evaluationId: evaluation._id.toString(),
        answerBookId: answerBook._id.toString(),
        pageNumber: answerPage.pageNumber,
        questionNumber,
      },
    });
  }

  // 6. Call EvaluationAssistantService
  const assistantResult = await EvaluationAssistantService.evaluateStudentAnswer({
    question: question.text,
    maximumMarks: question.maximumMarks,
    rubric: question.rubric.map((r) => ({
      criterion: r.criterion,
      marks: r.marks,
    })),
    referenceAnswer: question.referenceAnswer,
    keyConcepts: question.keyConcepts,
    gradingNotes: question.gradingNotes,
    language: question.evaluationLanguage,
    studentAnswerImage: signedMediaUrl,
    studentAnswerImageMimeType:
      answerPage?.cloudinary?.format === 'pdf' ? 'application/pdf' : 'image/jpeg',
    ocrText: answerPage?.ocr?.text,
    ocrConfidence: answerPage?.ocr?.confidence,
  });

  // 7. Store AI analysis in evaluation question data model (NEVER touching final examiner marks)
  const modelName = process.env.GEMINI_MODEL || 'gemini-1.5-flash';
  const aiAnalysisData = {
    suggestedMarks: assistantResult.suggestedMarks,
    minMarks: assistantResult.minMarks,
    maxMarks: assistantResult.maxMarks,
    confidence: assistantResult.confidence,
    needsHumanReview: assistantResult.needsHumanReview,
    criteria: assistantResult.criteria,
    missingConcepts: assistantResult.missingConcepts,
    reasoningSummary: assistantResult.reasoningSummary,
    generatedAt: new Date(),
    model: modelName,
  };

  if (existingIndex >= 0) {
    evaluation.questionMarks[existingIndex].aiAnalysis = aiAnalysisData;
  } else {
    evaluation.questionMarks.push({
      questionNumber,
      marks: 0,
      status: 'NOT_STARTED',
      aiAnalysis: aiAnalysisData,
    });
  }

  // Save evaluation (marks and totalMarks remain untouched by AI)
  await evaluation.save();

  // 8. Audit log
  await logAuditAction({
    actorId: options.userId,
    actorName: options.userName || 'Assigned Examiner',
    actorRole: options.userRole,
    action: 'EVALUATION_AI_ASSISTED',
    entityType: 'Evaluation',
    entityId: evaluation._id.toString(),
    metadata: {
      questionNumber,
      suggestedMarks: assistantResult.suggestedMarks,
      confidence: assistantResult.confidence,
      needsHumanReview: assistantResult.needsHumanReview,
      model: modelName,
      generatedAt: aiAnalysisData.generatedAt.toISOString(),
    },
  });

  // 9. Emit Socket.IO event
  emitToAll('evaluation.ai.updated', {
    evaluationId: evaluation._id.toString(),
    questionNumber,
    aiAnalysis: aiAnalysisData,
  });

  return {
    cached: false,
    aiAnalysis: aiAnalysisData,
    evaluationId: evaluation._id.toString(),
    questionNumber,
  };
}
