import { Response } from 'express';
import { AuthRequest } from '../middleware/auth';
import * as auditService from '../services/audit.service';

export async function getAuditLogs(req: AuthRequest, res: Response): Promise<void> {
  try {
    const page = parseInt(req.query.page as string) || 1;
    const limit = parseInt(req.query.limit as string) || 50;

    const filter: Record<string, unknown> = {};
    if (req.query.entityType) filter.entityType = req.query.entityType;
    if (req.query.entityId) filter.entityId = req.query.entityId;
    if (req.query.actorId) filter.actorId = req.query.actorId;

    const { logs, pagination } = await auditService.fetchAuditLogs(filter, page, limit);

    res.json({
      success: true,
      data: logs,
      pagination,
    });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch audit logs',
      code: error.code || 'FETCH_AUDIT_LOGS_ERROR',
    });
  }
}
