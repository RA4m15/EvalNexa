import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getSocket } from '../lib/socket';

export function useSocketEvents(events: Record<string, () => void>) {
  const queryClient = useQueryClient();

  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;

    const handlers: Array<[string, () => void]> = Object.entries(events);
    handlers.forEach(([event, handler]) => {
      socket.on(event, handler);
    });

    return () => {
      handlers.forEach(([event, handler]) => {
        socket.off(event, handler);
      });
    };
  }, [events]);

  return queryClient;
}
