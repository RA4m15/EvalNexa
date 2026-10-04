import dotenv from 'dotenv';
import path from 'path';

dotenv.config();
if (!process.env.CLOUDINARY_CLOUD_NAME && !process.env.MONGODB_URI) {
  dotenv.config({ path: path.resolve(__dirname, '../../.env') });
}

export const config = {
  port: parseInt(process.env.PORT || '5000', 10),
  nodeEnv: process.env.NODE_ENV || 'development',
  mongoUri: process.env.MONGODB_URI || '',
  jwtSecret: process.env.JWT_SECRET || 'evalnexa-dev-secret',
  jwtExpiresIn: process.env.JWT_EXPIRES_IN || '7d',
  clients: {
    controlCenter:
      process.env.CONTROL_CENTER_ORIGIN ||
      process.env.CLIENT_CONTROL_CENTER_URL ||
      'http://localhost:5173',
    examiner:
      process.env.EXAMINER_ORIGIN ||
      process.env.CLIENT_EXAMINER_URL ||
      'http://localhost:5174',
    moderation:
      process.env.MODERATION_ORIGIN ||
      process.env.CLIENT_MODERATION_URL ||
      'http://localhost:5175',
  },
  allowedOrigins: [
    process.env.CONTROL_CENTER_ORIGIN || process.env.CLIENT_CONTROL_CENTER_URL || 'http://localhost:5173',
    process.env.EXAMINER_ORIGIN || process.env.CLIENT_EXAMINER_URL || 'http://localhost:5174',
    process.env.MODERATION_ORIGIN || process.env.CLIENT_MODERATION_URL || 'http://localhost:5175',
    'http://127.0.0.1:5173',
    'http://127.0.0.1:5174',
    'http://127.0.0.1:5175',
  ],
  cloudinary: {
    cloudName: process.env.CLOUDINARY_CLOUD_NAME || '',
    apiKey: process.env.CLOUDINARY_API_KEY || '',
    apiSecret: process.env.CLOUDINARY_API_SECRET || '',
  },
  ingestionApiKey: process.env.INGESTION_API_KEY || '',
};
