import { z } from 'zod';

export const loginSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z.string().min(1, 'Password is required'),
});

export const createUserSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters'),
  email: z.string().email('Invalid email address'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  role: z.enum(['ADMIN', 'EXAMINER', 'MODERATOR']),
  institutionId: z.string().optional(),
});

export const updateUserSchema = z.object({
  name: z.string().min(2).optional(),
  institutionId: z.string().optional(),
  isActive: z.boolean().optional(),
  role: z.enum(['ADMIN', 'EXAMINER', 'MODERATOR']).optional(),
});

export const createExamSchema = z.object({
  title: z.string().min(3, 'Title must be at least 3 characters'),
  subjectCode: z.string().min(2, 'Subject code is required'),
  subjectName: z.string().min(2, 'Subject name is required'),
  academicSession: z.string().min(4, 'Academic session is required'),
  maximumMarks: z.number().int().positive('Maximum marks must be a positive integer'),
  totalQuestions: z.number().int().positive('Total questions must be a positive integer'),
});

export const updateExamSchema = z.object({
  title: z.string().min(3).optional(),
  subjectCode: z.string().min(2).optional(),
  subjectName: z.string().min(2).optional(),
  academicSession: z.string().min(4).optional(),
  maximumMarks: z.number().int().positive().optional(),
  totalQuestions: z.number().int().positive().optional(),
  status: z
    .enum(['DRAFT', 'READY', 'EVALUATION_OPEN', 'EVALUATION_CLOSED', 'MODERATION', 'FINALIZED'])
    .optional(),
});

export const createAnswerBookSchema = z.object({
  examId: z.string().min(1, 'Exam ID is required'),
  answerBookCode: z.string().min(2, 'Answer book code is required'),
  studentCode: z.string().min(2, 'Student code is required'),
  pageCount: z.number().int().positive().default(1),
  scanBatch: z.string().optional(),
  qualityStatus: z
    .enum(['READY', 'PROCESSING', 'QUALITY_REVIEW', 'RESCAN_REQUIRED', 'VERIFIED'])
    .optional(),
  pdfUrl: z.string().optional(),
});

export const assignAnswerBookSchema = z.object({
  examinerId: z.string().min(1, 'Examiner ID is required'),
});

export const questionMarkSchema = z.object({
  questionNumber: z.number().int().positive(),
  marks: z.number().min(0),
  status: z.enum(['NOT_STARTED', 'MARKED', 'FLAGGED', 'NOT_ATTEMPTED']),
  comment: z.string().optional(),
});

export const updateEvaluationSchema = z.object({
  totalMarks: z.number().min(0).optional(),
  remarks: z.string().optional(),
  questionMarks: z.array(questionMarkSchema).optional(),
});

export const submitEvaluationSchema = z.object({
  totalMarks: z.number().min(0).optional(),
  remarks: z.string().optional(),
  questionMarks: z.array(questionMarkSchema).optional(),
});

export const returnEvaluationSchema = z.object({
  reason: z.string().min(5, 'Please provide a reason of at least 5 characters'),
});

export const createQuestionSchema = z.object({
  questionNumber: z.number().int().positive('Question number must be a positive integer'),
  text: z.string().min(3, 'Question text must be at least 3 characters'),
  maximumMarks: z.number().positive('Maximum marks must be positive'),
  rubric: z
    .array(
      z.object({
        criterion: z.string().min(1, 'Criterion cannot be empty'),
        marks: z.number().min(0, 'Marks cannot be negative'),
      })
    )
    .optional()
    .default([]),
});

export const updateQuestionSchema = z.object({
  questionNumber: z.number().int().positive().optional(),
  text: z.string().min(3).optional(),
  maximumMarks: z.number().positive().optional(),
  rubric: z
    .array(
      z.object({
        criterion: z.string().min(1),
        marks: z.number().min(0),
      })
    )
    .optional(),
});
