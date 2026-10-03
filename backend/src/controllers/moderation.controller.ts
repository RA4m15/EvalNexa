import { Response } from 'express';
import { AuthRequest } from '../middleware/auth';
import * as moderationService from '../services/moderation.service';

export async function getModerationQueue(req: AuthRequest, res: Response): Promise<void> {
  try {
    const queue = await moderationService.fetchModerationQueue(req.query.status as string);
    res.json({ success: true, data: queue });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch moderation queue',
      code: error.code || 'FETCH_QUEUE_ERROR',
    });
  }
}

export async function getModerationById(req: AuthRequest, res: Response): Promise<void> {
  try {
    const result = await moderationService.fetchModerationById(req.params.id);
    res.json({ success: true, data: result.evaluation, history: result.moderationHistory });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to fetch evaluation',
      code: error.code || 'FETCH_MODERATION_ERROR',
    });
  }
}

export async function approveEvaluation(req: AuthRequest, res: Response): Promise<void> {
  try {
    const result = await moderationService.approveEvaluationByModerator(
      req.params.id,
      req.user!._id.toString()
    );
    res.json({ success: true, data: result.evaluation, moderation: result.moderation });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to approve evaluation',
      code: error.code || 'APPROVE_EVALUATION_ERROR',
    });
  }
}

export async function returnEvaluation(req: AuthRequest, res: Response): Promise<void> {
  try {
    const { reason } = req.body;
    const result = await moderationService.returnEvaluationByModerator(
      req.params.id,
      reason,
      req.user!._id.toString()
    );
    res.json({ success: true, data: result.evaluation, moderation: result.moderation });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to return evaluation',
      code: error.code || 'RETURN_EVALUATION_ERROR',
    });
  }
}

export async function getModeratorStats(_req: AuthRequest, res: Response): Promise<void> {
  try {
    const stats = await moderationService.fetchModeratorStats();
    res.json({ success: true, data: stats });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch moderator stats',
      code: error.code || 'FETCH_STATS_ERROR',
    });
  }
}

export async function getIntegrityChecks(_req: AuthRequest, res: Response): Promise<void> {
  try {
    const issues = await moderationService.fetchIntegrityChecks();
    res.json({ success: true, data: issues });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch integrity checks',
      code: error.code || 'FETCH_INTEGRITY_ERROR',
    });
  }
}

export async function getExaminerAnalytics(_req: AuthRequest, res: Response): Promise<void> {
  try {
    const analytics = await moderationService.fetchExaminerAnalytics();
    res.json({ success: true, data: analytics });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch examiner analytics',
      code: error.code || 'FETCH_ANALYTICS_ERROR',
    });
  }
}
