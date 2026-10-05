import mongoose, { Document, Schema } from 'mongoose';
import { EvaluationStatus } from '@evalnexa/types';

export interface IEvaluationQuestionAiAnalysis {
  suggestedMarks: number;
  minMarks: number;
  maxMarks: number;
  confidence: number;
  needsHumanReview: boolean;
  criteria: Array<{
    name: string;
    maxMarks: number;
    awardedMarks: number;
    evidence: string;
  }>;
  missingConcepts: string[];
  reasoningSummary: string;
  generatedAt: Date;
  model: string;
}

export interface IEvaluationQuestionMark {
  questionNumber: number;
  marks: number;
  status: 'NOT_STARTED' | 'MARKED' | 'FLAGGED' | 'NOT_ATTEMPTED';
  comment?: string;
  aiAnalysis?: IEvaluationQuestionAiAnalysis;
}

export interface IEvaluation extends Document {
  _id: mongoose.Types.ObjectId;
  answerBookId: mongoose.Types.ObjectId;
  examinerId: mongoose.Types.ObjectId;
  status: EvaluationStatus;
  totalMarks?: number;
  remarks?: string;
  questionMarks: IEvaluationQuestionMark[];
  startedAt?: Date;
  submittedAt?: Date;
  createdAt: Date;
  updatedAt: Date;
}

const EvaluationSchema = new Schema<IEvaluation>(
  {
    answerBookId: {
      type: Schema.Types.ObjectId,
      ref: 'AnswerBook',
      required: true,
    },
    examinerId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    status: {
      type: String,
      enum: [
        'NOT_STARTED',
        'IN_PROGRESS',
        'SUBMITTED',
        'UNDER_REVIEW',
        'APPROVED',
        'RETURNED',
      ],
      default: 'NOT_STARTED',
    },
    totalMarks: { type: Number, min: 0, default: 0 },
    remarks: { type: String, trim: true },
    questionMarks: [
      {
        questionNumber: { type: Number, required: true },
        marks: { type: Number, required: true, default: 0, min: 0 },
        status: {
          type: String,
          enum: ['NOT_STARTED', 'MARKED', 'FLAGGED', 'NOT_ATTEMPTED'],
          default: 'NOT_STARTED',
        },
        comment: { type: String, trim: true },
        aiAnalysis: {
          type: new Schema(
            {
              suggestedMarks: { type: Number },
              minMarks: { type: Number },
              maxMarks: { type: Number },
              confidence: { type: Number },
              needsHumanReview: { type: Boolean },
              criteria: [
                {
                  name: { type: String },
                  maxMarks: { type: Number },
                  awardedMarks: { type: Number },
                  evidence: { type: String },
                },
              ],
              missingConcepts: { type: [String], default: undefined },
              reasoningSummary: { type: String },
              generatedAt: { type: Date },
              model: { type: String },
            },
            { _id: false }
          ),
          default: undefined,
        },
      },
    ],
    startedAt: { type: Date },
    submittedAt: { type: Date },
  },
  { timestamps: true }
);

// Authoritative totalMarks calculation: always recalculate from questionMarks
EvaluationSchema.pre('validate', function (next) {
  if (this.questionMarks && Array.isArray(this.questionMarks)) {
    this.totalMarks = this.questionMarks
      .filter((q) => q.status === 'MARKED' || q.status === 'FLAGGED')
      .reduce((sum, q) => sum + (Number(q.marks) || 0), 0);
  }
  next();
});

export const Evaluation = mongoose.model<IEvaluation>('Evaluation', EvaluationSchema);
