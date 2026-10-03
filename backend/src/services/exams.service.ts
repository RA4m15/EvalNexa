import { Exam, IExam } from '../models/Exam';
import { AnswerBook } from '../models/AnswerBook';
import { logAuditAction } from './audit.service';
import { emitToAll } from '../sockets';

export async function fetchExams(filter: Record<string, unknown> = {}): Promise<IExam[]> {
  return Exam.find(filter)
    .populate('createdBy', 'name email')
    .sort({ createdAt: -1 });
}

export async function fetchExamById(id: string): Promise<IExam | null> {
  return Exam.findById(id).populate('createdBy', 'name email');
}

export async function createNewExam(data: Partial<IExam>, actorId: string): Promise<IExam> {
  const exam = await Exam.create({
    ...data,
    createdBy: actorId,
  });

  await exam.populate('createdBy', 'name email');

  await logAuditAction({
    actorId,
    action: 'EXAM_CREATED',
    entityType: 'Exam',
    entityId: exam._id.toString(),
    metadata: {
      title: exam.title,
      subjectCode: exam.subjectCode,
    },
  });

  emitToAll('exam.created', { exam });

  return exam;
}

export async function updateExistingExam(
  id: string,
  data: Partial<IExam>,
  actorId: string
): Promise<IExam | null> {
  const exam = await Exam.findByIdAndUpdate(id, data, {
    new: true,
    runValidators: true,
  }).populate('createdBy', 'name email');

  if (!exam) return null;

  await logAuditAction({
    actorId,
    action: 'EXAM_UPDATED',
    entityType: 'Exam',
    entityId: exam._id.toString(),
    metadata: data as Record<string, unknown>,
  });

  emitToAll('exam.updated', { exam });

  return exam;
}

export async function deleteExistingExam(id: string, actorId: string): Promise<boolean> {
  const answerBookCount = await AnswerBook.countDocuments({ examId: id });
  if (answerBookCount > 0) {
    const error: any = new Error(
      `Cannot delete exam with ${answerBookCount} registered answer books`
    );
    error.status = 400;
    error.code = 'EXAM_HAS_ANSWER_BOOKS';
    throw error;
  }

  const exam = await Exam.findByIdAndDelete(id);
  if (!exam) return false;

  await logAuditAction({
    actorId,
    action: 'EXAM_DELETED',
    entityType: 'Exam',
    entityId: id,
    metadata: { title: exam.title, subjectCode: exam.subjectCode },
  });

  return true;
}

export async function fetchAdminDashboardStats() {
  const [totalExams, totalAnswerBooks, statusCounts] = await Promise.all([
    Exam.countDocuments(),
    AnswerBook.countDocuments(),
    AnswerBook.aggregate([{ $group: { _id: '$status', count: { $sum: 1 } } }]),
  ]);

  const byStatus: Record<string, number> = {
    ready: 0,
    assigned: 0,
    inProgress: 0,
    submitted: 0,
    underReview: 0,
    approved: 0,
    returned: 0,
    finalized: 0,
  };

  statusCounts.forEach(({ _id, count }: { _id: string; count: number }) => {
    switch (_id) {
      case 'READY': byStatus.ready = count; break;
      case 'ASSIGNED': byStatus.assigned = count; break;
      case 'IN_PROGRESS': byStatus.inProgress = count; break;
      case 'SUBMITTED': byStatus.submitted = count; break;
      case 'UNDER_REVIEW': byStatus.underReview = count; break;
      case 'APPROVED': byStatus.approved = count; break;
      case 'RETURNED': byStatus.returned = count; break;
      case 'FINALIZED': byStatus.finalized = count; break;
    }
  });

  return { totalExams, totalAnswerBooks, byStatus };
}
