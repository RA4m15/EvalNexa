import { Response } from 'express';
import { AuthRequest } from '../middleware/auth';
import * as examsService from '../services/exams.service';

export async function getExams(req: AuthRequest, res: Response): Promise<void> {
  try {
    const filter: Record<string, unknown> = {};
    if (req.query.status) filter.status = req.query.status;
    if (req.query.academicSession) filter.academicSession = req.query.academicSession;

    const exams = await examsService.fetchExams(filter);
    res.json({ success: true, data: exams });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch exams',
      code: error.code || 'FETCH_EXAMS_ERROR',
    });
  }
}

export async function getExamById(req: AuthRequest, res: Response): Promise<void> {
  try {
    const exam = await examsService.fetchExamById(req.params.id);
    if (!exam) {
      res.status(404).json({
        success: false,
        message: 'Exam not found',
        code: 'NOT_FOUND',
      });
      return;
    }
    res.json({ success: true, data: exam });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch exam',
      code: error.code || 'FETCH_EXAM_ERROR',
    });
  }
}

export async function createExam(req: AuthRequest, res: Response): Promise<void> {
  try {
    const exam = await examsService.createNewExam(req.body, req.user!._id.toString());
    res.status(201).json({ success: true, data: exam });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to create exam',
      code: error.code || 'CREATE_EXAM_ERROR',
    });
  }
}

export async function updateExam(req: AuthRequest, res: Response): Promise<void> {
  try {
    const exam = await examsService.updateExistingExam(
      req.params.id,
      req.body,
      req.user!._id.toString()
    );
    if (!exam) {
      res.status(404).json({
        success: false,
        message: 'Exam not found',
        code: 'NOT_FOUND',
      });
      return;
    }
    res.json({ success: true, data: exam });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to update exam',
      code: error.code || 'UPDATE_EXAM_ERROR',
    });
  }
}

export async function deleteExam(req: AuthRequest, res: Response): Promise<void> {
  try {
    const deleted = await examsService.deleteExistingExam(
      req.params.id,
      req.user!._id.toString()
    );
    if (!deleted) {
      res.status(404).json({
        success: false,
        message: 'Exam not found',
        code: 'NOT_FOUND',
      });
      return;
    }
    res.json({ success: true, message: 'Exam deleted successfully' });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to delete exam',
      code: error.code || 'DELETE_EXAM_ERROR',
    });
  }
}

export async function getAdminDashboardStats(_req: AuthRequest, res: Response): Promise<void> {
  try {
    const stats = await examsService.fetchAdminDashboardStats();
    res.json({ success: true, data: stats });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch dashboard stats',
      code: error.code || 'FETCH_STATS_ERROR',
    });
  }
}
