import mongoose from 'mongoose';
import { Result, IResult } from '../models/Result';
import { Evaluation } from '../models/Evaluation';
import { AnswerBook } from '../models/AnswerBook';
import { Exam } from '../models/Exam';
import {
  fetchAuthoritativeQuestions,
  validateQuestionMarksList,
} from './evaluations.service';
import { validateStateTransition } from './answerBooks.service';
import { logAuditAction } from './audit.service';
import { emitToAll } from '../sockets';

/**
 * Finalizes an approved evaluation into an authoritative certified examination Result.
 * Idempotent: Subsequent calls return the existing finalized result without duplicate generation.
 */
export async function finalizeEvaluationResult(
  evaluationId: string,
  actorId: string,
  actor?: { name?: string; role?: string }
): Promise<IResult> {
  // 1. Verify evaluation exists
  let evaluation = await Evaluation.findById(evaluationId);
  let answerBook = null;

  if (!evaluation) {
    // Check if the parameter passed was answerBookId
    answerBook = await AnswerBook.findById(evaluationId);
    if (answerBook) {
      evaluation = await Evaluation.findOne({ answerBookId: answerBook._id });
    }
  }

  if (!evaluation) {
    const error: any = new Error('Evaluation not found');
    error.status = 404;
    error.code = 'EVALUATION_NOT_FOUND';
    throw error;
  }

  // 2. Verify answer book exists
  if (!answerBook) {
    answerBook = await AnswerBook.findById(evaluation.answerBookId);
  }

  if (!answerBook) {
    const error: any = new Error('Associated answer book not found');
    error.status = 404;
    error.code = 'ANSWER_BOOK_NOT_FOUND';
    throw error;
  }

  // 3. Verify evaluation belongs to answer book
  if (evaluation.answerBookId.toString() !== answerBook._id.toString()) {
    const error: any = new Error(
      `Evaluation mismatch: Evaluation belongs to answer book ${evaluation.answerBookId}, not ${answerBook._id}.`
    );
    error.status = 400;
    error.code = 'EVALUATION_ANSWER_BOOK_MISMATCH';
    throw error;
  }

  // 4. Idempotency check: if Result already exists for this answerBook or evaluation, return it immediately
  const existingResult = await Result.findOne({
    $or: [{ answerBookId: answerBook._id }, { evaluationId: evaluation._id }],
  })
    .populate('examId', 'title subjectCode subjectName maximumMarks academicSession')
    .populate('answerBookId', 'answerBookCode studentCode pageCount status')
    .populate('evaluationId', 'totalMarks questionMarks status remarks')
    .populate('examinerId', 'name email')
    .populate('finalizedBy', 'name email');

  if (existingResult) {
    if (answerBook.status !== 'FINALIZED') {
      answerBook.status = 'FINALIZED';
      await answerBook.save();
    }
    return existingResult;
  }

  // 5. Verify statuses: Both must be APPROVED before final result certification
  if (evaluation.status !== 'APPROVED') {
    const error: any = new Error(
      `Cannot finalize result: Evaluation status is '${evaluation.status}'. Must be 'APPROVED'.`
    );
    error.status = 400;
    error.code = 'INVALID_EVALUATION_STATUS';
    throw error;
  }

  if (answerBook.status !== 'APPROVED') {
    const error: any = new Error(
      `Cannot finalize result: Answer book status is '${answerBook.status}'. Must be 'APPROVED'.`
    );
    error.status = 400;
    error.code = 'INVALID_ANSWER_BOOK_STATUS';
    throw error;
  }

  // 6. Fetch official questions from MongoDB and strictly validate every question
  const examId =
    typeof answerBook.examId === 'object' && answerBook.examId !== null && '_id' in (answerBook.examId as any)
      ? (answerBook.examId as any)._id
      : answerBook.examId;

  const authoritativeQuestions = await fetchAuthoritativeQuestions(examId);

  if (!evaluation.questionMarks || evaluation.questionMarks.length === 0) {
    const error: any = new Error('Cannot finalize result: Evaluation has no question marks recorded.');
    error.status = 400;
    error.code = 'NO_QUESTION_MARKS';
    throw error;
  }

  // Authoritative validation of all question marks on submit/finalization
  const { validatedList, computedTotal } = validateQuestionMarksList(
    evaluation.questionMarks,
    authoritativeQuestions,
    true // isSubmitting = true (all questions must be evaluated and valid)
  );

  // Verify that recorded total marks matches the computed sum of question marks
  if (
    typeof evaluation.totalMarks === 'number' &&
    Math.abs(evaluation.totalMarks - computedTotal) > 0.001
  ) {
    const error: any = new Error(
      `Evaluation total marks (${evaluation.totalMarks}) does not equal the computed sum of question marks (${computedTotal}).`
    );
    error.status = 400;
    error.code = 'TOTAL_MARKS_MISMATCH';
    throw error;
  }

  // 7. Verify exam maximum marks
  const exam = await Exam.findById(examId);
  if (!exam) {
    const error: any = new Error('Associated examination specification not found');
    error.status = 404;
    error.code = 'EXAM_NOT_FOUND';
    throw error;
  }

  const examMaximumMarks =
    exam.maximumMarks ||
    (authoritativeQuestions.size > 0
      ? Array.from(authoritativeQuestions.values()).reduce((sum, q) => sum + q.maximumMarks, 0)
      : 100);

  if (examMaximumMarks <= 0) {
    const error: any = new Error('Invalid examination specification: Maximum marks must be greater than 0.');
    error.status = 400;
    error.code = 'INVALID_EXAM_MAXIMUM_MARKS';
    throw error;
  }

  if (computedTotal > examMaximumMarks) {
    const error: any = new Error(
      `Total calculated marks (${computedTotal}) exceed examination maximum allowed (${examMaximumMarks}).`
    );
    error.status = 400;
    error.code = 'TOTAL_EXCEEDS_EXAM_MAXIMUM';
    throw error;
  }

  const percentage =
    examMaximumMarks > 0
      ? Math.round((computedTotal / examMaximumMarks) * 10000) / 100
      : 0;

  // 8. Update evaluation totalMarks with authoritative calculation
  evaluation.questionMarks = validatedList;
  evaluation.totalMarks = computedTotal;
  await evaluation.save();

  // 9. Idempotently create or update Result
  const result = await Result.findOneAndUpdate(
    { answerBookId: answerBook._id },
    {
      $set: {
        examId: answerBook.examId,
        answerBookId: answerBook._id,
        evaluationId: evaluation._id,
        examinerId: evaluation.examinerId,
        totalMarks: computedTotal,
        maximumMarks: examMaximumMarks,
        percentage,
        status: 'FINALIZED',
        finalizedAt: new Date(),
        finalizedBy: new mongoose.Types.ObjectId(actorId),
      },
    },
    { upsert: true, new: true, setDefaultsOnInsert: true }
  );

  // 10. Transition AnswerBook -> FINALIZED
  validateStateTransition(answerBook.status, 'FINALIZED');
  answerBook.status = 'FINALIZED';
  await answerBook.save();

  // 11. Populate result references for return
  await result.populate('examId', 'title subjectCode subjectName maximumMarks academicSession');
  await result.populate('answerBookId', 'answerBookCode studentCode pageCount status');
  await result.populate('evaluationId', 'totalMarks questionMarks status remarks');
  await result.populate('examinerId', 'name email');
  await result.populate('finalizedBy', 'name email');

  // 12. Create AuditLog
  await logAuditAction({
    actorId,
    actorName: actor?.name || 'Academic Administrator',
    actorRole: actor?.role || 'ADMIN',
    action: 'RESULT_FINALIZED',
    entityType: 'Result',
    entityId: result._id.toString(),
    metadata: {
      examId: answerBook.examId.toString(),
      answerBookId: answerBook._id.toString(),
      answerBookCode: answerBook.answerBookCode,
      studentCode: answerBook.studentCode,
      evaluationId: evaluation._id.toString(),
      totalMarks: computedTotal,
      maximumMarks: examMaximumMarks,
      percentage,
      timestamp: new Date().toISOString(),
    },
  });

  // 13. Emit real-time Socket.IO events
  emitToAll('result.finalized', { result, answerBook, evaluation });
  emitToAll('result.updated', { result });
  emitToAll('answerbook.status.changed', { answerBook });

  return result;
}

/**
 * Fetches certified examination results with optional exam and status filters.
 */
export async function fetchResults(query: { examId?: string; status?: string }) {
  const filter: Record<string, unknown> = {};
  if (query.examId) filter.examId = query.examId;
  if (query.status) filter.status = query.status;

  return Result.find(filter)
    .populate('examId', 'title subjectCode subjectName maximumMarks academicSession')
    .populate('answerBookId', 'answerBookCode studentCode pageCount status')
    .populate('evaluationId', 'totalMarks questionMarks status remarks')
    .populate('examinerId', 'name email')
    .populate('finalizedBy', 'name email')
    .sort({ finalizedAt: -1 });
}

/**
 * Fetches certified results for a specific examination.
 */
export async function fetchResultsForExam(examId: string) {
  return Result.find({ examId })
    .populate('examId', 'title subjectCode subjectName maximumMarks academicSession')
    .populate('answerBookId', 'answerBookCode studentCode pageCount status')
    .populate('evaluationId', 'totalMarks questionMarks status remarks')
    .populate('examinerId', 'name email')
    .populate('finalizedBy', 'name email')
    .sort({ finalizedAt: -1 });
}

/**
 * Fetches a single certified result by its ID.
 */
export async function fetchResultById(id: string) {
  const result = await Result.findById(id)
    .populate('examId', 'title subjectCode subjectName maximumMarks academicSession')
    .populate('answerBookId', 'answerBookCode studentCode pageCount status')
    .populate('evaluationId', 'totalMarks questionMarks status remarks')
    .populate('examinerId', 'name email')
    .populate('finalizedBy', 'name email');

  if (!result) {
    const error: any = new Error('Result record not found');
    error.status = 404;
    error.code = 'RESULT_NOT_FOUND';
    throw error;
  }

  return result;
}
