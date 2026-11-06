import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ShieldCheck, Lock, User, AlertCircle, ArrowRight } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export const Login: React.FC = () => {
  const { login, error, clearError, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [usernameOrEmail, setUsernameOrEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // If already authenticated, redirect to dashboard or intended route
  const from = (location.state as any)?.from?.pathname || '/';

  React.useEffect(() => {
    if (isAuthenticated) {
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, navigate, from]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!usernameOrEmail || !password) return;

    setIsSubmitting(true);
    try {
      await login({ username_or_email: usernameOrEmail, password });
      navigate(from, { replace: true });
    } catch {
      // Handled in context
    } finally {
      setIsSubmitting(false);
    }
  };

  const fillQuickCredentials = (u: string, p: string) => {
    clearError();
    setUsernameOrEmail(u);
    setPassword(p);
  };

  return (
    <div className="max-w-md mx-auto my-8">
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="bg-slate-900 p-6 text-white text-center">
          <div className="mx-auto w-12 h-12 rounded-xl bg-slate-800 flex items-center justify-center mb-3 border border-slate-700">
            <ShieldCheck className="w-6 h-6 text-emerald-400" />
          </div>
          <h2 className="text-xl font-bold tracking-tight">LedgerLine Access</h2>
          <p className="text-xs text-slate-400 mt-1">
            Authenticate to access role-governed financial controls
          </p>
        </div>

        {/* Form Body */}
        <div className="p-6">
          {error && (
            <div className="mb-5 p-3 rounded-lg bg-rose-50 border border-rose-200 flex items-start gap-2 text-rose-700 text-xs">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold">Authentication Error:</span> {error}
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Username or Email
              </label>
              <div className="relative">
                <User className="w-4 h-4 text-slate-400 absolute left-3 top-3 pointer-events-none" />
                <input
                  type="text"
                  value={usernameOrEmail}
                  onChange={(e) => {
                    clearError();
                    setUsernameOrEmail(e.target.value);
                  }}
                  required
                  placeholder="admin or holder@ledgerline.internal"
                  className="w-full pl-9 pr-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900 focus:bg-white transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Password
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-3 pointer-events-none" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => {
                    clearError();
                    setPassword(e.target.value);
                  }}
                  required
                  placeholder="••••••••••••"
                  className="w-full pl-9 pr-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900 focus:bg-white transition"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting || !usernameOrEmail || !password}
              className="w-full mt-2 py-2.5 px-4 rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-sm font-semibold flex items-center justify-center gap-2 transition shadow-xs"
            >
              {isSubmitting ? (
                <span>Verifying credentials...</span>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          {/* Quick Development Role Fillers */}
          <div className="mt-8 pt-6 border-t border-slate-100">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Local Dev Quick-Fill Accounts
              </span>
              <span className="text-[10px] bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded border border-amber-200 font-mono">
                Development
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => fillQuickCredentials('admin', 'Admin_SecPass_2026!')}
                className="p-2 text-left rounded-lg border border-slate-200 hover:border-slate-400 hover:bg-slate-50 transition"
              >
                <div className="text-xs font-bold text-slate-900">Admin</div>
                <div className="text-[10px] text-slate-500">Full RBAC</div>
              </button>

              <button
                type="button"
                onClick={() => fillQuickCredentials('holder', 'Holder_SecPass_2026!')}
                className="p-2 text-left rounded-lg border border-slate-200 hover:border-slate-400 hover:bg-slate-50 transition"
              >
                <div className="text-xs font-bold text-slate-900">Holder</div>
                <div className="text-[10px] text-slate-500">Account Holder</div>
              </button>

              <button
                type="button"
                onClick={() => fillQuickCredentials('auditor', 'Auditor_SecPass_2026!')}
                className="p-2 text-left rounded-lg border border-slate-200 hover:border-slate-400 hover:bg-slate-50 transition"
              >
                <div className="text-xs font-bold text-slate-900">Auditor</div>
                <div className="text-[10px] text-slate-500">Read-Only</div>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
