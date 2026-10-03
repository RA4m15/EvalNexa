import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { User, UserRole } from '@evalnexa/types';

interface CreateUserForm {
  name: string;
  email: string;
  password: string;
  role: UserRole | '';
}

const EMPTY_FORM: CreateUserForm = {
  name: '',
  email: '',
  password: '',
  role: '',
};

const ROLES: UserRole[] = ['EXAMINER', 'MODERATOR'];

export function UsersPage() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<CreateUserForm>(EMPTY_FORM);
  const [formError, setFormError] = useState('');
  const [roleFilter, setRoleFilter] = useState('');

  const { data: users = [], isLoading, isError } = useQuery<User[]>({
    queryKey: ['users', roleFilter],
    queryFn: async () => {
      const { data } = await apiClient.get('/users');
      const list = data.data as User[];
      return roleFilter ? list.filter((u) => u.role === roleFilter) : list;
    },
  });

  const createMutation = useMutation({
    mutationFn: async (payload: object) => {
      const { data } = await apiClient.post('/users', payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['examiners'] });
      setShowModal(false);
      setForm(EMPTY_FORM);
      setFormError('');
    },
    onError: (err: unknown) => {
      const e = err as { response?: { data?: { message?: string } } };
      setFormError(e?.response?.data?.message || 'Failed to create user account');
    },
  });

  const toggleActiveMutation = useMutation({
    mutationFn: async ({ id, isActive }: { id: string; isActive: boolean }) => {
      await apiClient.patch(`/users/${id}`, { isActive });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['examiners'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    if (!form.role) {
      setFormError('Please select a designated role.');
      return;
    }
    if (form.password.length < 8) {
      setFormError('Password must be at least 8 characters.');
      return;
    }
    createMutation.mutate({ ...form });
  };

  const field = (key: keyof CreateUserForm) => ({
    value: form[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [key]: e.target.value })),
  });

  const roleCounts = {
    ADMIN: users.filter((u) => u.role === 'ADMIN').length,
    EXAMINER: users.filter((u) => u.role === 'EXAMINER').length,
    MODERATOR: users.filter((u) => u.role === 'MODERATOR').length,
  };

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Control Center · Access Governance</div>
          <h1 className="page-header__title">User Registry</h1>
          <p className="page-header__subtitle">
            Manage administrative, examiner, and moderator accounts with role-based access control. All actions are audit-logged.
          </p>
        </div>
        <div className="page-header__actions">
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>
            + Register New User
          </button>
        </div>
      </div>

      {/* Role Summary Cards (Prompt Section 21: Administrators, Examiners, Moderators) */}
      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)', marginBottom: 'var(--space-6)' }}>
        <div className="stat-card">
          <div className="stat-card__eyebrow">ADMINISTRATORS</div>
          <div className="stat-card__value">{isLoading ? '—' : roleCounts.ADMIN}</div>
          <div className="stat-card__sub">System governance & configuration</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow">EXAMINERS</div>
          <div className="stat-card__value">{isLoading ? '—' : roleCounts.EXAMINER}</div>
          <div className="stat-card__sub">Accredited script evaluators</div>
        </div>

        <div className="stat-card">
          <div className="stat-card__eyebrow">MODERATORS</div>
          <div className="stat-card__value">{isLoading ? '—' : roleCounts.MODERATOR}</div>
          <div className="stat-card__sub">Quality assurance & result certification</div>
        </div>
      </div>

      {/* User Accounts Folio Card */}
      <div className="folio-card">
        <div className="folio-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="folio-card__title">User Accounts ({users.length})</span>
            <div className="label-mono" style={{ fontSize: 'var(--text-metadata)', color: 'var(--text-muted)' }}>
              Accredited institutional credentials
            </div>
          </div>

          <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
            <span className="label-caps" style={{ fontSize: 'var(--text-metadata)' }}>Filter:</span>
            <select
              className="form-select"
              style={{ width: 180, fontSize: 'var(--text-metadata)', padding: '5px 10px' }}
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
            >
              <option value="">All Roles</option>
              {(['ADMIN', 'EXAMINER', 'MODERATOR'] as UserRole[]).map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="folio-card__body" style={{ padding: 0 }}>
          {isLoading ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : isError ? (
            <div className="state-container">
              <div className="state-title">Failed to load user accounts</div>
              <div className="state-body">Check connection to EvalNexa database services.</div>
              <button
                className="btn btn-secondary state-action"
                onClick={() => queryClient.invalidateQueries({ queryKey: ['users'] })}
              >
                Retry
              </button>
            </div>
          ) : users.length === 0 ? (
            <div className="state-container" style={{ padding: 'var(--space-10)' }}>
              <div className="state-icon">👤</div>
              <div className="state-title">No Users Found</div>
              <div className="state-body">
                {roleFilter ? `No users with role "${roleFilter}" exist.` : 'No accounts registered yet.'}
              </div>
              {!roleFilter && (
                <div className="state-action">
                  <button className="btn btn-primary" onClick={() => setShowModal(true)}>
                    + Register First User
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="data-table-wrap" style={{ border: 'none', margin: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user._id}>
                      <td>
                        <div style={{ fontWeight: 600, fontSize: 'var(--text-table)' }}>{user.name}</div>
                      </td>
                      <td>
                        <span className="label-mono" style={{ fontSize: 'var(--text-metadata)' }}>{user.email}</span>
                      </td>
                      <td>
                        <span
                          className={`status-badge ${
                            user.role === 'ADMIN'
                              ? 'status-badge--finalized'
                              : user.role === 'EXAMINER'
                              ? 'status-badge--assigned'
                              : 'status-badge--review'
                          }`}
                        >
                          {user.role}
                        </span>
                      </td>
                      <td>
                        <span className={`status-badge ${user.isActive ? 'status-badge--approved' : 'status-badge--returned'}`}>
                          {user.isActive ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="label-mono" style={{ fontSize: 'var(--text-metadata)' }}>
                        {new Date(user.createdAt).toLocaleDateString()}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {user.role !== 'ADMIN' && (
                          <button
                            className={`btn btn-sm ${user.isActive ? 'btn-secondary' : 'btn-primary'}`}
                            onClick={() => toggleActiveMutation.mutate({ id: user._id, isActive: !user.isActive })}
                            disabled={toggleActiveMutation.isPending}
                          >
                            {user.isActive ? 'Deactivate' : 'Activate'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Create User Modal */}
      {showModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowModal(false)}>
          <div className="modal">
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow">User Management</div>
                <div className="modal__title">Register New User Account</div>
              </div>
              <button className="modal__close" onClick={() => setShowModal(false)}>✕</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal__body">
                <div className="form-grid" style={{ marginBottom: 'var(--space-4)' }}>
                  <div className="form-field form-field--full">
                    <label className="form-label">Full Name <span className="required">*</span></label>
                    <input className="form-input" placeholder="e.g., Dr. Sarah Mitchell" required {...field('name')} />
                  </div>
                  <div className="form-field form-field--full">
                    <label className="form-label">Institutional Email <span className="required">*</span></label>
                    <input className="form-input" type="email" placeholder="e.g., s.mitchell@institution.edu" required {...field('email')} />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Role <span className="required">*</span></label>
                    <select
                      className="form-select"
                      value={form.role}
                      onChange={(e) => setForm((f) => ({ ...f, role: e.target.value as UserRole }))}
                      required
                    >
                      <option value="">— Select role —</option>
                      {ROLES.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-field">
                    <label className="form-label">Initial Password <span className="required">*</span></label>
                    <input
                      className="form-input"
                      type="password"
                      placeholder="Minimum 8 characters"
                      required
                      minLength={8}
                      {...field('password')}
                    />
                  </div>
                </div>

                {formError && (
                  <div className="attention-item attention-item--critical" style={{ marginTop: 'var(--space-3)' }}>
                    <div className="attention-item__icon">⚠</div>
                    <div className="attention-item__content">
                      <div className="attention-item__desc">{formError}</div>
                    </div>
                  </div>
                )}
              </div>

              <div className="modal__footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Registering…' : 'Register User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
