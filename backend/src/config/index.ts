import dotenv from 'dotenv';
dotenv.config();

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
};
