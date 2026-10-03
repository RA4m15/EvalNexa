import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { User, IUser } from '../models/User';
import { config } from '../config';
import { logAuditAction } from './audit.service';

export interface LoginResult {
  token: string;
  user: {
    _id: string;
    name: string;
    email: string;
    role: string;
    institutionId?: string;
    isActive: boolean;
  };
}

export async function authenticateUser(email: string, password: string): Promise<LoginResult> {
  const user = await User.findOne({ email: email.toLowerCase() }).select('+passwordHash');
  if (!user) {
    const error: any = new Error('Invalid credentials');
    error.status = 401;
    error.code = 'INVALID_CREDENTIALS';
    throw error;
  }

  if (!user.isActive) {
    const error: any = new Error('Account is deactivated');
    error.status = 403;
    error.code = 'ACCOUNT_DEACTIVATED';
    throw error;
  }

  const isMatch = await bcrypt.compare(password, user.passwordHash);
  if (!isMatch) {
    const error: any = new Error('Invalid credentials');
    error.status = 401;
    error.code = 'INVALID_CREDENTIALS';
    throw error;
  }

  const token = jwt.sign(
    { userId: user._id.toString(), role: user.role },
    config.jwtSecret,
    { expiresIn: config.jwtExpiresIn as jwt.SignOptions['expiresIn'] }
  );

  await logAuditAction({
    actorId: user._id.toString(),
    action: 'USER_LOGIN',
    entityType: 'User',
    entityId: user._id.toString(),
    metadata: { email: user.email },
  });

  return {
    token,
    user: {
      _id: user._id.toString(),
      name: user.name,
      email: user.email,
      role: user.role,
      institutionId: user.institutionId,
      isActive: user.isActive,
    },
  };
}

export async function getUserProfile(userId: string): Promise<IUser | null> {
  return User.findById(userId);
}
