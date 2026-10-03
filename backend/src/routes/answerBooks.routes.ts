import { Router } from 'express';
import {
  getAnswerBooks,
  createAnswerBook,
  getAnswerBookById,
  updateAnswerBook,
  assignAnswerBook,
  getExaminerAnswerBooks,
} from '../controllers/answerBooks.controller';
import { authenticate, authorize } from '../middleware/auth';
import { validate } from '../middleware/validate';
import { createAnswerBookSchema, assignAnswerBookSchema } from '../validators/schemas';

const router = Router();

router.use(authenticate);

router.get('/my', authorize('EXAMINER'), getExaminerAnswerBooks);
router.get('/', authorize('ADMIN', 'MODERATOR', 'EXAMINER'), getAnswerBooks);
router.post('/', authorize('ADMIN'), validate(createAnswerBookSchema), createAnswerBook);
router.get('/:id', authenticate, getAnswerBookById);
router.patch('/:id', authorize('ADMIN'), updateAnswerBook);
router.post('/:id/assign', authorize('ADMIN'), validate(assignAnswerBookSchema), assignAnswerBook);

export default router;
