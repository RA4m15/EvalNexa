import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AnswerBook } from '@evalnexa/types';

export function EvaluateRedirect() {
  const navigate = useNavigate();

  const { data: papers = [], isLoading } = useQuery<AnswerBook[]>({
    queryKey: ['my-papers'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books/my');
      return data.data;
    },
  });

  useEffect(() => {
    if (isLoading) return;

    // Pick highest priority script: RETURNED -> IN_PROGRESS -> ASSIGNED
    const priorityScript =
      papers.find((p) => p.status === 'RETURNED') ||
      papers.find((p) => p.status === 'IN_PROGRESS') ||
      papers.find((p) => p.status === 'ASSIGNED');

    if (priorityScript) {
      navigate(`/evaluate/${priorityScript._id}`, { replace: true });
    } else {
      navigate('/papers', { replace: true });
    }
  }, [papers, isLoading, navigate]);

  return (
    <div style={{ padding: '80px 0', textAlign: 'center', fontFamily: 'Cambria', color: 'var(--navy)' }}>
      <div style={{ fontSize: 28, marginBottom: 12 }}>📖</div>
      <div style={{ fontSize: 20, fontWeight: 700 }}>Opening Marking Desk…</div>
    </div>
  );
}
