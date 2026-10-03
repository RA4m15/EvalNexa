import bcrypt from 'bcryptjs';
import { User, IUser } from '../models/User';
import { logAuditAction } from './audit.service';
import { emitToAll } from '../sockets';

export async function fetchUsers(filter: Record<string, unknown> = {}): Promise<IUser[]> {
  return User.find(filter).sort({ createdAt: -1 });
}

export async function fetchUserById(id: string): Promise<IUser | null> {
  return User.findById(id);
}

export async function createNewUser(
  data: {
    name: string;
    email: string;
    password: string;
    role: 'ADMIN' | 'EXAMINER' | 'MODERATOR';
    institutionId?: string;
  },
  actorId: string
): Promise<IUser> {
  const existing = await User.findOne({ email: data.email.toLowerCase() });
  if (existing) {
    const error: any = new Error('A user with this email already exists');
    error.status = 409;
    error.code = 'EMAIL_ALREADY_EXISTS';
    throw error;
  }

  const salt = await bcrypt.genSalt(10);
  const passwordHash = await bcrypt.hash(data.password, salt);

  const user = await User.create({
    name: data.name,
    email: data.email.toLowerCase(),
    passwordHash,
    role: data.role,
    institutionId: data.institutionId,
    isActive: true,
  });

  await logAuditAction({
    actorId,
    action: 'USER_CREATED',
    entityType: 'User',
    entityId: user._id.toString(),
    metadata: { email: user.email, role: user.role },
  });

  emitToAll('user.created', {
    user: {
      _id: user._id,
      name: user.name,
      email: user.email,
      role: user.role,
      isActive: user.isActive,
    },
  });

  return user;
}

export async function updateExistingUser(
  id: string,
  data: Partial<IUser>,
  actorId: string
): Promise<IUser | null> {
  const user = await User.findByIdAndUpdate(id, data, {
    new: true,
    runValidators: true,
  });

  if (user) {
    await logAuditAction({
      actorId,
      action: 'USER_UPDATED',
      entityType: 'User',
      entityId: user._id.toString(),
      metadata: data as Record<string, unknown>,
    });
  }

  return user;
}

export async function fetchActiveExaminers(): Promise<IUser[]> {
  return User.find({ role: 'EXAMINER', isActive: true })
    .select('_id name email')
    .sort({ name: 1 });
}
