import { Router } from 'express';
import {
  finalizeResult,
  getResults,
  getResultById,
  getResultsForExam,
  publishResult,
  publishExamResults,
  withholdResult,
  releaseResult,
  batchFinalizeResults,
} from '../controllers/results.controller';
import { authenticate, authorize } from '../middleware/auth';

const router = Router();

router.use(authenticate);

// Query endpoints within authenticated roles
router.get('/', authorize('ADMIN', 'MODERATOR', 'EXAMINER'), getResults);
router.get('/exam/:examId', authorize('ADMIN', 'MODERATOR', 'EXAMINER'), getResultsForExam);

// Batch administrative operations (mounted before :id routes to prevent parameter collision)
router.post('/publish-exam', authorize('ADMIN', 'MODERATOR'), publishExamResults);
router.post('/batch-finalize', authorize('ADMIN', 'MODERATOR'), batchFinalizeResults);

// Specific evaluation / result mutations
router.post('/:evaluationId/finalize', authorize('ADMIN', 'MODERATOR'), finalizeResult);
router.post('/:id/publish', authorize('ADMIN', 'MODERATOR'), publishResult);
router.post('/:id/withhold', authorize('ADMIN', 'MODERATOR'), withholdResult);
router.post('/:id/release', authorize('ADMIN', 'MODERATOR'), releaseResult);

// Single record query
router.get('/:id', authorize('ADMIN', 'MODERATOR', 'EXAMINER'), getResultById);

export default router;
