import { Request, Response, NextFunction } from 'express';
import crypto from 'crypto';
import rateLimit from 'express-rate-limit';
import { config } from '../config';

/**
 * Middleware to authenticate requests from the scanning/recognition service
 * using the X-INGESTION-KEY header.
 */
export function requireIngestionKey(req: Request, res: Response, next: NextFunction): void {
  const providedKey = (req.headers['x-ingestion-key'] || req.headers['x-api-key']) as string | undefined;

  if (!providedKey) {
    res.status(401).json({
      success: false,
      message: 'Authentication failed: Missing X-INGESTION-KEY header',
    });
    return;
  }

  const expectedKey = config.ingestionApiKey;

  if (!expectedKey) {
    console.error('[IngestionAuth] INGESTION_API_KEY is not configured on the server');
    res.status(500).json({
      success: false,
      message: 'Server ingestion configuration error',
    });
    return;
  }

  // Safe timing comparison
  const providedBuffer = Buffer.from(providedKey);
  const expectedBuffer = Buffer.from(expectedKey);

  if (
    providedBuffer.length !== expectedBuffer.length ||
    !crypto.timingSafeEqual(providedBuffer, expectedBuffer)
  ) {
    res.status(403).json({
      success: false,
      message: 'Forbidden: Invalid ingestion API key',
    });
    return;
  }

  next();
}

/**
 * Dedicated rate limiter for server-to-server ingestion endpoints
 */
export const ingestionRateLimiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: 120, // 120 requests per minute
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    success: false,
    message: 'Too many ingestion requests from this IP. Please throttle.',
  },
});
