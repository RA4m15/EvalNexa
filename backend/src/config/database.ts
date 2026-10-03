import mongoose from 'mongoose';
import { config } from './index';

export async function connectDatabase(): Promise<void> {
  if (!config.mongoUri) {
    throw new Error('MONGODB_URI is not defined. Please set it in your .env file.');
  }

  try {
    await mongoose.connect(config.mongoUri);
    console.log('[DB] MongoDB connected successfully');
  } catch (error) {
    console.error('[DB] MongoDB connection failed:', error);
    process.exit(1);
  }
}

mongoose.connection.on('disconnected', () => {
  console.warn('[DB] MongoDB disconnected');
});

mongoose.connection.on('reconnected', () => {
  console.log('[DB] MongoDB reconnected');
});
