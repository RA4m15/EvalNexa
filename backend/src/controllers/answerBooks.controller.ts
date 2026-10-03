import { Response } from 'express';
import { AuthRequest } from '../middleware/auth';
import * as answerBooksService from '../services/answerBooks.service';

export async function getAnswerBooks(req: AuthRequest, res: Response): Promise<void> {
  try {
    const answerBooks = await answerBooksService.fetchAnswerBooks(
      {
        examId: req.query.examId as string,
        status: req.query.status as string,
      },
      req.user!.role,
      req.user!._id.toString()
    );
    res.json({ success: true, data: answerBooks });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch answer books',
      code: error.code || 'FETCH_ANSWER_BOOKS_ERROR',
    });
  }
}

export async function createAnswerBook(req: AuthRequest, res: Response): Promise<void> {
  try {
    const answerBook = await answerBooksService.createNewAnswerBook(
      req.body,
      req.user!._id.toString()
    );
    res.status(201).json({ success: true, data: answerBook });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to create answer book',
      code: error.code || 'CREATE_ANSWER_BOOK_ERROR',
    });
  }
}

export async function getAnswerBookById(req: AuthRequest, res: Response): Promise<void> {
  try {
    const result = await answerBooksService.fetchAnswerBookById(
      req.params.id,
      req.user!.role,
      req.user!._id.toString()
    );
    res.json({ success: true, data: result });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to fetch answer book',
      code: error.code || 'FETCH_ANSWER_BOOK_ERROR',
    });
  }
}

export async function updateAnswerBook(req: AuthRequest, res: Response): Promise<void> {
  try {
    const answerBook = await answerBooksService.updateExistingAnswerBook(
      req.params.id,
      req.body,
      req.user!._id.toString()
    );
    if (!answerBook) {
      res.status(404).json({
        success: false,
        message: 'Answer book not found',
        code: 'NOT_FOUND',
      });
      return;
    }
    res.json({ success: true, data: answerBook });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to update answer book',
      code: error.code || 'UPDATE_ANSWER_BOOK_ERROR',
    });
  }
}

export async function assignAnswerBook(req: AuthRequest, res: Response): Promise<void> {
  try {
    const answerBook = await answerBooksService.assignAnswerBookToExaminer(
      req.params.id,
      req.body.examinerId,
      req.user!._id.toString()
    );
    res.json({ success: true, data: answerBook });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to assign answer book',
      code: error.code || 'ASSIGN_ANSWER_BOOK_ERROR',
    });
  }
}

export async function getExaminerAnswerBooks(req: AuthRequest, res: Response): Promise<void> {
  try {
    const result = await answerBooksService.fetchExaminerAnswerBooks(
      req.user!._id.toString(),
      req.query.status as string
    );
    res.json({ success: true, data: result.answerBooks, stats: result.stats });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch examiner answer books',
      code: error.code || 'FETCH_EXAMINER_BOOKS_ERROR',
    });
  }
}
