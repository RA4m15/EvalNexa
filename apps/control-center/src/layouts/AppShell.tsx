import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const NAV_ITEMS = [
  { label: 'Dashboard', to: '/dashboard' },
  { label: 'Examinations', to: '/exams' },
  { label: 'Answer Books', to: '/answer-books' },
  { label: 'Scan & Quality', to: '/scan-center' },
  { label: 'Assignment', to: '/assignments' },
  { label: 'Live Monitoring', to: '/monitoring' },
  { label: 'Results', to: '/results' },
  { label: 'Users', to: '/users' },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div className="app-topbar__brand">
          <div className="app-topbar__logo">æ</div>
          <div className="app-topbar__identity">
            <span className="app-topbar__name">EvalNexa</span>
            <span className="app-topbar__sub">// Examination Intelligence</span>
          </div>
        </div>

        <nav className="app-topbar__nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="app-topbar__right">
          <div className="app-topbar__user">
            <span>{user?.name}</span>
            <span className="app-topbar__role-badge">{user?.role}</span>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={handleLogout}>
            Sign Out
          </button>
        </div>
      </header>

      <div className="app-content">
        {/* Watermark */}
        <div className="watermark-overlay" aria-hidden="true">
          <svg width="700" height="700" viewBox="0 0 400 400" fill="none">
            <circle cx="200" cy="200" r="190" stroke="currentColor" strokeDasharray="2 3" strokeWidth="0.75" />
            <circle cx="200" cy="200" r="165" stroke="currentColor" strokeWidth="1.25" />
            <circle cx="200" cy="200" r="135" stroke="currentColor" strokeDasharray="6 4" strokeWidth="0.5" />
            <circle cx="200" cy="200" r="85" stroke="currentColor" strokeWidth="0.5" />
            <line x1="200" x2="200" y1="5" y2="395" stroke="currentColor" strokeWidth="0.5" />
            <line x1="5" x2="395" y1="200" y2="200" stroke="currentColor" strokeWidth="0.5" />
          </svg>
        </div>
        <main className="app-main">{children}</main>
      </div>
    </div>
  );
}
