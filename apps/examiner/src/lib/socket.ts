import { io, Socket } from 'socket.io-client';

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || 'http://localhost:5000';
let socket: Socket | null = null;

export function getSocket(token?: string): Socket {
  if (!socket) {
    socket = io(SOCKET_URL, { withCredentials: true, auth: token ? { token } : {}, autoConnect: false });
  }
  return socket;
}

export function connectSocket(token: string): Socket {
  const s = getSocket(token);
  s.auth = { token };
  if (!s.connected) s.connect();
  return s;
}

export function disconnectSocket(): void {
  if (socket?.connected) { socket.disconnect(); socket = null; }
}
