import { AuditLog, IAuditLog } from '../models/AuditLog';

export interface CreateAuditLogParams {
  actorId: string | object;
  action: string;
  entityType: string;
  entityId: string;
  metadata?: Record<string, unknown>;
}

export async function logAuditAction(params: CreateAuditLogParams): Promise<IAuditLog | null> {
  try {
    return await AuditLog.create(params);
  } catch (error) {
    console.error('[AuditService] Failed to create audit log:', error);
    return null;
  }
}

export async function fetchAuditLogs(
  filter: Record<string, unknown>,
  page = 1,
  limit = 50
) {
  const skip = (page - 1) * limit;

  const [logs, total] = await Promise.all([
    AuditLog.find(filter)
      .populate('actorId', 'name email role')
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(limit),
    AuditLog.countDocuments(filter),
  ]);

  return {
    logs,
    pagination: {
      total,
      page,
      limit,
      totalPages: Math.ceil(total / limit),
    },
  };
}
