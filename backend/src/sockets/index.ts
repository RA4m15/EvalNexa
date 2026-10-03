import { Server as HttpServer } from 'http';
import { Server as SocketServer, Socket } from 'socket.io';
import jwt from 'jsonwebtoken';
import { config } from '../config';
import { User } from '../models/User';
import { UserRole } from '@evalnexa/types';

let io: SocketServer;

export function initializeSocket(httpServer: HttpServer): SocketServer {
  io = new SocketServer(httpServer, {
    cors: {
      origin: config.allowedOrigins,
      methods: ['GET', 'POST'],
      credentials: true,
    },
  });

  io.use(async (socket: Socket, next) => {
    try {
      const token = socket.handshake.auth.token || socket.handshake.headers.cookie
        ?.split(';')
        .find((c) => c.trim().startsWith('token='))
        ?.split('=')[1];

      if (!token) {
        return next(new Error('Authentication required'));
      }

      const decoded = jwt.verify(token, config.jwtSecret) as {
        userId: string;
        role: UserRole;
      };

      const user = await User.findById(decoded.userId).select('-passwordHash');
      if (!user || !user.isActive) {
        return next(new Error('User not found or inactive'));
      }

      socket.data.userId = user._id.toString();
      socket.data.role = user.role;
      next();
    } catch {
      next(new Error('Invalid token'));
    }
  });

  io.on('connection', (socket: Socket) => {
    const { userId, role } = socket.data;
    console.log(`[Socket] Connected: ${userId} (${role})`);

    // Join role room
    socket.join(`role:${role.toLowerCase()}`);
    // Join personal room
    socket.join(`user:${userId}`);

    socket.on('join:exam', (examId: string) => {
      socket.join(`exam:${examId}`);
    });

    socket.on('leave:exam', (examId: string) => {
      socket.leave(`exam:${examId}`);
    });

    socket.on('disconnect', () => {
      console.log(`[Socket] Disconnected: ${userId}`);
    });
  });

  return io;
}

export function getIO(): SocketServer {
  if (!io) {
    throw new Error('Socket.IO not initialized. Call initializeSocket first.');
  }
  return io;
}

export function emitToRole(role: UserRole, event: string, data: unknown): void {
  if (io) {
    io.to(`role:${role.toLowerCase()}`).emit(event, {
      ...((data as object) || {}),
      timestamp: new Date().toISOString(),
    });
  }
}

export function emitToAll(event: string, data: unknown): void {
  if (io) {
    io.emit(event, {
      ...((data as object) || {}),
      timestamp: new Date().toISOString(),
    });
  }
}

export function emitToExam(examId: string, event: string, data: unknown): void {
  if (io) {
    io.to(`exam:${examId}`).emit(event, {
      ...((data as object) || {}),
      timestamp: new Date().toISOString(),
    });
  }
}

export function emitToUser(userId: string, event: string, data: unknown): void {
  if (io) {
    io.to(`user:${userId}`).emit(event, {
      ...((data as object) || {}),
      timestamp: new Date().toISOString(),
    });
  }
}
