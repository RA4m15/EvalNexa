import { Router } from 'express';
import {
  getEvaluations,
  getEvaluationById,
  startEvaluation,
  updateEvaluation,
  submitEvaluation,
  getAIEvaluationSuggestion,
} from '../controllers/evaluations.controller';
import { authenticate, authorize } from '../middleware/auth';
import { validate } from '../middleware/validate';
import { updateEvaluationSchema, submitEvaluationSchema } from '../validators/schemas';

const router = Router();

router.use(authenticate);

router.get('/', authorize('ADMIN', 'MODERATOR', 'EXAMINER'), getEvaluations);
router.get('/:id', authorize('ADMIN', 'MODERATOR', 'EXAMINER'), getEvaluationById);
router.post('/:id/start', authorize('EXAMINER'), startEvaluation);
router.patch('/:id', authorize('EXAMINER'), validate(updateEvaluationSchema), updateEvaluation);
router.post('/:id/submit', authorize('EXAMINER'), validate(submitEvaluationSchema), submitEvaluation);

// AI-Assisted Question Evaluation Copilot
router.get(
  '/:id/questions/:questionNumber/suggest',
  authorize('EXAMINER', 'MODERATOR', 'ADMIN'),
  getAIEvaluationSuggestion
);
router.post(
  '/:id/questions/:questionNumber/suggest',
  authorize('EXAMINER', 'MODERATOR', 'ADMIN'),
  getAIEvaluationSuggestion
);

export default router;
