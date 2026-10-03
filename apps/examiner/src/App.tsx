import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AppShell } from './layouts/AppShell';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { PapersPage } from './pages/PapersPage';
import { EvaluationWorkspacePage } from './pages/EvaluationWorkspacePage';
import { AnalyticsPage } from './pages/AnalyticsPage';

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/*" element={
        <ProtectedRoute allowedRoles={['EXAMINER']}>
          <AppShell>
            <Routes>
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="papers" element={<PapersPage />} />
              <Route path="queue" element={<PapersPage />} />
              <Route path="analytics" element={<AnalyticsPage />} />
              <Route path="papers/:id" element={<EvaluationWorkspacePage />} />
              <Route path="evaluate/:id" element={<EvaluationWorkspacePage />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </AppShell>
        </ProtectedRoute>
      } />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
