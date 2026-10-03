import mongoose, { Document, Schema } from 'mongoose';
import { ExamStatus } from '@evalnexa/types';

export interface IExam extends Document {
  _id: mongoose.Types.ObjectId;
  title: string;
  subjectCode: string;
  subjectName: string;
  academicSession: string;
  maximumMarks: number;
  totalQuestions: number;
  status: ExamStatus;
  createdBy: mongoose.Types.ObjectId;
  createdAt: Date;
  updatedAt: Date;
}

const ExamSchema = new Schema<IExam>(
  {
    title: { type: String, required: true, trim: true },
    subjectCode: { type: String, required: true, trim: true, uppercase: true },
    subjectName: { type: String, required: true, trim: true },
    academicSession: { type: String, required: true, trim: true },
    maximumMarks: { type: Number, required: true, min: 1 },
    totalQuestions: { type: Number, required: true, min: 1 },
    status: {
      type: String,
      enum: [
        'DRAFT',
        'READY',
        'EVALUATION_OPEN',
        'EVALUATION_CLOSED',
        'MODERATION',
        'FINALIZED',
      ],
      default: 'DRAFT',
    },
    createdBy: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
  },
  { timestamps: true }
);

export const Exam = mongoose.model<IExam>('Exam', ExamSchema);
