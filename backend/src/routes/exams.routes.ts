import { Router } from 'express';
import {
  getExams,
  createExam,
  getExamById,
  updateExam,
  deleteExam,
  getAdminDashboardStats,
} from '../controllers/exams.controller';
import {
  getQuestionsForExam,
  createQuestion,
} from '../controllers/questions.controller';
import { getResultsForExam } from '../controllers/results.controller';
import { authenticate, authorize } from '../middleware/auth';
import { validate } from '../middleware/validate';
import {
  createExamSchema,
  updateExamSchema,
  createQuestionSchema,
} from '../validators/schemas';

const router = Router();

router.use(authenticate);

router.get('/stats/dashboard', authorize('ADMIN'), getAdminDashboardStats);
router.get('/', authorize('ADMIN', 'MODERATOR', 'EXAMINER'), getExams);
router.post('/', authorize('ADMIN'), validate(createExamSchema), createExam);
router.get('/:id', authorize('ADMIN', 'MODERATOR', 'EXAMINER'), getExamById);
router.patch('/:id', authorize('ADMIN'), validate(updateExamSchema), updateExam);
router.delete('/:id', authorize('ADMIN'), deleteExam);

// Question routes nested under exams
router.get('/:examId/questions', authorize('ADMIN', 'EXAMINER', 'MODERATOR'), getQuestionsForExam);
router.post(
  '/:examId/questions',
  authorize('ADMIN'),
  validate(createQuestionSchema),
  createQuestion
);

// Result routes nested under exams
router.get('/:examId/results', authorize('ADMIN', 'MODERATOR', 'EXAMINER'), getResultsForExam);

export default router;
