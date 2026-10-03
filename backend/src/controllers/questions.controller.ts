import { Response } from 'express';
import { AuthRequest } from '../middleware/auth';
import * as questionsService from '../services/questions.service';

export async function getQuestionsForExam(req: AuthRequest, res: Response): Promise<void> {
  try {
    const questions = await questionsService.fetchQuestionsByExam(req.params.examId);
    res.json({ success: true, data: questions });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to fetch questions',
      code: error.code || 'QUESTIONS_FETCH_ERROR',
    });
  }
}

export async function getQuestionById(req: AuthRequest, res: Response): Promise<void> {
  try {
    const question = await questionsService.fetchQuestionById(req.params.id);
    if (!question) {
      res.status(404).json({
        success: false,
        message: 'Question not found',
        code: 'NOT_FOUND',
      });
      return;
    }
    res.json({ success: true, data: question });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch question',
      code: error.code || 'QUESTION_FETCH_ERROR',
    });
  }
}

export async function createQuestion(req: AuthRequest, res: Response): Promise<void> {
  try {
    const question = await questionsService.createNewQuestion(
      req.params.examId,
      req.body,
      req.user!._id.toString()
    );
    res.status(201).json({ success: true, data: question });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to create question',
      code: error.code || 'QUESTION_CREATE_ERROR',
    });
  }
}

export async function updateQuestion(req: AuthRequest, res: Response): Promise<void> {
  try {
    const question = await questionsService.updateExistingQuestion(
      req.params.id,
      req.body,
      req.user!._id.toString()
    );
    if (!question) {
      res.status(404).json({
        success: false,
        message: 'Question not found',
        code: 'NOT_FOUND',
      });
      return;
    }
    res.json({ success: true, data: question });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to update question',
      code: error.code || 'QUESTION_UPDATE_ERROR',
    });
  }
}

export async function deleteQuestion(req: AuthRequest, res: Response): Promise<void> {
  try {
    const deleted = await questionsService.deleteExistingQuestion(
      req.params.id,
      req.user!._id.toString()
    );
    if (!deleted) {
      res.status(404).json({
        success: false,
        message: 'Question not found',
        code: 'NOT_FOUND',
      });
      return;
    }
    res.json({ success: true, message: 'Question deleted successfully' });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to delete question',
      code: error.code || 'QUESTION_DELETE_ERROR',
    });
  }
}
