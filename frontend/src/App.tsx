import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { AppLayout } from './layouts/AppLayout';
import { Dashboard } from './pages/Dashboard';
import { Login } from './pages/Login';
import { UsersPage } from './pages/Users';
import { AccountsPage } from './pages/Accounts';
import { TransfersPage } from './pages/Transfers';
import { StatementsPage } from './pages/Statements';
import { AuditTrailPage } from './pages/AuditTrail';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<AppLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="accounts" element={<AccountsPage />} />
            <Route path="transfers" element={<TransfersPage />} />
            <Route path="statements" element={<StatementsPage />} />
            <Route path="audit" element={<AuditTrailPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

