import { AnswerBook, IAnswerBook } from '../models/AnswerBook';
import { Evaluation } from '../models/Evaluation';
import { User } from '../models/User';
import { AnswerBookStatus } from '@evalnexa/types';
import { logAuditAction } from './audit.service';
import { emitToAll, emitToUser } from '../sockets';

const VALID_TRANSITIONS: Record<AnswerBookStatus, AnswerBookStatus[]> = {
  READY: ['ASSIGNED'],
  ASSIGNED: ['IN_PROGRESS'],
  IN_PROGRESS: ['SUBMITTED'],
  SUBMITTED: ['UNDER_REVIEW', 'APPROVED', 'RETURNED'],
  UNDER_REVIEW: ['APPROVED', 'RETURNED'],
  RETURNED: ['ASSIGNED', 'IN_PROGRESS'],
  APPROVED: ['FINALIZED'],
  FINALIZED: [],
};

export function validateStateTransition(
  currentStatus: AnswerBookStatus,
  nextStatus: AnswerBookStatus
): void {
  if (currentStatus === nextStatus) return;

  const allowed = VALID_TRANSITIONS[currentStatus] || [];
  if (!allowed.includes(nextStatus)) {
    const error: any = new Error(
      `Invalid state transition: Cannot transition from '${currentStatus}' to '${nextStatus}'. Allowed transitions: ${allowed.join(', ') || 'None'}`
    );
    error.status = 400;
    error.code = 'INVALID_STATE_TRANSITION';
    throw error;
  }
}

export async function fetchAnswerBooks(
  query: { examId?: string; status?: string },
  userRole: string,
  userId: string
) {
  const filter: Record<string, unknown> = {};
  if (query.examId) filter.examId = query.examId;
  if (query.status) filter.status = query.status;

  // Examiner can only see answer books assigned to themselves
  if (userRole === 'EXAMINER') {
    filter.assignedExaminerId = userId;
  }

  return AnswerBook.find(filter)
    .populate('examId', 'title subjectCode subjectName maximumMarks')
    .populate('assignedExaminerId', 'name email')
    .sort({ createdAt: -1 });
}

export async function fetchExaminerAnswerBooks(userId: string, status?: string) {
  const filter: Record<string, unknown> = { assignedExaminerId: userId };
  if (status) filter.status = status;

  const answerBooks = await AnswerBook.find(filter)
    .populate('examId', 'title subjectCode subjectName maximumMarks')
    .sort({ createdAt: -1 });

  const stats = {
    assigned: 0,
    inProgress: 0,
    submitted: 0,
  };

  answerBooks.forEach((ab) => {
    if (ab.status === 'ASSIGNED') stats.assigned++;
    if (ab.status === 'IN_PROGRESS') stats.inProgress++;
    if (['SUBMITTED', 'UNDER_REVIEW', 'APPROVED'].includes(ab.status)) stats.submitted++;
  });

  return { answerBooks, stats };
}

export async function fetchAnswerBookById(id: string, userRole: string, userId: string) {
  const answerBook = await AnswerBook.findById(id)
    .populate('examId', 'title subjectCode subjectName maximumMarks totalQuestions')
    .populate('assignedExaminerId', 'name email');

  if (!answerBook) {
    const error: any = new Error('Answer book not found');
    error.status = 404;
    error.code = 'ANSWER_BOOK_NOT_FOUND';
    throw error;
  }

  if (
    userRole === 'EXAMINER' &&
    answerBook.assignedExaminerId?.toString() !== userId
  ) {
    const error: any = new Error('Access denied: Answer book is not assigned to you');
    error.status = 403;
    error.code = 'ACCESS_DENIED';
    throw error;
  }

  const evaluation = await Evaluation.findOne({ answerBookId: answerBook._id });

  return { answerBook, evaluation };
}

export async function createNewAnswerBook(
  data: {
    examId: string;
    answerBookCode: string;
    studentCode: string;
    pageCount?: number;
  },
  actorId: string
): Promise<IAnswerBook> {
  const existing = await AnswerBook.findOne({
    answerBookCode: data.answerBookCode.toUpperCase(),
  });

  if (existing) {
    const error: any = new Error('Answer book code already exists');
    error.status = 409;
    error.code = 'ANSWER_BOOK_CODE_EXISTS';
    throw error;
  }

  const answerBook = await AnswerBook.create({
    ...data,
    answerBookCode: data.answerBookCode.toUpperCase(),
    status: 'READY',
  });

  await answerBook.populate('examId', 'title subjectCode subjectName');

  await logAuditAction({
    actorId,
    action: 'ANSWER_BOOK_CREATED',
    entityType: 'AnswerBook',
    entityId: answerBook._id.toString(),
    metadata: {
      code: answerBook.answerBookCode,
      examId: answerBook.examId,
    },
  });

  emitToAll('answerbook.created', { answerBook });

  return answerBook;
}

export async function assignAnswerBookToExaminer(
  answerBookId: string,
  examinerId: string,
  actorId: string
): Promise<IAnswerBook> {
  const examiner = await User.findOne({
    _id: examinerId,
    role: 'EXAMINER',
    isActive: true,
  });

  if (!examiner) {
    const error: any = new Error('Active examiner not found');
    error.status = 404;
    error.code = 'EXAMINER_NOT_FOUND';
    throw error;
  }

  const answerBook = await AnswerBook.findById(answerBookId);
  if (!answerBook) {
    const error: any = new Error('Answer book not found');
    error.status = 404;
    error.code = 'ANSWER_BOOK_NOT_FOUND';
    throw error;
  }

  if (!['READY', 'RETURNED'].includes(answerBook.status)) {
    const error: any = new Error(
      `Cannot assign an answer book with status: ${answerBook.status}. Must be READY or RETURNED.`
    );
    error.status = 400;
    error.code = 'INVALID_STATUS_FOR_ASSIGNMENT';
    throw error;
  }

  answerBook.assignedExaminerId = examiner._id;
  answerBook.status = 'ASSIGNED';
  await answerBook.save();

  await answerBook.populate('examId', 'title subjectCode subjectName');
  await answerBook.populate('assignedExaminerId', 'name email');

  await logAuditAction({
    actorId,
    action: 'ANSWER_BOOK_ASSIGNED',
    entityType: 'AnswerBook',
    entityId: answerBook._id.toString(),
    metadata: { examinerId, examinerName: examiner.name },
  });

  emitToAll('answerbook.assigned', { answerBook });
  emitToUser(examinerId, 'answerbook.assigned', { answerBook });

  return answerBook;
}

export async function updateExistingAnswerBook(
  id: string,
  data: Partial<IAnswerBook>,
  actorId: string
): Promise<IAnswerBook | null> {
  const current = await AnswerBook.findById(id);
  if (!current) return null;

  if (data.status && data.status !== current.status) {
    validateStateTransition(current.status, data.status);
  }

  const answerBook = await AnswerBook.findByIdAndUpdate(id, data, {
    new: true,
    runValidators: true,
  })
    .populate('examId', 'title subjectCode subjectName')
    .populate('assignedExaminerId', 'name email');

  if (answerBook) {
    await logAuditAction({
      actorId,
      action: 'ANSWER_BOOK_UPDATED',
      entityType: 'AnswerBook',
      entityId: answerBook._id.toString(),
      metadata: data as Record<string, unknown>,
    });

    emitToAll('answerbook.status.changed', { answerBook });
  }

  return answerBook;
}
