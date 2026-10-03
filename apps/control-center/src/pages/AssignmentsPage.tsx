import React, { useState, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { AnswerBook, Exam, User } from '@evalnexa/types';
import { StatusBadge } from '../components/StatusBadge';
import { useSocketEvents } from '../hooks/useSocketEvents';

export function AssignmentsPage() {
  const queryClient = useQueryClient();
  const [selectedExamId, setSelectedExamId] = useState<string>('');
  const [selectedBookId, setSelectedBookId] = useState<string | null>(null);
  const [selectedExaminerId, setSelectedExaminerId] = useState<string>('');
  const [assignError, setAssignError] = useState('');
  const [assignSuccess, setAssignSuccess] = useState('');
  const [isAutoAssigning, setIsAutoAssigning] = useState(false);
  const [autoAssignProgress, setAutoAssignProgress] = useState<string | null>(null);

  // 1. Fetch real Answer Books from MongoDB
  const { data: allAnswerBooks = [], isLoading: booksLoading } = useQuery<AnswerBook[]>({
    queryKey: ['answer-books-all'],
    queryFn: async () => {
      const { data } = await apiClient.get('/answer-books');
      return data.data;
    },
  });

  // 2. Fetch real Exams
  const { data: exams = [] } = useQuery<Exam[]>({
    queryKey: ['exams'],
    queryFn: async () => {
      const { data } = await apiClient.get('/exams');
      return data.data;
    },
  });

  // 3. Fetch accredited Examiners
  const { data: examiners = [], isLoading: examinersLoading } = useQuery<User[]>({
    queryKey: ['examiners'],
    queryFn: async () => {
      const { data } = await apiClient.get('/users/examiners');
      return data.data;
    },
  });

  // Real-time socket sync
  const handlers = useCallback(() => ({
    'answerbook.assigned': () => {
      queryClient.invalidateQueries({ queryKey: ['answer-books-all'] });
      queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] });
    },
    'answerbook.status.changed': () => {
      queryClient.invalidateQueries({ queryKey: ['answer-books-all'] });
      queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] });
    },
    'evaluation.started': () => {
      queryClient.invalidateQueries({ queryKey: ['answer-books-all'] });
    },
    'evaluation.submitted': () => {
      queryClient.invalidateQueries({ queryKey: ['answer-books-all'] });
    },
    'moderation.approved': () => {
      queryClient.invalidateQueries({ queryKey: ['answer-books-all'] });
    },
  }), [queryClient]);
  useSocketEvents(handlers());

  // Filter assignable answer books (status READY or RETURNED)
  const assignableBooks = useMemo(() => {
    return allAnswerBooks.filter((ab) => {
      const isAssignable = ab.status === 'READY' || ab.status === 'RETURNED';
      if (!isAssignable) return false;
      if (selectedExamId) {
        const eid = typeof ab.examId === 'object' ? (ab.examId as any)._id : ab.examId;
        if (eid !== selectedExamId) return false;
      }
      return true;
    });
  }, [allAnswerBooks, selectedExamId]);

  // Compute live workload for each examiner
  const examinerWorkload = useMemo(() => {
    return examiners.map((ex) => {
      const assignedToExaminer = allAnswerBooks.filter((ab) => {
        const eid = typeof ab.assignedExaminerId === 'object' ? (ab.assignedExaminerId as any)?._id : ab.assignedExaminerId;
        return eid === ex._id;
      });

      const assignedCount = assignedToExaminer.filter((b) => b.status === 'ASSIGNED').length;
      const inProgressCount = assignedToExaminer.filter((b) => b.status === 'IN_PROGRESS').length;
      const completedCount = assignedToExaminer.filter((b) => ['SUBMITTED', 'APPROVED', 'FINALIZED'].includes(b.status)).length;
      const activeLoad = assignedCount + inProgressCount;

      let capacityStatus = 'AVAILABLE';
      let capacityBadgeClass = 'status-badge--approved';
      if (activeLoad >= 5) {
        capacityStatus = 'AT CAPACITY';
        capacityBadgeClass = 'status-badge--returned';
      } else if (activeLoad >= 2) {
        capacityStatus = 'MODERATE';
        capacityBadgeClass = 'status-badge--review';
      }

      return {
        examiner: ex,
        assignedCount,
        inProgressCount,
        completedCount,
        activeLoad,
        capacityStatus,
        capacityBadgeClass,
      };
    });
  }, [examiners, allAnswerBooks]);

  const selectedBook = allAnswerBooks.find((b) => b._id === selectedBookId) || null;
  const selectedExaminer = examiners.find((ex) => ex._id === selectedExaminerId) || null;
  const selectedExam = exams.find((ex) => ex._id === selectedExamId) || null;

  // Single Assignment Mutation
  const assignMutation = useMutation({
    mutationFn: async ({ bookId, examinerId }: { bookId: string; examinerId: string }) => {
      const { data } = await apiClient.post(`/answer-books/${bookId}/assign`, { examinerId });
      return data;
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['answer-books-all'] });
      queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] });
      setAssignSuccess(`Digital script ${res.data?.answerBookCode || ''} assigned successfully.`);
      setSelectedBookId(null);
      setSelectedExaminerId('');
      setAssignError('');
      setTimeout(() => setAssignSuccess(''), 5000);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || 'Assignment failed';
      setAssignError(msg);
    },
  });

  const handleManualAssign = () => {
    if (!selectedBookId || !selectedExaminerId) {
      setAssignError('Please select both a digital script and an examiner to proceed.');
      return;
    }
    setAssignError('');
    assignMutation.mutate({ bookId: selectedBookId, examinerId: selectedExaminerId });
  };

  // Deterministic Load-Balancing Auto Assignment
  const handleAutoAssign = async () => {
    if (assignableBooks.length === 0) {
      alert('No unassigned scripts available for allocation.');
      return;
    }
    if (examiners.length === 0) {
      alert('No accredited examiners registered.');
      return;
    }

    const confirmRun = window.confirm(
      `Auto-assign ${assignableBooks.length} available script(s) across ${examiners.length} examiner(s) using deterministic load-balancing?`
    );
    if (!confirmRun) return;

    setIsAutoAssigning(true);
    setAssignError('');
    setAssignSuccess('');

    try {
      const currentLoads = new Map<string, number>();
      examinerWorkload.forEach((ew) => {
        currentLoads.set(ew.examiner._id, ew.activeLoad);
      });

      let assignedCount = 0;
      for (let i = 0; i < assignableBooks.length; i++) {
        const book = assignableBooks[i];
        setAutoAssignProgress(`Assigning script ${i + 1} of ${assignableBooks.length} (${book.answerBookCode})…`);

        let lowestExaminerId = examiners[0]._id;
        let lowestLoad = Infinity;
        for (const ex of examiners) {
          const load = currentLoads.get(ex._id) ?? 0;
          if (load < lowestLoad) {
            lowestLoad = load;
            lowestExaminerId = ex._id;
          }
        }

        await apiClient.post(`/answer-books/${book._id}/assign`, {
          examinerId: lowestExaminerId,
        });

        currentLoads.set(lowestExaminerId, lowestLoad + 1);
        assignedCount++;
      }

      await queryClient.invalidateQueries({ queryKey: ['answer-books-all'] });
      await queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] });
      setAssignSuccess(`Successfully auto-assigned ${assignedCount} digital script(s) using load-balancing.`);
      setSelectedBookId(null);
    } catch (err: any) {
      setAssignError(err.response?.data?.message || 'Error occurred during auto-assignment sequence.');
    } finally {
      setIsAutoAssigning(false);
      setAutoAssignProgress(null);
    }
  };

  // Determine current active workflow step (1 to 4)
  const currentStep = !selectedExamId && exams.length > 0 ? 1 : !selectedBookId ? 2 : !selectedExaminerId ? 3 : 4;

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Control Center · Allocation Workflow</div>
          <h1 className="page-header__title">Examiner Assignment</h1>
          <p className="page-header__subtitle">
            Allocate unassigned digital scripts to accredited examiners. Follow the 4-step workflow or execute deterministic load balancing.
          </p>
        </div>
        <div className="page-header__actions" style={{ display: 'flex', gap: 'var(--space-3)' }}>
          <button
            className="btn btn-primary"
            disabled={assignableBooks.length === 0 || examiners.length === 0 || isAutoAssigning}
            onClick={handleAutoAssign}
            title="Deterministically balance unassigned scripts across accredited examiners"
          >
            {isAutoAssigning ? (autoAssignProgress || 'Auto Assigning…') : '⚡ Auto-Assign (Load-Balance)'}
          </button>
        </div>
      </div>

      {/* 4-Step Assignment Workflow Strip */}
      <div className="process-strip" style={{ marginBottom: 'var(--space-6)' }}>
        <div className={`process-step ${currentStep >= 1 ? 'process-step--active' : ''}`}>
          <div className="process-step__number">1</div>
          <div className="process-step__content">
            <div className="process-step__title">SELECT EXAMINATION</div>
            <div className="process-step__desc">
              {selectedExam ? selectedExam.subjectCode : 'All or specific exam'}
            </div>
          </div>
        </div>

        <div className={`process-step ${currentStep >= 2 ? 'process-step--active' : ''}`}>
          <div className="process-step__number">2</div>
          <div className="process-step__content">
            <div className="process-step__title">SELECT SCRIPT</div>
            <div className="process-step__desc">
              {selectedBook ? selectedBook.answerBookCode : `${assignableBooks.length} ready in queue`}
            </div>
          </div>
        </div>

        <div className={`process-step ${currentStep >= 3 ? 'process-step--active' : ''}`}>
          <div className="process-step__number">3</div>
          <div className="process-step__content">
            <div className="process-step__title">SELECT EXAMINER</div>
            <div className="process-step__desc">
              {selectedExaminer ? selectedExaminer.name : `${examiners.length} accredited`}
            </div>
          </div>
        </div>

        <div className={`process-step ${currentStep >= 4 ? 'process-step--active' : ''}`}>
          <div className="process-step__number">4</div>
          <div className="process-step__content">
            <div className="process-step__title">CONFIRM DOCKET</div>
            <div className="process-step__desc">
              {selectedBook && selectedExaminer ? 'Ready to allocate' : 'Awaiting selections'}
            </div>
          </div>
        </div>
      </div>

      {/* Status Alerts */}
      {assignError && (
        <div className="attention-item attention-item--critical" style={{ marginBottom: 'var(--space-4)' }}>
          <div className="attention-item__icon">⚠</div>
          <div className="attention-item__content">
            <div className="attention-item__title">Assignment Failed</div>
            <div className="attention-item__desc">{assignError}</div>
          </div>
        </div>
      )}

      {assignSuccess && (
        <div
          style={{
            padding: 'var(--space-3) var(--space-4)',
            background: 'var(--status-approved-bg)',
            border: '1px solid rgba(45,106,79,0.3)',
            borderRadius: 'var(--radius-sm)',
            fontSize: 'var(--text-body)',
            color: 'var(--status-approved-text)',
            marginBottom: 'var(--space-4)',
          }}
        >
          ✓ {assignSuccess}
        </div>
      )}

      {/* 4-Step Interactive Assignment Console */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 'var(--space-6)', marginBottom: 'var(--space-8)' }}>
        
        {/* Left Side: Step 1 (Filter) & Step 2 (Select Unassigned Script) */}
        <div className="folio-card" style={{ padding: 0 }}>
          <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span className="folio-card__title">Step 2: Unassigned Digital Scripts ({assignableBooks.length})</span>
              <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                Scripts verified and ready for examiner allocation (READY / RETURNED)
              </div>
            </div>
            
            {/* Step 1: Select Examination */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              <span className="label-caps" style={{ fontSize: 'var(--text-metadata)' }}>Step 1 Exam:</span>
              <select
                className="form-select"
                style={{ fontSize: 'var(--text-metadata)', padding: '4px 8px', width: 200 }}
                value={selectedExamId}
                onChange={(e) => {
                  setSelectedExamId(e.target.value);
                  setSelectedBookId(null);
                }}
              >
                <option value="">All Examinations</option>
                {exams.map((ex) => (
                  <option key={ex._id} value={ex._id}>
                    {ex.subjectCode} · {ex.title}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="folio-card__body" style={{ padding: 0 }}>
            {booksLoading ? (
              <div className="state-container"><div className="spinner" /></div>
            ) : assignableBooks.length === 0 ? (
              <div className="state-container" style={{ padding: 'var(--space-8)' }}>
                <div className="state-icon">✓</div>
                <div className="state-title">No Scripts Ready for Assignment</div>
                <div className="state-body">
                  All digital scripts for this examination cohort have already been allocated or are pending quality ingestion.
                </div>
              </div>
            ) : (
              <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th style={{ width: 44 }}>Select</th>
                      <th>Script Code</th>
                      <th>Student Code</th>
                      <th>Examination</th>
                      <th>Pages</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assignableBooks.map((ab) => {
                      const exam = typeof ab.examId === 'object' ? (ab.examId as unknown as Exam) : null;
                      const isSelected = selectedBookId === ab._id;

                      return (
                        <tr
                          key={ab._id}
                          style={{
                            cursor: 'pointer',
                            background: isSelected ? 'rgba(14, 26, 43, 0.06)' : undefined,
                          }}
                          onClick={() => setSelectedBookId(ab._id)}
                        >
                          <td style={{ textAlign: 'center' }}>
                            <input
                              type="radio"
                              name="selectedScript"
                              checked={isSelected}
                              onChange={() => setSelectedBookId(ab._id)}
                              style={{ accentColor: 'var(--parchment-navy)', cursor: 'pointer', width: 16, height: 16 }}
                            />
                          </td>
                          <td>
                            <span className="data-table__code">{ab.answerBookCode}</span>
                          </td>
                          <td>
                            <span className="label-mono" style={{ fontSize: 'var(--text-table)' }}>
                              {ab.studentCode}
                            </span>
                          </td>
                          <td>
                            {exam ? (
                              <div>
                                <div style={{ fontWeight: 600, fontSize: 'var(--text-table)' }}>{exam.title}</div>
                                <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                                  {exam.subjectCode}
                                </div>
                              </div>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td className="label-mono" style={{ fontSize: 'var(--text-table)' }}>{ab.pageCount}</td>
                          <td>
                            <StatusBadge status={ab.status} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right Side: Step 3 (Select Examiner) & Step 4 (Confirm Assignment) */}
        <div>
          <div className="folio-card">
            <div className="folio-card__header">
              <span className="folio-card__title">Assignment Docket</span>
            </div>
            <div className="folio-card__body">
              {/* Selected Script Summary */}
              <div style={{ marginBottom: 'var(--space-5)', padding: 'var(--space-3) var(--space-4)', background: 'var(--parchment-panel)', border: '1px solid var(--parchment-border)', borderRadius: 'var(--radius-sm)' }}>
                <div className="label-caps" style={{ marginBottom: 4, color: 'var(--text-muted)' }}>Step 2 · Selected Script</div>
                {selectedBook ? (
                  <div>
                    <div style={{ fontSize: 'var(--text-card-title)', fontWeight: 700, color: 'var(--text-primary)' }}>
                      {selectedBook.answerBookCode}
                    </div>
                    <div style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-secondary)', marginTop: 4 }}>
                      Student ID: <strong>{selectedBook.studentCode}</strong> · {selectedBook.pageCount} Pages
                    </div>
                  </div>
                ) : (
                  <div style={{ fontSize: 'var(--text-body)', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                    Select an unassigned script from the table on the left.
                  </div>
                )}
              </div>

              {/* Step 3: Select Examiner */}
              <div className="form-field" style={{ marginBottom: 'var(--space-5)' }}>
                <label className="form-label" style={{ fontSize: 'var(--text-body)', fontWeight: 600 }}>
                  Step 3 · Accredited Examiner <span className="required">*</span>
                </label>
                {examinersLoading ? (
                  <div style={{ fontSize: 'var(--text-body)', color: 'var(--text-muted)' }}>Loading examiners…</div>
                ) : examiners.length === 0 ? (
                  <div style={{ fontSize: 'var(--text-body)', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                    No accredited examiners registered in the database.
                  </div>
                ) : (
                  <select
                    className="form-select"
                    value={selectedExaminerId}
                    onChange={(e) => setSelectedExaminerId(e.target.value)}
                    style={{ fontSize: 'var(--text-body)', padding: '8px 12px' }}
                  >
                    <option value="">— Select qualified examiner —</option>
                    {examinerWorkload.map(({ examiner, activeLoad, capacityStatus }) => (
                      <option key={examiner._id} value={examiner._id}>
                        {examiner.name} ({activeLoad} active dockets · {capacityStatus})
                      </option>
                    ))}
                  </select>
                )}
                <div className="form-hint" style={{ fontSize: 'var(--text-metadata)' }}>
                  Workload capacity updates live upon allocation.
                </div>
              </div>

              {/* Step 4: Confirm Action */}
              <div style={{ marginTop: 'var(--space-6)' }}>
                <button
                  className="btn btn-primary"
                  style={{ width: '100%', justifyContent: 'center', padding: '10px 16px', fontSize: 'var(--text-body)' }}
                  disabled={!selectedBookId || !selectedExaminerId || assignMutation.isPending}
                  onClick={handleManualAssign}
                >
                  {assignMutation.isPending ? 'Confirming Assignment…' : 'Step 4 · Confirm Assignment'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* EXAMINER WORKLOAD ROSTER */}
      <div className="folio-card">
        <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="folio-card__title">Examiner Workload & Capacity Roster</span>
            <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
              Accredited examiners, active evaluation quotas, and available capacity
            </div>
          </div>
          <span className="label-mono" style={{ fontSize: 'var(--text-metadata)' }}>
            {examiners.length} Accredited Examiners
          </span>
        </div>

        <div className="folio-card__body" style={{ padding: 0 }}>
          {examinersLoading ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : examiners.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-6)' }}>
              <div className="state-body">No accredited examiners registered.</div>
            </div>
          ) : (
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Examiner</th>
                    <th>Assigned</th>
                    <th>In Progress</th>
                    <th>Completed</th>
                    <th>Active Load</th>
                    <th>Available Capacity</th>
                  </tr>
                </thead>
                <tbody>
                  {examinerWorkload.map(({ examiner, assignedCount, inProgressCount, completedCount, activeLoad, capacityStatus, capacityBadgeClass }) => (
                    <tr key={examiner._id}>
                      <td>
                        <div style={{ fontWeight: 600, fontSize: 'var(--text-table)' }}>{examiner.name}</div>
                        <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
                          {examiner.email}
                        </div>
                      </td>
                      <td className="label-mono" style={{ fontSize: 'var(--text-table)' }}>{assignedCount}</td>
                      <td
                        className="label-mono"
                        style={{
                          fontSize: 'var(--text-table)',
                          color: inProgressCount > 0 ? 'var(--status-review-text)' : 'inherit',
                          fontWeight: inProgressCount > 0 ? 700 : 400,
                        }}
                      >
                        {inProgressCount}
                      </td>
                      <td className="label-mono" style={{ fontSize: 'var(--text-table)' }}>{completedCount}</td>
                      <td className="label-mono" style={{ fontSize: 'var(--text-table)', fontWeight: 700 }}>
                        {activeLoad}
                      </td>
                      <td>
                        <span className={`status-badge ${capacityBadgeClass}`}>
                          {capacityStatus}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
