import { AuditLog } from '../models/AuditLog';

interface CreateAuditLogParams {
  actorId: string;
  action: string;
  entityType: string;
  entityId: string;
  metadata?: Record<string, unknown>;
}

export async function createAuditLog(params: CreateAuditLogParams): Promise<void> {
  try {
    await AuditLog.create(params);
  } catch (error) {
    // Audit log failures should not break the main flow
    console.error('[AuditLog] Failed to create audit log:', error);
  }
}
