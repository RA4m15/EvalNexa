import mongoose from 'mongoose';
import { Evaluation, IEvaluation, IEvaluationQuestionMark } from '../models/Evaluation';
import { AnswerBook } from '../models/AnswerBook';
import { Question } from '../models/Question';
import { Exam } from '../models/Exam';
import { validateStateTransition } from './answerBooks.service';
import { logAuditAction } from './audit.service';
import { emitToAll, emitToRole } from '../sockets';

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
export function validateQuestionMarksList(
  questionMarks: IEvaluationQuestionMark[],
  authoritativeQuestions: Map<number, IAuthoritativeQuestion>,
  isSubmitting = false
): { validatedList: IEvaluationQuestionMark[]; computedTotal: number } {
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
    for (const [qNum] of authoritativeQuestions.entries()) {
      if (!seenQuestions.has(qNum)) {
        const error: any = new Error(
          `Missing question entry: Question Q${qNum} is required but missing from the submission.`
        );
        error.status = 400;
        error.code = 'MISSING_QUESTION_EVALUATION';
        throw error;
      }
    }

    // Also ensure no question remains in NOT_STARTED state upon submission
    for (const qm of questionMarks) {
      if (qm.status === 'NOT_STARTED') {
        const error: any = new Error(
          `Question Q${qm.questionNumber} has not been evaluated. Every question must have an explicit evaluated status (MARKED, FLAGGED, or NOT_ATTEMPTED) before submission.`
        );
        error.status = 400;
        error.code = 'QUESTION_UNMARKED';
        throw error;
      }
    }
  }

  // Authoritative total marks calculation:
  // only MARKED and FLAGGED statuses contribute marks
  const computedTotal = questionMarks
    .filter((q) => q.status === 'MARKED' || q.status === 'FLAGGED')
    .reduce((sum, q) => sum + (Number(q.marks) || 0), 0);

  return { validatedList: questionMarks, computedTotal };
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
  const { validatedList, computedTotal } = validateQuestionMarksList(
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
      answerBookId: evaluation.answerBookId.toString(),
      questionCount: evaluation.questionMarks.length,
      timestamp: new Date().toISOString(),
    },
  });

  emitToAll('evaluation.submitted', { evaluation, answerBook });
  emitToRole('MODERATOR', 'evaluation.submitted', { evaluation, answerBook });

  return { evaluation, answerBook };
}
