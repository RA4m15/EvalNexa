import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import cookieParser from 'cookie-parser';
import { config } from './config';
import { errorHandler, notFound } from './middleware/errorHandler';

import authRoutes from './routes/auth.routes';
import usersRoutes from './routes/users.routes';
import examsRoutes from './routes/exams.routes';
import answerBooksRoutes from './routes/answerBooks.routes';
import evaluationsRoutes from './routes/evaluations.routes';
import moderationRoutes from './routes/moderation.routes';
import questionsRoutes from './routes/questions.routes';
import auditRoutes from './routes/audit.routes';

const app = express();

// Security & parsing middleware
app.use(helmet());
app.use(
  cors({
    origin: config.allowedOrigins,
    credentials: true,
  })
);
app.use(morgan(config.nodeEnv === 'production' ? 'combined' : 'dev'));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(cookieParser());

// Health check
app.get('/health', (_req, res) => {
  res.json({ status: 'ok', service: 'EvalNexa API', timestamp: new Date().toISOString() });
});

// API routes
app.use('/api/auth', authRoutes);
app.use('/api/users', usersRoutes);
app.use('/api/exams', examsRoutes);
app.use('/api/questions', questionsRoutes);
app.use('/api/answer-books', answerBooksRoutes);
app.use('/api/evaluations', evaluationsRoutes);
app.use('/api/moderation', moderationRoutes);
app.use('/api/moderations', moderationRoutes);
app.use('/api/audit-logs', auditRoutes);

// Error handling
app.use(notFound);
app.use(errorHandler);

export default app;
