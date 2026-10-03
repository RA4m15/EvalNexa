import mongoose, { Document, Schema } from 'mongoose';
import { AnswerBookStatus, ProcessingStatus, QualityStatus } from '@evalnexa/types';

export interface IAnswerBook extends Document {
  _id: mongoose.Types.ObjectId;
  examId: mongoose.Types.ObjectId;
  answerBookCode: string;
  studentCode: string;
  pageCount: number;
  status: AnswerBookStatus;
  processingStatus: ProcessingStatus;
  qualityStatus: QualityStatus;
  scanBatch?: string;
  pdfUrl?: string;
  cloudinaryAsset?: {
    publicId: string;
    assetId?: string;
    resourceType?: string;
    format?: string;
    bytes?: number;
    secureUrl?: string;
  };
  assignedExaminerId?: mongoose.Types.ObjectId;
  createdAt: Date;
  updatedAt: Date;
}

const AnswerBookSchema = new Schema<IAnswerBook>(
  {
    examId: { type: Schema.Types.ObjectId, ref: 'Exam', required: true, index: true },
    answerBookCode: {
      type: String,
      required: true,
      unique: true,
      trim: true,
      uppercase: true,
      index: true,
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
      index: true,
    },
    processingStatus: {
      type: String,
      enum: [
        'RECEIVED',
        'PROCESSING',
        'QUALITY_REVIEW',
        'RESCAN_REQUIRED',
        'OCR_PROCESSING',
        'FINALIZING',
        'FINALIZED',
        'READY_FOR_EVALUATION',
        'ERROR',
      ],
      default: 'RECEIVED',
      index: true,
    },
    qualityStatus: {
      type: String,
      enum: [
        'PENDING',
        'PASSED',
        'REVIEW_REQUIRED',
        'RESCAN_REQUIRED',
        'VERIFIED',
        'READY',
        'PROCESSING',
        'QUALITY_REVIEW',
      ],
      default: 'PENDING',
    },
    scanBatch: { type: String, trim: true },
    pdfUrl: { type: String, trim: true },
    cloudinaryAsset: {
      publicId: { type: String, trim: true },
      assetId: { type: String, trim: true },
      resourceType: { type: String, trim: true },
      format: { type: String, trim: true },
      bytes: { type: Number },
      secureUrl: { type: String, trim: true },
    },
    assignedExaminerId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      default: null,
      index: true,
    },
  },
  { timestamps: true }
);

export const AnswerBook = mongoose.model<IAnswerBook>('AnswerBook', AnswerBookSchema);
