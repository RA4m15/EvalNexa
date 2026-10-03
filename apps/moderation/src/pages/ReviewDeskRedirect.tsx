import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { Evaluation } from '@evalnexa/types';

export function ReviewDeskRedirect() {
  const navigate = useNavigate();

  const { data: queue = [], isLoading } = useQuery<Evaluation[]>({
    queryKey: ['moderation-queue'],
    queryFn: async () => {
      const { data } = await apiClient.get('/moderation');
      return data.data;
    },
  });

  useEffect(() => {
    if (isLoading) return;

    // Pick highest priority evaluation: UNDER_REVIEW -> SUBMITTED
    const priorityEvaluation =
      queue.find((e) => e.status === 'UNDER_REVIEW') ||
      queue.find((e) => e.status === 'SUBMITTED') ||
      queue[0];

    if (priorityEvaluation) {
      navigate(`/review/${priorityEvaluation._id}`, { replace: true });
    } else {
      navigate('/queue', { replace: true });
    }
  }, [queue, isLoading, navigate]);

  return (
    <div style={{ padding: '80px 0', textAlign: 'center', fontFamily: 'Cambria, serif', color: 'var(--navy)' }}>
      <div style={{ fontSize: 32, marginBottom: 12 }}>⚖</div>
      <div style={{ fontSize: 22, fontWeight: 700 }}>Opening Moderation Review Desk…</div>
      <div style={{ fontSize: 14, color: 'var(--text-muted)', marginTop: 6 }}>
        Retrieving active examination evaluation docket from MongoDB
      </div>
    </div>
  );
}
