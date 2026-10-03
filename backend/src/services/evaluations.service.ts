import { Evaluation, IEvaluation, IEvaluationQuestionMark } from '../models/Evaluation';
import { AnswerBook } from '../models/AnswerBook';
import { Question } from '../models/Question';
import { validateStateTransition } from './answerBooks.service';
import { logAuditAction } from './audit.service';
import { emitToAll, emitToRole } from '../sockets';

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

  if (evaluation.examinerId.toString() !== examinerId) {
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

  if (data.questionMarks && Array.isArray(data.questionMarks)) {
    evaluation.questionMarks = data.questionMarks;
    const computedTotal = data.questionMarks
      .filter((q) => q.status === 'MARKED' || q.status === 'FLAGGED')
      .reduce((sum, q) => sum + (Number(q.marks) || 0), 0);
    evaluation.totalMarks = data.totalMarks !== undefined ? data.totalMarks : computedTotal;
  } else if (data.totalMarks !== undefined) {
    evaluation.totalMarks = data.totalMarks;
  }

  if (data.remarks !== undefined) evaluation.remarks = data.remarks;
  await evaluation.save();

  await logAuditAction({
    actorId: examinerId,
    action: 'EVALUATION_UPDATED',
    entityType: 'Evaluation',
    entityId: evaluation._id.toString(),
    metadata: { totalMarks: evaluation.totalMarks },
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

  if (evaluation.examinerId.toString() !== examinerId) {
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

  // If question marks provided with submission, save them first
  if (data.questionMarks && Array.isArray(data.questionMarks)) {
    evaluation.questionMarks = data.questionMarks;
  }

  // Deterministic validation rules:
  const examQuestions = await Question.find({ examId: answerBook.examId });

  if (examQuestions.length > 0) {
    const marksMap = new Map<number, IEvaluationQuestionMark>();
    (evaluation.questionMarks || []).forEach((qm) => {
      marksMap.set(qm.questionNumber, qm);
    });

    for (const q of examQuestions) {
      const qMark = marksMap.get(q.questionNumber);
      if (!qMark || qMark.status === 'NOT_STARTED') {
        const error: any = new Error(
          `Question Q${q.questionNumber} has not been evaluated. Every question must have an explicit status before submission.`
        );
        error.status = 400;
        error.code = 'QUESTION_UNMARKED';
        throw error;
      }

      if (qMark.marks < 0) {
        const error: any = new Error(
          `Question Q${q.questionNumber} has negative marks (${qMark.marks}). Marks cannot be negative.`
        );
        error.status = 400;
        error.code = 'INVALID_MARKS_NEGATIVE';
        throw error;
      }

      if (qMark.marks > q.maximumMarks) {
        const error: any = new Error(
          `Question Q${q.questionNumber} score (${qMark.marks}) exceeds the maximum allowed marks (${q.maximumMarks}).`
        );
        error.status = 400;
        error.code = 'MARKS_EXCEED_MAXIMUM';
        throw error;
      }
    }

    // Auto-calculate total marks from questions
    const computedTotal = (evaluation.questionMarks || [])
      .filter((q) => q.status === 'MARKED' || q.status === 'FLAGGED')
      .reduce((sum, q) => sum + (Number(q.marks) || 0), 0);

    evaluation.totalMarks = computedTotal;
  } else if (data.totalMarks !== undefined) {
    evaluation.totalMarks = data.totalMarks;
  }

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
    },
  });

  emitToAll('evaluation.submitted', { evaluation, answerBook });
  emitToRole('MODERATOR', 'evaluation.submitted', { evaluation, answerBook });

  return { evaluation, answerBook };
}
