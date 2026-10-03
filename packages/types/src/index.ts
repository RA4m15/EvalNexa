// ============================================================
// EVALNEXA SHARED TYPE DEFINITIONS
// ============================================================

// --- Roles ---
export type UserRole = 'ADMIN' | 'EXAMINER' | 'MODERATOR';

// --- User ---
export interface User {
  _id: string;
  name: string;
  email: string;
  role: UserRole;
  institutionId?: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

// --- Exam Status ---
export type ExamStatus =
  | 'DRAFT'
  | 'READY'
  | 'EVALUATION_OPEN'
  | 'EVALUATION_CLOSED'
  | 'MODERATION'
  | 'FINALIZED';

// --- Exam ---
export interface Exam {
  _id: string;
  title: string;
  subjectCode: string;
  subjectName: string;
  academicSession: string;
  maximumMarks: number;
  totalQuestions: number;
  status: ExamStatus;
  createdBy: string | User;
  createdAt: string;
  updatedAt: string;
}

// --- Answer Book Status ---
export type AnswerBookStatus =
  | 'READY'
  | 'ASSIGNED'
  | 'IN_PROGRESS'
  | 'SUBMITTED'
  | 'UNDER_REVIEW'
  | 'APPROVED'
  | 'RETURNED'
  | 'FINALIZED';

export type QualityStatus =
  | 'READY'
  | 'PROCESSING'
  | 'QUALITY_REVIEW'
  | 'RESCAN_REQUIRED'
  | 'VERIFIED';

// --- Answer Book ---
export interface AnswerBook {
  _id: string;
  examId: string | Exam;
  answerBookCode: string;
  studentCode: string;
  pageCount: number;
  status: AnswerBookStatus;
  qualityStatus?: QualityStatus;
  scanBatch?: string;
  pdfUrl?: string;
  assignedExaminerId?: string | User;
  createdAt: string;
  updatedAt: string;
}

// --- Evaluation Status ---
export type EvaluationStatus =
  | 'NOT_STARTED'
  | 'IN_PROGRESS'
  | 'SUBMITTED'
  | 'UNDER_REVIEW'
  | 'APPROVED'
  | 'RETURNED';

// --- Question Marking Status ---
export type QuestionMarkStatus = 'NOT_STARTED' | 'MARKED' | 'FLAGGED' | 'NOT_ATTEMPTED';

export interface QuestionMarkItem {
  questionNumber: number;
  marks: number;
  status: QuestionMarkStatus;
  comment?: string;
}

// --- Evaluation ---
export interface Evaluation {
  _id: string;
  answerBookId: string | AnswerBook;
  examinerId: string | User;
  status: EvaluationStatus;
  totalMarks?: number;
  remarks?: string;
  questionMarks?: QuestionMarkItem[];
  startedAt?: string;
  submittedAt?: string;
  createdAt: string;
  updatedAt: string;
}

// --- Question ---
export interface QuestionRubricItem {
  criterion: string;
  marks: number;
}

export interface Question {
  _id: string;
  examId: string | Exam;
  questionNumber: number;
  text: string;
  maximumMarks: number;
  rubric: QuestionRubricItem[];
  createdAt: string;
  updatedAt: string;
}

// --- Moderation ---
export interface Moderation {
  _id: string;
  evaluationId: string | Evaluation;
  moderatorId: string | User;
  status: 'UNDER_REVIEW' | 'APPROVED' | 'RETURNED';
  decision: 'APPROVE' | 'RETURN';
  reason?: string;
  createdAt: string;
  updatedAt: string;
}

// --- Audit Log ---
export interface AuditLog {
  _id: string;
  actorId: string | User;
  action: string;
  entityType: string;
  entityId: string;
  metadata?: Record<string, unknown>;
  createdAt: string;
}

// --- API Response Wrappers ---
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  pagination: {
    total: number;
    page: number;
    limit: number;
    totalPages: number;
  };
}

export interface ApiError {
  success: false;
  message: string;
  errors?: Record<string, string[]>;
}

// --- Dashboard Stats ---
export interface AdminDashboardStats {
  totalExams: number;
  totalAnswerBooks: number;
  byStatus: {
    ready: number;
    assigned: number;
    inProgress: number;
    submitted: number;
    underReview: number;
    approved: number;
    returned: number;
    finalized: number;
  };
}

export interface ExaminerDashboardStats {
  assigned: number;
  inProgress: number;
  submitted: number;
}

export interface ModeratorDashboardStats {
  submitted: number;
  underReview: number;
  approved: number;
  returned: number;
}

export interface IntegrityIssue {
  id: string;
  ruleName: string;
  severity: 'HIGH' | 'MEDIUM' | 'LOW';
  answerBookCode: string;
  examCode: string;
  examinerName: string;
  description: string;
  timestamp: string;
}

export interface ExaminerAnalyticsItem {
  examinerId: string;
  name: string;
  email: string;
  isActive: boolean;
  assigned: number;
  completed: number;
  returned: number;
  flags: number;
  averageMarks: number;
  averageEvaluationTimeMinutes: number;
}

// --- Socket.IO Events ---
export type SocketEvent =
  | 'exam.created'
  | 'exam.updated'
  | 'answerbook.created'
  | 'answerbook.assigned'
  | 'answerbook.status.changed'
  | 'evaluation.started'
  | 'evaluation.updated'
  | 'evaluation.submitted'
  | 'moderation.approved'
  | 'moderation.returned'
  | 'user.created';

export interface SocketEventPayload {
  event: SocketEvent;
  data: Record<string, unknown>;
  timestamp: string;
}
