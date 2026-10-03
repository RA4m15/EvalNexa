import { Response } from 'express';
import { AuthRequest } from '../middleware/auth';
import * as usersService from '../services/users.service';

export async function getUsers(req: AuthRequest, res: Response): Promise<void> {
  try {
    const filter: Record<string, unknown> = {};
    if (req.query.role) filter.role = req.query.role;
    if (req.query.isActive !== undefined) filter.isActive = req.query.isActive === 'true';

    const users = await usersService.fetchUsers(filter);
    res.json({ success: true, data: users });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch users',
      code: error.code || 'FETCH_USERS_ERROR',
    });
  }
}

export async function getUserById(req: AuthRequest, res: Response): Promise<void> {
  try {
    const user = await usersService.fetchUserById(req.params.id);
    if (!user) {
      res.status(404).json({
        success: false,
        message: 'User not found',
        code: 'NOT_FOUND',
      });
      return;
    }
    res.json({ success: true, data: user });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch user',
      code: error.code || 'FETCH_USER_ERROR',
    });
  }
}

export async function createUser(req: AuthRequest, res: Response): Promise<void> {
  try {
    const user = await usersService.createNewUser(req.body, req.user!._id.toString());
    res.status(201).json({ success: true, data: user });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to create user',
      code: error.code || 'USER_CREATE_ERROR',
    });
  }
}

export async function updateUser(req: AuthRequest, res: Response): Promise<void> {
  try {
    const user = await usersService.updateExistingUser(
      req.params.id,
      req.body,
      req.user!._id.toString()
    );
    if (!user) {
      res.status(404).json({
        success: false,
        message: 'User not found',
        code: 'NOT_FOUND',
      });
      return;
    }
    res.json({ success: true, data: user });
  } catch (error: any) {
    const status = error.status || 500;
    res.status(status).json({
      success: false,
      message: error.message || 'Failed to update user',
      code: error.code || 'USER_UPDATE_ERROR',
    });
  }
}

export async function getExaminers(_req: AuthRequest, res: Response): Promise<void> {
  try {
    const examiners = await usersService.fetchActiveExaminers();
    res.json({ success: true, data: examiners });
  } catch (error: any) {
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to fetch examiners',
      code: error.code || 'FETCH_EXAMINERS_ERROR',
    });
  }
}
