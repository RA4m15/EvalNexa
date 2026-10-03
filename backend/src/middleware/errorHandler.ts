import { Request, Response, NextFunction } from 'express';

export function errorHandler(
  err: Error,
  _req: Request,
  res: Response,
  _next: NextFunction
): void {
  console.error('[Error]', err.message, err.stack);

  res.status(500).json({
    success: false,
    message:
      process.env.NODE_ENV === 'production'
        ? 'Internal server error'
        : err.message || 'Internal server error',
    code: 'INTERNAL_SERVER_ERROR',
  });
}

export function notFound(_req: Request, res: Response): void {
  res.status(404).json({
    success: false,
    message: 'The requested resource was not found',
    code: 'NOT_FOUND',
  });
}
