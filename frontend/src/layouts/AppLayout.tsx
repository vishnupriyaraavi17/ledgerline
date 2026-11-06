import React from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import { ShieldCheck, BookOpen, Layers, ArrowLeftRight, FileText, ExternalLink } from 'lucide-react';
import { useHealth } from '../hooks/useHealth';
import { HealthBadge } from '../components/HealthBadge';

export const AppLayout: React.FC = () => {
  const { data, loading, error, refetch } = useHealth(10000);

  return (
    <div className="min-h-screen bg-finance-bg text-finance-text flex flex-col font-sans">
      {/* Top Professional Header */}
      <header className="border-b border-finance-border bg-white sticky top-0 z-30 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Branding */}
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-lg bg-slate-900 flex items-center justify-center text-white shadow-sm">
                <ShieldCheck className="h-5 w-5 text-emerald-400" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold tracking-tight text-slate-900">LedgerLine</span>
                  <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                    Foundation
                  </span>
                </div>
                <p className="text-xs text-slate-500 hidden sm:block">
                  Money movement with a ledger you can prove
                </p>
              </div>
            </div>

            {/* Subsystem Health Indicator & API Docs link */}
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
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 transition"
              >
                <span>API Docs</span>
                <ExternalLink className="w-3 h-3 text-slate-500" />
              </a>
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

            {/* Future Modules - Clearly marked as unbuilt per strict foundation scope */}
            <span
              className="px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium text-slate-400 cursor-not-allowed inline-flex items-center gap-1.5"
              title="Accounts & Balances module will be implemented in a subsequent approved task."
            >
              <BookOpen className="w-4 h-4" />
              <span>Accounts</span>
              <span className="text-[10px] bg-slate-100 px-1 rounded text-slate-400">Task 02</span>
            </span>

            <span
              className="px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium text-slate-400 cursor-not-allowed inline-flex items-center gap-1.5"
              title="Transfers & Idempotent Execution will be implemented in a subsequent approved task."
            >
              <ArrowLeftRight className="w-4 h-4" />
              <span>Transfers</span>
              <span className="text-[10px] bg-slate-100 px-1 rounded text-slate-400">Task 03</span>
            </span>

            <span
              className="px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium text-slate-400 cursor-not-allowed inline-flex items-center gap-1.5"
              title="Append-only Immutable Statements will be implemented in a subsequent approved task."
            >
              <FileText className="w-4 h-4" />
              <span>Audit Ledger</span>
              <span className="text-[10px] bg-slate-100 px-1 rounded text-slate-400">Task 04</span>
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
            Environment: {data?.environment || 'development'} | API: /api/v1
          </span>
        </div>
      </footer>
    </div>
  );
};
