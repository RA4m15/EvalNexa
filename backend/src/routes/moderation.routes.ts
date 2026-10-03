import { Router } from 'express';
import {
  getModerationQueue,
  getModerationById,
  approveEvaluation,
  returnEvaluation,
  getModeratorStats,
  getIntegrityChecks,
  getExaminerAnalytics,
} from '../controllers/moderation.controller';
import { authenticate, authorize } from '../middleware/auth';
import { validate } from '../middleware/validate';
import { returnEvaluationSchema } from '../validators/schemas';

const router = Router();

router.use(authenticate, authorize('MODERATOR', 'ADMIN'));

router.get('/stats', getModeratorStats);
router.get('/queue', getModerationQueue);
router.get('/integrity-checks', getIntegrityChecks);
router.get('/examiner-analytics', getExaminerAnalytics);
router.get('/', getModerationQueue);
router.get('/:id', getModerationById);
router.post('/:id/approve', approveEvaluation);
router.post('/:id/return', validate(returnEvaluationSchema), returnEvaluation);

export default router;
