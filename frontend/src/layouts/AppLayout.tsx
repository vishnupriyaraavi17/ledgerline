import React from 'react';
import { Outlet, NavLink, Link, useNavigate } from 'react-router-dom';
import {
  ShieldCheck,
  BookOpen,
  Layers,
  ArrowLeftRight,
  FileText,
  FileSpreadsheet,
  Users,
  LogIn,
  LogOut,
  User as UserIcon,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export const AppLayout: React.FC = () => {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const getRoleDisplayName = (role?: string) => {
    switch (role) {
      case 'admin':
        return 'Administrator';
      case 'auditor':
        return 'Auditor';
      case 'account_holder':
        return 'Account Holder';
      default:
        return 'Customer';
    }
  };

  return (
    <div className="min-h-screen bg-[#F1F4EF] text-[#1D2B27] flex flex-col font-sans">
      {/* Top Professional Header */}
      <header className="border-b border-[#E3E9E2] bg-white sticky top-0 z-30 shadow-xs app-header print:hidden">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Branding */}
            <Link to="/" className="flex items-center gap-3 hover:opacity-90 transition">
              <div className="h-9 w-9 rounded-xl bg-[#245344] flex items-center justify-center text-white shadow-xs">
                <ShieldCheck className="h-5 w-5 text-[#DCE9DF]" />
              </div>
              <div>
                <span className="text-lg font-serif font-bold tracking-tight text-[#1D2B27]">
                  LedgerLine
                </span>
                <p className="text-[11px] text-[#6D7C73] hidden sm:block font-normal">
                  Precision financial custody &amp; trust
                </p>
              </div>
            </Link>

            {/* User Session Profile & Controls */}
            <div className="flex items-center gap-3">
              {isAuthenticated && user ? (
                <div className="flex items-center gap-2 pl-2">
                  <div className="flex items-center gap-2 px-3 py-1.5 bg-[#F1F4EF] border border-[#E3E9E2] rounded-xl">
                    <div className="w-6 h-6 rounded-lg bg-[#DCE9DF] text-[#245344] flex items-center justify-center">
                      <UserIcon className="w-3.5 h-3.5" />
                    </div>
                    <div className="text-left">
                      <div className="text-xs font-semibold text-[#1D2B27] leading-tight">
                        {user.username}
                      </div>
                      <span className="text-[9px] uppercase tracking-wider font-bold text-[#245344]">
                        {getRoleDisplayName(user.role)}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={handleLogout}
                    title="Sign Out"
                    className="p-2 text-[#6D7C73] hover:text-[#9B5540] hover:bg-[#F5E9DF] rounded-xl transition cursor-pointer"
                  >
                    <LogOut className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <Link
                  to="/login"
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#245344] text-white text-xs font-semibold hover:bg-[#1B3F34] transition shadow-xs"
                >
                  <LogIn className="w-3.5 h-3.5" />
                  <span>Sign In</span>
                </Link>
              )}
            </div>
          </div>

          {/* Navigation Bar */}
          <nav className="flex space-x-1 sm:space-x-2 border-t border-[#E3E9E2]/70 py-2 overflow-x-auto">
            <NavLink
              to="/"
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition inline-flex items-center gap-1.5 ${
                  isActive
                    ? 'bg-[#245344] text-white shadow-xs'
                    : 'text-[#6D7C73] hover:text-[#1D2B27] hover:bg-[#DCE9DF]/50'
                }`
              }
            >
              <Layers className="w-4 h-4" />
              <span>Dashboard</span>
            </NavLink>

            <NavLink
              to="/accounts"
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition inline-flex items-center gap-1.5 ${
                  isActive
                    ? 'bg-[#245344] text-white shadow-xs'
                    : 'text-[#6D7C73] hover:text-[#1D2B27] hover:bg-[#DCE9DF]/50'
                }`
              }
            >
              <BookOpen className="w-4 h-4" />
              <span>Accounts</span>
            </NavLink>

            <NavLink
              to="/transfers"
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition inline-flex items-center gap-1.5 ${
                  isActive
                    ? 'bg-[#245344] text-white shadow-xs'
                    : 'text-[#6D7C73] hover:text-[#1D2B27] hover:bg-[#DCE9DF]/50'
                }`
              }
            >
              <ArrowLeftRight className="w-4 h-4" />
              <span>{user?.role === 'account_holder' ? 'Transfers' : 'Transaction History'}</span>
            </NavLink>

            <NavLink
              to="/statements"
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition inline-flex items-center gap-1.5 ${
                  isActive
                    ? 'bg-[#245344] text-white shadow-xs'
                    : 'text-[#6D7C73] hover:text-[#1D2B27] hover:bg-[#DCE9DF]/50'
                }`
              }
            >
              <FileSpreadsheet className="w-4 h-4" />
              <span>Statements</span>
            </NavLink>

            {(user?.role === 'admin' || user?.role === 'auditor') && (
              <NavLink
                to="/audit"
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition inline-flex items-center gap-1.5 ${
                    isActive
                      ? 'bg-[#245344] text-white shadow-xs'
                      : 'text-[#6D7C73] hover:text-[#1D2B27] hover:bg-[#DCE9DF]/50'
                  }`
                }
              >
                <FileText className="w-4 h-4" />
                <span>Audit Trail</span>
              </NavLink>
            )}

            {(user?.role === 'admin' || user?.role === 'auditor') && (
              <NavLink
                to="/users"
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition inline-flex items-center gap-1.5 ${
                    isActive
                      ? 'bg-[#245344] text-white shadow-xs'
                      : 'text-[#6D7C73] hover:text-[#1D2B27] hover:bg-[#DCE9DF]/50'
                  }`
                }
              >
                <Users className="w-4 h-4" />
                <span>{user?.role === 'admin' ? 'User Management' : 'User Directory'}</span>
              </NavLink>
            )}
          </nav>
        </div>
      </header>

      {/* Main Content Container */}
      <main className="app-main flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 print:max-w-none print:p-0 print:m-0">
        <Outlet />
      </main>

      {/* Institutional Banking Footer */}
      <footer className="app-footer border-t border-[#E3E9E2] bg-white py-5 text-xs text-[#6D7C73] print:hidden">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-[#1D2B27]">LedgerLine</span>
            <span>&copy; 2026 LedgerLine Financial Technologies. All rights reserved.</span>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-[#6D7C73]">
            <span className="w-2 h-2 rounded-full bg-[#245344]" />
            <span>Protected by immutable records &amp; tamper-evident audit trails.</span>
          </div>
        </div>
      </footer>
    </div>
  );
};
