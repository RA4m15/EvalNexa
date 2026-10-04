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
 * Pure institutional grading helper converting authoritative percentage to grade,
 * grade points, and formal degree classification.
 */
export function calculateGradeAndClassification(percentage: number): {
  grade: string;
  gradePoint: number;
  classification: string;
} {
  const rounded = Math.round(percentage * 100) / 100;
  if (rounded >= 90) {
    return { grade: 'A+', gradePoint: 10, classification: 'FIRST_CLASS_DISTINCTION' };
  }
  if (rounded >= 80) {
    return { grade: 'A', gradePoint: 9, classification: 'FIRST_CLASS_DISTINCTION' };
  }
  if (rounded >= 70) {
    return { grade: 'B+', gradePoint: 8, classification: 'FIRST_CLASS' };
  }
  if (rounded >= 60) {
    return { grade: 'B', gradePoint: 7, classification: 'HIGHER_SECOND_CLASS' };
  }
  if (rounded >= 50) {
    return { grade: 'C', gradePoint: 6, classification: 'SECOND_CLASS' };
  }
  if (rounded >= 40) {
    return { grade: 'P', gradePoint: 4, classification: 'PASS' };
  }
  return { grade: 'F', gradePoint: 0, classification: 'FAIL' };
}

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
    .populate('finalizedBy', 'name email')
    .populate('publishedBy', 'name email');

  if (existingResult) {
    if (answerBook.status !== 'FINALIZED') {
      answerBook.status = 'FINALIZED';
      await answerBook.save();
    }
    // Backfill grade calculation if missing on legacy records
    if (!existingResult.grade && typeof existingResult.percentage === 'number') {
      const { grade, gradePoint, classification } = calculateGradeAndClassification(existingResult.percentage);
      existingResult.grade = grade;
      existingResult.gradePoint = gradePoint;
      existingResult.classification = classification;
      await existingResult.save();
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

  const { grade, gradePoint, classification } = calculateGradeAndClassification(percentage);

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
        grade,
        gradePoint,
        classification,
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
  await result.populate('publishedBy', 'name email');

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
      grade,
      gradePoint,
      classification,
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
 * Publishes a finalized Result to make it officially accessible on the institutional ledger.
 */
export async function publishResult(
  resultId: string,
  actorId: string,
  actor?: { name?: string; role?: string }
): Promise<IResult> {
  const result = await Result.findById(resultId);

  if (!result) {
    const error: any = new Error('Result record not found');
    error.status = 404;
    error.code = 'RESULT_NOT_FOUND';
    throw error;
  }

  result.status = 'PUBLISHED';
  result.publishedAt = new Date();
  result.publishedBy = new mongoose.Types.ObjectId(actorId);
  result.withheldReason = undefined;

  await result.save();

  await result.populate('examId', 'title subjectCode subjectName maximumMarks academicSession');
  await result.populate('answerBookId', 'answerBookCode studentCode pageCount status');
  await result.populate('evaluationId', 'totalMarks questionMarks status remarks');
  await result.populate('examinerId', 'name email');
  await result.populate('finalizedBy', 'name email');
  await result.populate('publishedBy', 'name email');

  await logAuditAction({
    actorId,
    actorName: actor?.name || 'Academic Administrator',
    actorRole: actor?.role || 'ADMIN',
    action: 'RESULT_PUBLISHED',
    entityType: 'Result',
    entityId: result._id.toString(),
    metadata: {
      resultId: result._id.toString(),
      totalMarks: result.totalMarks,
      percentage: result.percentage,
      grade: result.grade,
      timestamp: new Date().toISOString(),
    },
  });

  emitToAll('result.published', { result });
  emitToAll('result.updated', { result });

  return result;
}

/**
 * Publishes all finalized Results for a given examination in a single batch operation.
 */
export async function publishResultsForExam(
  examId: string,
  actorId: string,
  actor?: { name?: string; role?: string }
): Promise<{ success: boolean; publishedCount: number; message: string }> {
  const exam = await Exam.findById(examId);
  if (!exam) {
    const error: any = new Error('Examination not found');
    error.status = 404;
    error.code = 'EXAM_NOT_FOUND';
    throw error;
  }

  const now = new Date();
  const actorObjectId = new mongoose.Types.ObjectId(actorId);

  const updateResult = await Result.updateMany(
    { examId: exam._id, status: 'FINALIZED' },
    {
      $set: {
        status: 'PUBLISHED',
        publishedAt: now,
        publishedBy: actorObjectId,
      },
    }
  );

  const publishedCount = updateResult.modifiedCount;

  await logAuditAction({
    actorId,
    actorName: actor?.name || 'Academic Administrator',
    actorRole: actor?.role || 'ADMIN',
    action: 'EXAM_RESULTS_PUBLISHED',
    entityType: 'Exam',
    entityId: examId,
    metadata: {
      examId,
      publishedCount,
      timestamp: now.toISOString(),
    },
  });

  emitToAll('result.published', { examId, publishedCount });

  return {
    success: true,
    publishedCount,
    message: `Successfully published ${publishedCount} examination result(s).`,
  };
}

/**
 * Flags a result as WITHHELD with an authoritative audit rationale.
 */
export async function withholdResult(
  resultId: string,
  reason: string,
  actorId: string,
  actor?: { name?: string; role?: string }
): Promise<IResult> {
  if (!reason || !reason.trim()) {
    const error: any = new Error('A valid reason is required to withhold an examination result.');
    error.status = 400;
    error.code = 'MISSING_WITHHOLD_REASON';
    throw error;
  }

  const result = await Result.findById(resultId);
  if (!result) {
    const error: any = new Error('Result record not found');
    error.status = 404;
    error.code = 'RESULT_NOT_FOUND';
    throw error;
  }

  result.status = 'WITHHELD';
  result.withheldReason = reason.trim();
  await result.save();

  await result.populate('examId', 'title subjectCode subjectName maximumMarks academicSession');
  await result.populate('answerBookId', 'answerBookCode studentCode pageCount status');
  await result.populate('evaluationId', 'totalMarks questionMarks status remarks');
  await result.populate('examinerId', 'name email');
  await result.populate('finalizedBy', 'name email');
  await result.populate('publishedBy', 'name email');

  await logAuditAction({
    actorId,
    actorName: actor?.name || 'Academic Administrator',
    actorRole: actor?.role || 'ADMIN',
    action: 'RESULT_WITHHELD',
    entityType: 'Result',
    entityId: result._id.toString(),
    metadata: {
      resultId: result._id.toString(),
      reason: reason.trim(),
      timestamp: new Date().toISOString(),
    },
  });

  emitToAll('result.withheld', { result, reason: reason.trim() });
  emitToAll('result.updated', { result });

  return result;
}

/**
 * Releases a withheld result back to FINALIZED or PUBLISHED status.
 */
export async function releaseWithheldResult(
  resultId: string,
  actorId: string,
  actor?: { name?: string; role?: string }
): Promise<IResult> {
  const result = await Result.findById(resultId);
  if (!result) {
    const error: any = new Error('Result record not found');
    error.status = 404;
    error.code = 'RESULT_NOT_FOUND';
    throw error;
  }

  if (result.status !== 'WITHHELD') {
    return result;
  }

  // Restore to PUBLISHED if it was published prior to withholding, else FINALIZED
  result.status = result.publishedAt ? 'PUBLISHED' : 'FINALIZED';
  result.withheldReason = undefined;
  await result.save();

  await result.populate('examId', 'title subjectCode subjectName maximumMarks academicSession');
  await result.populate('answerBookId', 'answerBookCode studentCode pageCount status');
  await result.populate('evaluationId', 'totalMarks questionMarks status remarks');
  await result.populate('examinerId', 'name email');
  await result.populate('finalizedBy', 'name email');
  await result.populate('publishedBy', 'name email');

  await logAuditAction({
    actorId,
    actorName: actor?.name || 'Academic Administrator',
    actorRole: actor?.role || 'ADMIN',
    action: 'RESULT_RELEASED',
    entityType: 'Result',
    entityId: result._id.toString(),
    metadata: {
      resultId: result._id.toString(),
      restoredStatus: result.status,
      timestamp: new Date().toISOString(),
    },
  });

  emitToAll('result.updated', { result });

  return result;
}

/**
 * Batch finalizes all APPROVED evaluations for an examination in one coordinated pass.
 */
export async function batchFinalizeApprovedEvaluations(
  examId: string,
  actorId: string,
  actor?: { name?: string; role?: string }
): Promise<{
  success: boolean;
  finalizedCount: number;
  totalApproved: number;
  errors: Array<{ evaluationId: string; error: string }>;
}> {
  const exam = await Exam.findById(examId);
  if (!exam) {
    const error: any = new Error('Examination not found');
    error.status = 404;
    error.code = 'EXAM_NOT_FOUND';
    throw error;
  }

  // Find all answer books for this exam that are APPROVED
  const approvedBooks = await AnswerBook.find({ examId, status: 'APPROVED' });
  const bookIds = approvedBooks.map((b) => b._id);

  // Find all evaluations for these approved books that are also APPROVED
  const approvedEvals = await Evaluation.find({
    answerBookId: { $in: bookIds },
    status: 'APPROVED',
  });

  const errors: Array<{ evaluationId: string; error: string }> = [];
  let finalizedCount = 0;

  for (const evalDoc of approvedEvals) {
    try {
      await finalizeEvaluationResult(evalDoc._id.toString(), actorId, actor);
      finalizedCount++;
    } catch (err: any) {
      errors.push({
        evaluationId: evalDoc._id.toString(),
        error: err.message || 'Finalization failed',
      });
    }
  }

  await logAuditAction({
    actorId,
    actorName: actor?.name || 'Academic Administrator',
    actorRole: actor?.role || 'ADMIN',
    action: 'BATCH_FINALIZATION_COMPLETED',
    entityType: 'Exam',
    entityId: examId,
    metadata: {
      examId,
      finalizedCount,
      totalApproved: approvedEvals.length,
      errorsCount: errors.length,
      timestamp: new Date().toISOString(),
    },
  });

  return {
    success: true,
    finalizedCount,
    totalApproved: approvedEvals.length,
    errors,
  };
}

/**
 * Fetches certified examination results with optional exam and status filters.
 */
export async function fetchResults(query: { examId?: string; status?: string }) {
  const filter: Record<string, unknown> = {};
  if (query.examId) filter.examId = query.examId;
  if (query.status && query.status !== 'ALL') filter.status = query.status;

  return Result.find(filter)
    .populate('examId', 'title subjectCode subjectName maximumMarks academicSession')
    .populate('answerBookId', 'answerBookCode studentCode pageCount status')
    .populate('evaluationId', 'totalMarks questionMarks status remarks')
    .populate('examinerId', 'name email')
    .populate('finalizedBy', 'name email')
    .populate('publishedBy', 'name email')
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
    .populate('publishedBy', 'name email')
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
    .populate('finalizedBy', 'name email')
    .populate('publishedBy', 'name email');

  if (!result) {
    const error: any = new Error('Result record not found');
    error.status = 404;
    error.code = 'RESULT_NOT_FOUND';
    throw error;
  }

  return result;
}
