import { Router } from 'express';
import {
  getQuestionById,
  updateQuestion,
  deleteQuestion,
} from '../controllers/questions.controller';
import { authenticate, authorize } from '../middleware/auth';
import { validate } from '../middleware/validate';
import { updateQuestionSchema } from '../validators/schemas';

const router = Router();

router.use(authenticate);

router.get('/:id', authorize('ADMIN', 'EXAMINER', 'MODERATOR'), getQuestionById);
router.patch('/:id', authorize('ADMIN'), validate(updateQuestionSchema), updateQuestion);
router.delete('/:id', authorize('ADMIN'), deleteQuestion);

export default router;
