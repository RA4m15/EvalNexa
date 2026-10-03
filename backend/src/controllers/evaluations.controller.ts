import { Response } from 'express';
import { AuthRequest } from '../middleware/auth';
import * as evaluationsService from '../services/evaluations.service';

export async function getEvaluations(req: AuthRequest, res: Response): Promise<void> {
  try {
    const evaluations = await evaluationsService.fetchEvaluations(
      { status: req.query.status as string },
      req.user!.role,
      req.user!._id.toString()
    );
    res.json({ success: true, data: evaluations });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch evaluations',
      code: error.code || 'FETCH_EVALUATIONS_ERROR',
    });
  }
}

export async function getEvaluationById(req: AuthRequest, res: Response): Promise<void> {
  try {
    const evaluation = await evaluationsService.fetchEvaluationById(
      req.params.id,
      req.user!.role,
      req.user!._id.toString()
    );
    res.json({ success: true, data: evaluation });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to fetch evaluation',
      code: error.code || 'FETCH_EVALUATION_ERROR',
    });
  }
}

export async function startEvaluation(req: AuthRequest, res: Response): Promise<void> {
  try {
    const { evaluation } = await evaluationsService.beginEvaluation(
      req.params.id,
      req.user!._id.toString()
    );
    res.json({ success: true, data: evaluation });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to start evaluation',
      code: error.code || 'START_EVALUATION_ERROR',
    });
  }
}

export async function updateEvaluation(req: AuthRequest, res: Response): Promise<void> {
  try {
    const evaluation = await evaluationsService.updateEvaluationMarks(
      req.params.id,
      req.body,
      req.user!._id.toString()
    );
    res.json({ success: true, data: evaluation });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to update evaluation',
      code: error.code || 'UPDATE_EVALUATION_ERROR',
    });
  }
}

export async function submitEvaluation(req: AuthRequest, res: Response): Promise<void> {
  try {
    const { evaluation } = await evaluationsService.submitEvaluationFinal(
      req.params.id,
      req.body,
      req.user!._id.toString()
    );
    res.json({ success: true, data: evaluation });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to submit evaluation',
      code: error.code || 'SUBMIT_EVALUATION_ERROR',
    });
  }
}
