import { Question, IQuestion, IQuestionRubricItem } from '../models/Question';
import { Exam } from '../models/Exam';
import { logAuditAction } from './audit.service';
import { emitToExam } from '../sockets';

export async function fetchQuestionsByExam(examId: string): Promise<IQuestion[]> {
  const exam = await Exam.findById(examId);
  if (!exam) {
    const error: any = new Error('Exam not found');
    error.status = 404;
    error.code = 'EXAM_NOT_FOUND';
    throw error;
  }

  return Question.find({ examId }).sort({ questionNumber: 1 });
}

export async function fetchQuestionById(id: string): Promise<IQuestion | null> {
  return Question.findById(id).populate('examId', 'title subjectCode');
}

export async function createNewQuestion(
  examId: string,
  data: {
    questionNumber: number;
    text: string;
    maximumMarks: number;
    rubric?: IQuestionRubricItem[];
  },
  actorId: string
): Promise<IQuestion> {
  const exam = await Exam.findById(examId);
  if (!exam) {
    const error: any = new Error('Exam not found');
    error.status = 404;
    error.code = 'EXAM_NOT_FOUND';
    throw error;
  }

  const existing = await Question.findOne({ examId, questionNumber: data.questionNumber });
  if (existing) {
    const error: any = new Error(
      `Question number ${data.questionNumber} already exists for this exam`
    );
    error.status = 409;
    error.code = 'QUESTION_NUMBER_EXISTS';
    throw error;
  }

  const question = await Question.create({
    examId,
    questionNumber: data.questionNumber,
    text: data.text,
    maximumMarks: data.maximumMarks,
    rubric: data.rubric || [],
  });

  await logAuditAction({
    actorId,
    action: 'QUESTION_CREATED',
    entityType: 'Question',
    entityId: question._id.toString(),
    metadata: {
      examId,
      questionNumber: question.questionNumber,
      maximumMarks: question.maximumMarks,
    },
  });

  emitToExam(examId, 'question.created', { question });

  return question;
}

export async function updateExistingQuestion(
  id: string,
  data: Partial<IQuestion>,
  actorId: string
): Promise<IQuestion | null> {
  const question = await Question.findByIdAndUpdate(id, data, {
    new: true,
    runValidators: true,
  });

  if (!question) return null;

  await logAuditAction({
    actorId,
    action: 'QUESTION_UPDATED',
    entityType: 'Question',
    entityId: question._id.toString(),
    metadata: data as Record<string, unknown>,
  });

  emitToExam(question.examId.toString(), 'question.updated', { question });

  return question;
}

export async function deleteExistingQuestion(id: string, actorId: string): Promise<boolean> {
  const question = await Question.findByIdAndDelete(id);
  if (!question) return false;

  await logAuditAction({
    actorId,
    action: 'QUESTION_DELETED',
    entityType: 'Question',
    entityId: id,
    metadata: {
      examId: question.examId.toString(),
      questionNumber: question.questionNumber,
    },
  });

  return true;
}
