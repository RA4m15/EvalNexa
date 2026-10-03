import mongoose, { Document, Schema } from 'mongoose';

export interface IQuestionRubricItem {
  criterion: string;
  marks: number;
}

export interface IQuestion extends Document {
  _id: mongoose.Types.ObjectId;
  examId: mongoose.Types.ObjectId;
  questionNumber: number;
  text: string;
  maximumMarks: number;
  rubric: IQuestionRubricItem[];
  createdAt: Date;
  updatedAt: Date;
}

const RubricItemSchema = new Schema<IQuestionRubricItem>(
  {
    criterion: { type: String, required: true, trim: true },
    marks: { type: Number, required: true, min: 0 },
  },
  { _id: false }
);

const QuestionSchema = new Schema<IQuestion>(
  {
    examId: {
      type: Schema.Types.ObjectId,
      ref: 'Exam',
      required: true,
      index: true,
    },
    questionNumber: {
      type: Number,
      required: true,
      min: 1,
    },
    text: {
      type: String,
      required: true,
      trim: true,
    },
    maximumMarks: {
      type: Number,
      required: true,
      min: 0.5,
    },
    rubric: {
      type: [RubricItemSchema],
      default: [],
    },
  },
  { timestamps: true }
);

// Enforce unique question number per exam
QuestionSchema.index({ examId: 1, questionNumber: 1 }, { unique: true });

export const Question = mongoose.model<IQuestion>('Question', QuestionSchema);
