import mongoose, { Document, Schema } from 'mongoose';
import { AnswerBookStatus } from '@evalnexa/types';

export interface IAnswerBook extends Document {
  _id: mongoose.Types.ObjectId;
  examId: mongoose.Types.ObjectId;
  answerBookCode: string;
  studentCode: string;
  pageCount: number;
  status: AnswerBookStatus;
  qualityStatus: 'READY' | 'PROCESSING' | 'QUALITY_REVIEW' | 'RESCAN_REQUIRED' | 'VERIFIED';
  scanBatch?: string;
  pdfUrl?: string;
  assignedExaminerId?: mongoose.Types.ObjectId;
  createdAt: Date;
  updatedAt: Date;
}

const AnswerBookSchema = new Schema<IAnswerBook>(
  {
    examId: { type: Schema.Types.ObjectId, ref: 'Exam', required: true },
    answerBookCode: {
      type: String,
      required: true,
      unique: true,
      trim: true,
      uppercase: true,
    },
    studentCode: { type: String, required: true, trim: true, uppercase: true },
    pageCount: { type: Number, required: true, min: 1, default: 1 },
    status: {
      type: String,
      enum: [
        'READY',
        'ASSIGNED',
        'IN_PROGRESS',
        'SUBMITTED',
        'UNDER_REVIEW',
        'APPROVED',
        'RETURNED',
        'FINALIZED',
      ],
      default: 'READY',
    },
    qualityStatus: {
      type: String,
      enum: ['READY', 'PROCESSING', 'QUALITY_REVIEW', 'RESCAN_REQUIRED', 'VERIFIED'],
      default: 'READY',
    },
    scanBatch: { type: String, trim: true },
    pdfUrl: { type: String, trim: true },
    assignedExaminerId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      default: null,
    },
  },
  { timestamps: true }
);

export const AnswerBook = mongoose.model<IAnswerBook>('AnswerBook', AnswerBookSchema);
