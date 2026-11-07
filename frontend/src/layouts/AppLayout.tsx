import React from 'react';
import { Outlet, NavLink, Link, useNavigate } from 'react-router-dom';
import { ShieldCheck, BookOpen, Layers, ArrowLeftRight, FileText, ExternalLink, Users, LogIn, LogOut, User as UserIcon } from 'lucide-react';
import { useHealth } from '../hooks/useHealth';
import { useAuth } from '../context/AuthContext';
import { HealthBadge } from '../components/HealthBadge';

export const AppLayout: React.FC = () => {
  const { data, loading, error, refetch } = useHealth(10000);
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-finance-bg text-finance-text flex flex-col font-sans">
      {/* Top Professional Header */}
      <header className="border-b border-finance-border bg-white sticky top-0 z-30 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Branding */}
            <Link to="/" className="flex items-center gap-3 hover:opacity-90 transition">
              <div className="h-9 w-9 rounded-lg bg-slate-900 flex items-center justify-center text-white shadow-sm">
                <ShieldCheck className="h-5 w-5 text-emerald-400" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold tracking-tight text-slate-900">LedgerLine</span>
                  <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                    Core RBAC
                  </span>
                </div>
                <p className="text-xs text-slate-500 hidden sm:block">
                  Money movement with a ledger you can prove
                </p>
              </div>
            </Link>

            {/* Subsystem Health Indicator & Auth Session Controls */}
            <div className="flex items-center gap-3">
              <div
                onClick={() => refetch()}
                className="cursor-pointer transition hover:opacity-85"
                title="Click to re-check system health"
              >
                <HealthBadge
                  status={data?.status}
                  loading={loading}
                  label={data?.database.status === 'connected' ? 'PostgreSQL Active' : error ? 'DB Disconnected' : undefined}
                />
              </div>

              <a
                href="http://127.0.0.1:8000/docs"
                target="_blank"
                rel="noreferrer"
                className="hidden md:inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 transition"
              >
                <span>Swagger</span>
                <ExternalLink className="w-3 h-3 text-slate-500" />
              </a>

              {/* User Session Badge / Action */}
              {isAuthenticated && user ? (
                <div className="flex items-center gap-2 pl-2 border-l border-slate-200">
                  <div className="flex items-center gap-2 px-2.5 py-1 bg-slate-50 border border-slate-200 rounded-lg">
                    <UserIcon className="w-3.5 h-3.5 text-slate-500" />
                    <div className="text-left">
                      <div className="text-xs font-bold text-slate-900 leading-none">
                        {user.username}
                      </div>
                      <span className="text-[9px] uppercase tracking-wider font-semibold text-indigo-600">
                        {user.role}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={handleLogout}
                    title="Sign Out (destroys in-memory access token)"
                    className="p-1.5 text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                  >
                    <LogOut className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <Link
                  to="/login"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 transition shadow-xs"
                >
                  <LogIn className="w-3.5 h-3.5" />
                  <span>Sign In</span>
                </Link>
              )}
            </div>
          </div>

          {/* Navigation Bar */}
          <nav className="flex space-x-1 sm:space-x-4 border-t border-slate-100 py-2 overflow-x-auto">
            <NavLink
              to="/"
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium transition inline-flex items-center gap-1.5 ${
                  isActive
                    ? 'bg-slate-900 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`
              }
            >
              <Layers className="w-4 h-4" />
              <span>Foundation Status</span>
            </NavLink>

            <NavLink
              to="/users"
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium transition inline-flex items-center gap-1.5 ${
                  isActive
                    ? 'bg-slate-900 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`
              }
            >
              <Users className="w-4 h-4" />
              <span>Identity & RBAC</span>
              <span className="text-[10px] bg-emerald-100 text-emerald-800 px-1 rounded font-semibold">Task 02</span>
            </NavLink>

            <NavLink
              to="/accounts"
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium transition inline-flex items-center gap-1.5 ${
                  isActive
                    ? 'bg-slate-900 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`
              }
            >
              <BookOpen className="w-4 h-4" />
              <span>Accounts</span>
              <span className="text-[10px] bg-emerald-100 text-emerald-800 px-1 rounded font-semibold">Task 03</span>
            </NavLink>

            <NavLink
              to="/transfers"
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium transition inline-flex items-center gap-1.5 ${
                  isActive
                    ? 'bg-slate-900 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`
              }
            >
              <ArrowLeftRight className="w-4 h-4" />
              <span>Transfers</span>
              <span className="text-[10px] bg-emerald-100 text-emerald-800 px-1 rounded font-semibold">Task 04</span>
            </NavLink>


            <span
              className="px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium text-slate-400 cursor-not-allowed inline-flex items-center gap-1.5"
              title="Append-only Immutable Statements will be implemented in a subsequent approved task."
            >
              <FileText className="w-4 h-4" />
              <span>Audit Ledger</span>
              <span className="text-[10px] bg-slate-100 px-1 rounded text-slate-400">Task 05</span>
            </span>
          </nav>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="border-t border-finance-border bg-white py-4 text-center text-xs text-slate-400">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>LedgerLine Financial Core &copy; 2026. Zero money created or lost.</span>
          <span className="font-mono text-[11px] text-slate-400">
            Environment: {data?.environment || 'development'} | Auth: In-Memory JWT (Argon2id)
          </span>
        </div>
      </footer>
    </div>
  );
};
