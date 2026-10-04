import { Router } from 'express';
import {
  finalizeResult,
  getResults,
  getResultById,
  getResultsForExam,
} from '../controllers/results.controller';
import { authenticate, authorize } from '../middleware/auth';

const router = Router();

router.use(authenticate);

// Public query within authenticated roles
router.get('/', authorize('ADMIN', 'MODERATOR', 'EXAMINER'), getResults);
router.get('/exam/:examId', authorize('ADMIN', 'MODERATOR', 'EXAMINER'), getResultsForExam);
router.get('/:id', authorize('ADMIN', 'MODERATOR', 'EXAMINER'), getResultById);

// Finalization is restricted to ADMIN and MODERATOR
router.post(
  '/:evaluationId/finalize',
  authorize('ADMIN', 'MODERATOR'),
  finalizeResult
);

export default router;
