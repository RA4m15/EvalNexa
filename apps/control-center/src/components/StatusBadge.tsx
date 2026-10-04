import React from 'react';
import { AnswerBookStatus, EvaluationStatus, ExamStatus } from '@evalnexa/types';

type AnyStatus = AnswerBookStatus | EvaluationStatus | ExamStatus;

const STATUS_MAP: Record<string, string> = {
  READY: 'ready',
  ASSIGNED: 'assigned',
  IN_PROGRESS: 'in_progress',
  SUBMITTED: 'submitted',
  UNDER_REVIEW: 'under_review',
  APPROVED: 'approved',
  RETURNED: 'returned',
  FINALIZED: 'finalized',
  PUBLISHED: 'finalized',
  WITHHELD: 'returned',
  DRAFT: 'draft',
  EVALUATION_OPEN: 'ready',
  EVALUATION_CLOSED: 'assigned',
  MODERATION: 'under_review',
  NOT_STARTED: 'not_started',
};

const STATUS_LABELS: Record<string, string> = {
  READY: 'Ready',
  ASSIGNED: 'Assigned',
  IN_PROGRESS: 'In Progress',
  SUBMITTED: 'Submitted',
  UNDER_REVIEW: 'Under Review',
  APPROVED: 'Approved',
  RETURNED: 'Returned',
  FINALIZED: 'Finalized',
  PUBLISHED: 'Published',
  WITHHELD: 'Withheld',
  DRAFT: 'Draft',
  EVALUATION_OPEN: 'Open',
  EVALUATION_CLOSED: 'Closed',
  MODERATION: 'Moderation',
  NOT_STARTED: 'Not Started',
};

export function StatusBadge({ status }: { status: AnyStatus | string }) {
  const cls = STATUS_MAP[status] || 'not_started';
  const label = STATUS_LABELS[status] || status;
  return (
    <span className={`status-badge status-badge--${cls}`}>{label}</span>
  );
}
