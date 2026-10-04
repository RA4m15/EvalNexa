import mongoose, { Document, Schema } from 'mongoose';
import { ResultStatus } from '@evalnexa/types';

export interface IResult extends Document {
  _id: mongoose.Types.ObjectId;
  examId: mongoose.Types.ObjectId;
  answerBookId: mongoose.Types.ObjectId;
  evaluationId: mongoose.Types.ObjectId;
  examinerId: mongoose.Types.ObjectId;
  totalMarks: number;
  maximumMarks: number;
  percentage: number;
  grade?: string;
  gradePoint?: number;
  classification?: string;
  status: ResultStatus;
  finalizedAt: Date;
  finalizedBy: mongoose.Types.ObjectId;
  publishedAt?: Date;
  publishedBy?: mongoose.Types.ObjectId;
  withheldReason?: string;
  createdAt: Date;
  updatedAt: Date;
}

const ResultSchema = new Schema<IResult>(
  {
    examId: {
      type: Schema.Types.ObjectId,
      ref: 'Exam',
      required: true,
      index: true,
    },
    answerBookId: {
      type: Schema.Types.ObjectId,
      ref: 'AnswerBook',
      required: true,
      unique: true, // Guarantees one result per answer book (idempotency)
      index: true,
    },
    evaluationId: {
      type: Schema.Types.ObjectId,
      ref: 'Evaluation',
      required: true,
      unique: true, // Guarantees one result per evaluation
      index: true,
    },
    examinerId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
      index: true,
    },
    totalMarks: {
      type: Number,
      required: true,
      min: 0,
    },
    maximumMarks: {
      type: Number,
      required: true,
      min: 1,
    },
    percentage: {
      type: Number,
      required: true,
      min: 0,
      max: 100,
    },
    grade: {
      type: String,
      trim: true,
      uppercase: true,
    },
    gradePoint: {
      type: Number,
      min: 0,
      max: 10,
    },
    classification: {
      type: String,
      trim: true,
    },
    status: {
      type: String,
      enum: ['FINALIZED', 'PUBLISHED', 'WITHHELD'],
      default: 'FINALIZED',
      index: true,
    },
    finalizedAt: {
      type: Date,
      required: true,
      default: Date.now,
    },
    finalizedBy: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    publishedAt: {
      type: Date,
    },
    publishedBy: {
      type: Schema.Types.ObjectId,
      ref: 'User',
    },
    withheldReason: {
      type: String,
      trim: true,
    },
  },
  { timestamps: true }
);

export const Result = mongoose.model<IResult>('Result', ResultSchema);
