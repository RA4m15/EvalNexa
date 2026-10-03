import mongoose, { Document, Schema } from 'mongoose';
import { UserRole } from '@evalnexa/types';

export interface IUser extends Document {
  _id: mongoose.Types.ObjectId;
  name: string;
  email: string;
  passwordHash: string;
  role: UserRole;
  institutionId?: string;
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}

const UserSchema = new Schema<IUser>(
  {
    name: { type: String, required: true, trim: true },
    email: {
      type: String,
      required: true,
      unique: true,
      lowercase: true,
      trim: true,
    },
    passwordHash: { type: String, required: true, select: false },
    role: {
      type: String,
      enum: ['ADMIN', 'EXAMINER', 'MODERATOR'],
      required: true,
    },
    institutionId: { type: String, trim: true },
    isActive: { type: Boolean, default: true },
  },
  { timestamps: true }
);

// Never expose passwordHash in API responses
UserSchema.methods.toJSON = function () {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const obj: any = this.toObject();
  delete obj.passwordHash;
  return obj;
};

export const User = mongoose.model<IUser>('User', UserSchema);
