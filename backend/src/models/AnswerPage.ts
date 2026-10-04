import mongoose, { Document, Schema } from 'mongoose';
import { ProcessingStatus, QualityStatus } from '@evalnexa/types';

export interface IAnswerPage extends Document {
  _id: mongoose.Types.ObjectId;
  answerBookId: mongoose.Types.ObjectId;
  pageNumber: number;
  cloudinary: {
    publicId: string;
    assetId?: string;
    resourceType: string;
    deliveryType?: string;
    format?: string;
    bytes?: number;
    width?: number;
    height?: number;
    secureUrl?: string;
  };
  ocr?: {
    text?: string;
    confidence?: number | null;
    language?: string;
  };
  quality?: {
    status: QualityStatus;
    score?: number | null;
    reviewedAt?: Date;
    reviewedBy?: string;
  };
  processingStatus: ProcessingStatus;
  finalized: boolean;
  createdAt: Date;
  updatedAt: Date;
}

const AnswerPageSchema = new Schema<IAnswerPage>(
  {
    answerBookId: {
      type: Schema.Types.ObjectId,
      ref: 'AnswerBook',
      required: true,
      index: true,
    },
    pageNumber: {
      type: Number,
      required: true,
      min: 1,
    },
    cloudinary: {
      publicId: { type: String, required: true, trim: true },
      assetId: { type: String, trim: true },
      resourceType: { type: String, default: 'image', trim: true },
      deliveryType: { type: String, default: 'upload', trim: true },
      format: { type: String, trim: true },
      bytes: { type: Number },
      width: { type: Number },
      height: { type: Number },
      secureUrl: { type: String, trim: true },
    },
    ocr: {
      text: { type: String, default: '' },
      confidence: { type: Number, default: null },
      language: { type: String, default: 'en' },
    },
    quality: {
      status: {
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
      score: { type: Number, default: null },
      reviewedAt: { type: Date },
      reviewedBy: { type: String },
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
        'COMPLETED',
        'ERROR',
      ],
      default: 'RECEIVED',
    },
    finalized: {
      type: Boolean,
      default: false,
    },
  },
  { timestamps: true }
);

// Unique compound index: answerBookId + pageNumber so duplicate pages cannot exist
AnswerPageSchema.index({ answerBookId: 1, pageNumber: 1 }, { unique: true });

export const AnswerPage = mongoose.model<IAnswerPage>('AnswerPage', AnswerPageSchema);
