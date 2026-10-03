import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Exam, User } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';

export function AssignmentsPage() {
  const queryClient = useQueryClient();
  const [selectedBook, setSelectedBook] = useState<AnswerBook | null>(null);
  const [selectedExaminerId, setSelectedExaminerId] = useState('');
  const [assignError, setAssignError] = useState('');
  const [assignSuccess, setAssignSuccess] = useState('');

  const { data: answerBooks = [], isLoading: booksLoading } = useQuery<AnswerBook[]>({
    queryKey: ['answer-books-assignable'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books?status=READY');
      return data.data;
    },
  });

  const { data: returnedBooks = [] } = useQuery<AnswerBook[]>({
    queryKey: ['answer-books-returned'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books?status=RETURNED');
      return data.data;
    },
  });

  const { data: examiners = [] } = useQuery<User[]>({
    queryKey: ['examiners'],
    queryFn: async () => {
      const { data } = await apiClient.get('/users/examiners');
      return data.data;
    },
  });

  const assignablBooks = [...answerBooks, ...returnedBooks];

  const assignMutation = useMutation({
    mutationFn: async ({ bookId, examinerId }: { bookId: string; examinerId: string }) => {
      const { data } = await apiClient.post(`/answer-books/${bookId}/assign`, { examinerId });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['answer-books-assignable'] });
      queryClient.invalidateQueries({ queryKey: ['answer-books-returned'] });
      queryClient.invalidateQueries({ queryKey: ['answer-books'] });
      queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] });
      setAssignSuccess('Answer book assigned successfully.');
      setSelectedBook(null);
      setSelectedExaminerId('');
      setTimeout(() => setAssignSuccess(''), 4000);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || 'Assignment failed';
      setAssignError(msg);
    },
  });

  const handleAssign = () => {
    if (!selectedBook || !selectedExaminerId) {
      setAssignError('Please select both an answer book and an examiner.');
      return;
    }
    setAssignError('');
    assignMutation.mutate({ bookId: selectedBook._id, examinerId: selectedExaminerId });
  };

  return (
    <div>
      <div className="page-header">
        <div className="page-header__eyebrow">Control Center · Assignment</div>
        <h1 className="page-header__title">Examiner Assignment</h1>
        <p className="page-header__subtitle">
          Assign answer books to qualified examiners. Assigned examiners are notified in real time.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--space-6)' }}>
        {/* Left: assignable books */}
        <div>
          <div className="section-header">
            <span className="section-header__title">Unassigned Answer Books ({assignablBooks.length})</span>
          </div>

          {booksLoading ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : assignablBooks.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-10)' }}>
              <div className="state-icon">✓</div>
              <div className="state-title">All Answer Books Assigned</div>
              <div className="state-body">
                No answer books are currently in READY or RETURNED status. Register more answer books to continue.
              </div>
            </div>
          ) : (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Select</th>
                    <th>Answer Book Code</th>
                    <th>Student Code</th>
                    <th>Examination</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {assignablBooks.map((ab) => {
                    const exam = typeof ab.examId === 'object' ? ab.examId as unknown as Exam : null;
                    return (
                      <tr
                        key={ab._id}
                        style={{ cursor: 'pointer', background: selectedBook?._id === ab._id ? 'var(--bg-overlay)' : undefined }}
                        onClick={() => setSelectedBook(ab)}
                      >
                        <td>
                          <input
                            type="radio"
                            checked={selectedBook?._id === ab._id}
                            onChange={() => setSelectedBook(ab)}
                            style={{ accentColor: 'var(--bg-dark)' }}
                          />
                        </td>
                        <td><span className="data-table__code">{ab.answerBookCode}</span></td>
                        <td><span className="data-table__code">{ab.studentCode}</span></td>
                        <td>{exam?.title || '—'}</td>
                        <td><StatusBadge status={ab.status} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Right: assignment panel */}
        <div>
          <div className="folio-card">
            <div className="folio-card__header">
              <span className="folio-card__title">Assignment Panel</span>
            </div>
            <div className="folio-card__body">
              {selectedBook ? (
                <div style={{ marginBottom: 'var(--space-5)' }}>
                  <div className="label-caps" style={{ marginBottom: 6 }}>Selected Answer Book</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600 }}>
                    {selectedBook.answerBookCode}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                    Student: {selectedBook.studentCode}
                  </div>
                </div>
              ) : (
                <div style={{ color: 'var(--text-faint)', fontSize: 12, marginBottom: 'var(--space-5)', fontStyle: 'italic' }}>
                  Select an answer book from the table on the left.
                </div>
              )}

              <div className="form-field" style={{ marginBottom: 'var(--space-5)' }}>
                <label className="form-label">Assign to Examiner</label>
                {examiners.length === 0 ? (
                  <div style={{ fontSize: 12, color: 'var(--text-faint)', fontStyle: 'italic' }}>
                    No active examiners found. Create examiners via user management.
                  </div>
                ) : (
                  <select
                    className="form-select"
                    value={selectedExaminerId}
                    onChange={(e) => setSelectedExaminerId(e.target.value)}
                  >
                    <option value="">— Select examiner —</option>
                    {examiners.map((examiner) => (
                      <option key={examiner._id} value={examiner._id}>
                        {examiner.name} ({examiner.email})
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {assignError && (
                <div className="form-error" style={{ padding: 'var(--space-3)', background: 'var(--status-returned-bg)', borderRadius: 'var(--radius-sm)', marginBottom: 'var(--space-4)' }}>
                  ⚠ {assignError}
                </div>
              )}

              {assignSuccess && (
                <div style={{ padding: 'var(--space-3)', background: 'var(--status-approved-bg)', border: '1px solid rgba(45,106,79,0.2)', borderRadius: 'var(--radius-sm)', fontSize: 12, color: 'var(--status-approved)', marginBottom: 'var(--space-4)' }}>
                  ✓ {assignSuccess}
                </div>
              )}

              <button
                className="btn btn-primary w-full"
                style={{ width: '100%' }}
                disabled={!selectedBook || !selectedExaminerId || assignMutation.isPending}
                onClick={handleAssign}
              >
                {assignMutation.isPending ? 'Assigning…' : 'Confirm Assignment'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
