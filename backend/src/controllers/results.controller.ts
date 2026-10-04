import { Response } from 'express';
import { AuthRequest } from '../middleware/auth';
import * as resultsService from '../services/results.service';

/**
 * Controller to finalize an approved evaluation into a certified Result record.
 */
export async function finalizeResult(req: AuthRequest, res: Response): Promise<void> {
  try {
    const { evaluationId } = req.params;
    const actorId = req.user!._id.toString();
    const actor = {
      name: req.user!.name,
      role: req.user!.role,
    };

    const result = await resultsService.finalizeEvaluationResult(
      evaluationId,
      actorId,
      actor
    );

    res.json({
      success: true,
      message: 'Examination result successfully certified and finalized',
      data: result,
    });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to finalize examination result',
      code: error.code || 'FINALIZE_RESULT_ERROR',
    });
  }
}

/**
 * Controller to fetch all results with optional filters.
 */
export async function getResults(req: AuthRequest, res: Response): Promise<void> {
  try {
    const { examId, status } = req.query;
    const results = await resultsService.fetchResults({
      examId: examId as string | undefined,
      status: status as string | undefined,
    });

    res.json({
      success: true,
      data: results,
    });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to fetch results',
      code: error.code || 'FETCH_RESULTS_ERROR',
    });
  }
}

/**
 * Controller to fetch results for a specific examination.
 */
export async function getResultsForExam(req: AuthRequest, res: Response): Promise<void> {
  try {
    const { examId } = req.params;
    const results = await resultsService.fetchResultsForExam(examId);

    res.json({
      success: true,
      data: results,
    });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to fetch examination results',
      code: error.code || 'FETCH_EXAM_RESULTS_ERROR',
    });
  }
}

/**
 * Controller to fetch a single result by its ID.
 */
export async function getResultById(req: AuthRequest, res: Response): Promise<void> {
  try {
    const { id } = req.params;
    const result = await resultsService.fetchResultById(id);

    res.json({
      success: true,
      data: result,
    });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to fetch result record',
      code: error.code || 'FETCH_RESULT_ERROR',
    });
  }
}
