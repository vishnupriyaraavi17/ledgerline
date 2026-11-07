import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { AppLayout } from './layouts/AppLayout';
import { Dashboard } from './pages/Dashboard';
import { Login } from './pages/Login';
import { UsersPage } from './pages/Users';
import { AccountsPage } from './pages/Accounts';
import { TransfersPage } from './pages/Transfers';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="login" element={<Login />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="accounts" element={<AccountsPage />} />
            <Route path="transfers" element={<TransfersPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

