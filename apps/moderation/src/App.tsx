import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AppShell } from './layouts/AppShell';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { ReviewQueuePage } from './pages/ReviewQueuePage';
import { ReviewDetailPage } from './pages/ReviewDetailPage';
import { ReviewDeskRedirect } from './pages/ReviewDeskRedirect';
import { IntegrityPage } from './pages/IntegrityPage';
import { HistoryPage } from './pages/HistoryPage';

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute allowedRoles={['MODERATOR', 'ADMIN']}>
            <AppShell>
              <Routes>
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="dashboard" element={<DashboardPage />} />
                <Route path="queue" element={<ReviewQueuePage />} />
                <Route path="desk" element={<ReviewDeskRedirect />} />
                <Route path="review" element={<ReviewDeskRedirect />} />
                <Route path="review/:id" element={<ReviewDetailPage />} />
                <Route path="integrity" element={<IntegrityPage />} />
                <Route path="history" element={<HistoryPage />} />
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
