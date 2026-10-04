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

/**
 * Controller to publish a single finalized result to the public/institutional ledger.
 */
export async function publishResult(req: AuthRequest, res: Response): Promise<void> {
  try {
    const { id } = req.params;
    const actorId = req.user!._id.toString();
    const actor = {
      name: req.user!.name,
      role: req.user!.role,
    };

    const result = await resultsService.publishResult(id, actorId, actor);

    res.json({
      success: true,
      message: 'Examination result successfully published',
      data: result,
    });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to publish examination result',
      code: error.code || 'PUBLISH_RESULT_ERROR',
    });
  }
}

/**
 * Controller to batch publish all finalized results for an examination.
 */
export async function publishExamResults(req: AuthRequest, res: Response): Promise<void> {
  try {
    const { examId } = req.body;
    if (!examId) {
      res.status(400).json({
        success: false,
        message: 'Exam ID is required to publish exam results',
        code: 'MISSING_EXAM_ID',
      });
      return;
    }

    const actorId = req.user!._id.toString();
    const actor = {
      name: req.user!.name,
      role: req.user!.role,
    };

    const result = await resultsService.publishResultsForExam(examId, actorId, actor);

    res.json({
      success: true,
      message: result.message,
      data: result,
    });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to publish examination results',
      code: error.code || 'PUBLISH_EXAM_RESULTS_ERROR',
    });
  }
}

/**
 * Controller to withhold a result with justification.
 */
export async function withholdResult(req: AuthRequest, res: Response): Promise<void> {
  try {
    const { id } = req.params;
    const { reason } = req.body;
    const actorId = req.user!._id.toString();
    const actor = {
      name: req.user!.name,
      role: req.user!.role,
    };

    const result = await resultsService.withholdResult(id, reason, actorId, actor);

    res.json({
      success: true,
      message: 'Examination result flagged as withheld',
      data: result,
    });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to withhold result',
      code: error.code || 'WITHHOLD_RESULT_ERROR',
    });
  }
}

/**
 * Controller to release a previously withheld result back into circulation.
 */
export async function releaseResult(req: AuthRequest, res: Response): Promise<void> {
  try {
    const { id } = req.params;
    const actorId = req.user!._id.toString();
    const actor = {
      name: req.user!.name,
      role: req.user!.role,
    };

    const result = await resultsService.releaseWithheldResult(id, actorId, actor);

    res.json({
      success: true,
      message: 'Examination result released from withheld status',
      data: result,
    });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to release withheld result',
      code: error.code || 'RELEASE_RESULT_ERROR',
    });
  }
}

/**
 * Controller to batch-finalize all approved evaluations for an examination.
 */
export async function batchFinalizeResults(req: AuthRequest, res: Response): Promise<void> {
  try {
    const { examId } = req.body;
    if (!examId) {
      res.status(400).json({
        success: false,
        message: 'Exam ID is required to batch finalize results',
        code: 'MISSING_EXAM_ID',
      });
      return;
    }

    const actorId = req.user!._id.toString();
    const actor = {
      name: req.user!.name,
      role: req.user!.role,
    };

    const result = await resultsService.batchFinalizeApprovedEvaluations(examId, actorId, actor);

    res.json({
      success: true,
      message: `Batch finalization complete: ${result.finalizedCount} of ${result.totalApproved} approved scripts certified.`,
      data: result,
    });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to batch finalize results',
      code: error.code || 'BATCH_FINALIZE_ERROR',
    });
  }
}
