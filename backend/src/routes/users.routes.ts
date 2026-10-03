import { Router } from 'express';
import {
  getUsers,
  createUser,
  getUserById,
  updateUser,
  getExaminers,
} from '../controllers/users.controller';
import { authenticate, authorize } from '../middleware/auth';
import { validate } from '../middleware/validate';
import { createUserSchema, updateUserSchema } from '../validators/schemas';

const router = Router();

router.use(authenticate);

router.get('/', authorize('ADMIN'), getUsers);
router.post('/', authorize('ADMIN'), validate(createUserSchema), createUser);
router.get('/examiners', authorize('ADMIN'), getExaminers);
router.get('/:id', authorize('ADMIN'), getUserById);
router.patch('/:id', authorize('ADMIN'), validate(updateUserSchema), updateUser);

export default router;
