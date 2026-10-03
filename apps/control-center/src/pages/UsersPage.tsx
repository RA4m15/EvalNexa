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
  name: '', email: '', password: '', role: '',
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
      setFormError(e?.response?.data?.message || 'Failed to create user');
    },
  });

  const toggleActiveMutation = useMutation({
    mutationFn: async ({ id, isActive }: { id: string; isActive: boolean }) => {
      await apiClient.patch(`/users/${id}`, { isActive });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    if (!form.role) { setFormError('Please select a role.'); return; }
    if (form.password.length < 8) { setFormError('Password must be at least 8 characters.'); return; }
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
      <div className="page-header">
        <div className="page-header__eyebrow">Control Center · User Management</div>
        <h1 className="page-header__title">User Registry</h1>
        <p className="page-header__subtitle">
          Manage examiner and moderator accounts. All user actions are audit-logged.
        </p>
        <div className="page-header__actions">
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>
            + Register New User
          </button>
        </div>
      </div>

      {/* Role summary */}
      {!isLoading && (
        <div className="metric-grid" style={{ marginBottom: 'var(--space-8)' }}>
          {[
            { label: 'Administrators', count: roleCounts.ADMIN },
            { label: 'Examiners', count: roleCounts.EXAMINER },
            { label: 'Moderators', count: roleCounts.MODERATOR },
          ].map(({ label, count }) => (
            <div className="metric-card" key={label}>
              <div className="metric-card__label">{label}</div>
              <div className="metric-card__value">{count}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filter */}
      <div className="section-header" style={{ marginBottom: 'var(--space-4)' }}>
        <span className="section-header__title">User Accounts</span>
        <select
          className="form-select"
          style={{ width: 200 }}
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
        >
          <option value="">All Roles</option>
          {(['ADMIN', 'EXAMINER', 'MODERATOR'] as UserRole[]).map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="state-container"><div className="spinner" /></div>
      ) : isError ? (
        <div className="state-container">
          <div className="state-title">Failed to load users</div>
          <button className="btn btn-secondary state-action" onClick={() => queryClient.invalidateQueries({ queryKey: ['users'] })}>Retry</button>
        </div>
      ) : users.length === 0 ? (
        <div className="state-container">
          <div className="state-icon">👤</div>
          <div className="state-title">No Users Found</div>
          <div className="state-body">
            {roleFilter ? `No users with role "${roleFilter}" exist.` : 'No users registered. Create the first examiner or moderator account.'}
          </div>
          {!roleFilter && (
            <div className="state-action">
              <button className="btn btn-primary" onClick={() => setShowModal(true)}>Register User</button>
            </div>
          )}
        </div>
      ) : (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user._id}>
                  <td>
                    <div style={{ fontWeight: 500 }}>{user.name}</div>
                  </td>
                  <td>
                    <span className="label-mono" style={{ fontSize: 11 }}>{user.email}</span>
                  </td>
                  <td>
                    <span className={`status-badge ${
                      user.role === 'ADMIN' ? 'status-badge--finalized' :
                      user.role === 'EXAMINER' ? 'status-badge--assigned' :
                      'status-badge--under_review'
                    }`}>
                      {user.role}
                    </span>
                  </td>
                  <td>
                    <span className={`status-badge ${user.isActive ? 'status-badge--approved' : 'status-badge--returned'}`}>
                      {user.isActive ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="label-mono" style={{ fontSize: 11 }}>
                    {new Date(user.createdAt).toLocaleDateString()}
                  </td>
                  <td>
                    {user.role !== 'ADMIN' && (
                      <button
                        className={`btn btn-sm ${user.isActive ? 'btn-secondary' : 'btn-ghost'}`}
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

      {/* Create User Modal */}
      {showModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowModal(false)}>
          <div className="modal">
            <div className="modal__header">
              <div>
                <div className="modal__eyebrow">User Registry</div>
                <div className="modal__title">Register New User Account</div>
              </div>
              <button className="modal__close" onClick={() => setShowModal(false)}>✕</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal__body">
                <div className="form-grid" style={{ marginBottom: 'var(--space-5)' }}>
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
                    <label className="form-label">Temporary Password <span className="required">*</span></label>
                    <input
                      className="form-input"
                      type="password"
                      placeholder="Minimum 8 characters"
                      required
                      minLength={8}
                      {...field('password')}
                    />
                    <div className="form-hint">User should change this after first login.</div>
                  </div>
                </div>
                {formError && (
                  <div className="form-error" style={{ padding: 'var(--space-3)', background: 'var(--status-returned-bg)', borderRadius: 'var(--radius-sm)' }}>
                    ⚠ {formError}
                  </div>
                )}
              </div>
              <div className="modal__footer">
                <button type="button" className="btn btn-secondary" onClick={() => { setShowModal(false); setForm(EMPTY_FORM); setFormError(''); }}>
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
