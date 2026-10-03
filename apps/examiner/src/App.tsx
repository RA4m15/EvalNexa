import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AppShell } from './layouts/AppShell';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { PapersPage } from './pages/PapersPage';
import { EvaluationWorkspacePage } from './pages/EvaluationWorkspacePage';
import { ActivityPage } from './pages/ActivityPage';
import { EvaluateRedirect } from './pages/EvaluateRedirect';

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute allowedRoles={['EXAMINER']}>
            <AppShell>
              <Routes>
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="dashboard" element={<DashboardPage />} />
                <Route path="papers" element={<PapersPage />} />
                <Route path="evaluate" element={<EvaluateRedirect />} />
                <Route path="evaluate/:id" element={<EvaluationWorkspacePage />} />
                <Route path="papers/:id" element={<EvaluationWorkspacePage />} />
                <Route path="activity" element={<ActivityPage />} />
                <Route path="analytics" element={<Navigate to="/activity" replace />} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Routes>
            </AppShell>
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
