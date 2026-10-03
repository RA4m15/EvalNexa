import mongoose, { Document, Schema } from 'mongoose';

export interface IModeration extends Document {
  _id: mongoose.Types.ObjectId;
  evaluationId: mongoose.Types.ObjectId;
  moderatorId: mongoose.Types.ObjectId;
  status: 'UNDER_REVIEW' | 'APPROVED' | 'RETURNED';
  decision: 'APPROVE' | 'RETURN';
  reason?: string;
  createdAt: Date;
  updatedAt: Date;
}

const ModerationSchema = new Schema<IModeration>(
  {
    evaluationId: {
      type: Schema.Types.ObjectId,
      ref: 'Evaluation',
      required: true,
      index: true,
    },
    moderatorId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
      index: true,
    },
    status: {
      type: String,
      enum: ['UNDER_REVIEW', 'APPROVED', 'RETURNED'],
      required: true,
    },
    decision: {
      type: String,
      enum: ['APPROVE', 'RETURN'],
      required: true,
    },
    reason: {
      type: String,
      trim: true,
    },
  },
  { timestamps: true }
);

export const Moderation = mongoose.model<IModeration>('Moderation', ModerationSchema);
