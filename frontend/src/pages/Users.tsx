import React, { useState, useEffect } from 'react';
import { Shield, ShieldAlert, UserPlus, Users as UsersIcon, Check, X, RefreshCw, KeyRound, AlertCircle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { apiService } from '../services/api';
import type { User, UserCreateInput, UserRole } from '../types/auth';

export const UsersPage: React.FC = () => {
  const { user, isAuthenticated } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // New user form state
  const [showModal, setShowModal] = useState<boolean>(false);
  const [formData, setFormData] = useState<UserCreateInput>({
    username: '',
    email: '',
    password: '',
    role: 'account_holder',
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiService.listUsers(0, 50);
      setUsers(response.items);
      setTotal(response.total);
    } catch (err: any) {
      if (err.response?.status === 403) {
        setError('403 Forbidden: You do not have permission to view or manage users.');
      } else if (err.response?.status === 401) {
        setError('401 Unauthorized: Please sign in to access user administration.');
      } else {
        setError('Failed to load user roster.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated && (user?.role === 'admin' || user?.role === 'auditor')) {
      fetchUsers();
    } else {
      setLoading(false);
    }
  }, [isAuthenticated, user?.role]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (user?.role !== 'admin') {
      setFormError('403 Forbidden: Only Admin accounts can provision users.');
      return;
    }
    setFormError(null);
    setIsSubmitting(true);

    try {
      await apiService.createUser(formData);
      setSuccessMsg(`User '${formData.username}' provisioned successfully.`);
      setShowModal(false);
      setFormData({
        username: '',
        email: '',
        password: '',
        role: 'account_holder',
      });
      await fetchUsers();
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setFormError(typeof detail === 'string' ? detail : 'Failed to provision user.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Unauthenticated view
  if (!isAuthenticated) {
    return (
      <div className="bg-white rounded-xl p-8 border border-slate-200 text-center max-w-lg mx-auto shadow-xs">
        <ShieldAlert className="w-12 h-12 text-amber-500 mx-auto mb-3" />
        <h3 className="text-lg font-bold text-slate-900">Authentication Required</h3>
        <p className="text-xs text-slate-500 mt-1 mb-4">
          Identity management is restricted to authorized administrative and auditing personnel.
        </p>
        <a
          href="/login"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 transition"
        >
          Sign In Now
        </a>
      </div>
    );
  }

  // Account Holder blocked view (RBAC boundary)
  if (user?.role === 'account_holder') {
    return (
      <div className="bg-white rounded-xl p-8 border border-rose-200 text-center max-w-lg mx-auto shadow-xs">
        <div className="w-12 h-12 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center mx-auto mb-3">
          <ShieldAlert className="w-6 h-6" />
        </div>
        <h3 className="text-lg font-bold text-slate-900">403 Forbidden: RBAC Restriction</h3>
        <p className="text-xs text-slate-600 mt-2">
          Your role is <strong className="text-slate-900">Account Holder</strong>. Identity administration and user directory access are strictly reserved for <strong>Admin</strong> and <strong>Auditor</strong> roles.
        </p>
        <div className="mt-4 p-3 bg-slate-50 rounded-lg text-[11px] text-slate-500 text-left border border-slate-100">
          <div className="font-semibold text-slate-700 mb-1">Server-Side Permission Rule:</div>
          <code>require_role([UserRole.ADMIN, UserRole.AUDITOR])</code>
        </div>
      </div>
    );
  }

  const roleBadge = (role: UserRole) => {
    switch (role) {
      case 'admin':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
            Admin
          </span>
        );
      case 'auditor':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            Auditor (Read-Only)
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            Account Holder
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-slate-900 flex items-center justify-center text-white">
            <UsersIcon className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900">User Identity & RBAC Directory</h1>
            <p className="text-xs text-slate-500">
              Role-governed directory of authorized LedgerLine principals ({total} registered)
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchUsers}
            disabled={loading}
            className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600 transition"
            title="Refresh user roster"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>

          {user?.role === 'admin' ? (
            <button
              onClick={() => {
                setFormError(null);
                setShowModal(true);
              }}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shadow-xs transition"
            >
              <UserPlus className="w-3.5 h-3.5" />
              <span>Provision User</span>
            </button>
          ) : (
            <div className="text-[11px] font-medium text-slate-500 bg-slate-100 px-3 py-1.5 rounded-lg border border-slate-200 flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-blue-500" />
              <span>Auditor Mode (Read-Only)</span>
            </div>
          )}
        </div>
      </div>

      {successMsg && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-xs flex items-center gap-2">
          <Check className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {error && (
        <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-lg text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* User Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
            <thead className="bg-slate-50 text-slate-600 font-semibold uppercase tracking-wider">
              <tr>
                <th scope="col" className="px-4 py-3">UUID</th>
                <th scope="col" className="px-4 py-3">Username</th>
                <th scope="col" className="px-4 py-3">Email</th>
                <th scope="col" className="px-4 py-3">Role</th>
                <th scope="col" className="px-4 py-3">Status</th>
                <th scope="col" className="px-4 py-3">Registered At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                    Loading directory...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                    No users found.
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50 transition">
                    <td className="px-4 py-3 font-mono text-[11px] text-slate-500">
                      {u.id.substring(0, 8)}...
                    </td>
                    <td className="px-4 py-3 font-semibold text-slate-900">
                      {u.username}
                    </td>
                    <td className="px-4 py-3 text-slate-600 font-mono text-[11px]">
                      {u.email}
                    </td>
                    <td className="px-4 py-3">
                      {roleBadge(u.role)}
                    </td>
                    <td className="px-4 py-3">
                      {u.is_active ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-rose-700">
                          <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                          Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-500 font-mono text-[11px]">
                      {new Date(u.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Provision User Modal - Strictly restricted to Admin */}
      {showModal && user?.role === 'admin' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full overflow-hidden">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <KeyRound className="w-4 h-4 text-slate-700" />
                <h3 className="font-bold text-slate-900 text-sm">Provision New User Account</h3>
              </div>
              <button
                onClick={() => setShowModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateUser} className="p-5 space-y-4">
              {formError && (
                <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{formError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Username
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. jdoe_ops"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Email Address
                </label>
                <input
                  type="email"
                  required
                  placeholder="e.g. jdoe@ledgerline.internal"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Initial Password (Argon2id Hashed)
                </label>
                <input
                  type="password"
                  required
                  placeholder="Min 8 characters"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Assigned Role
                </label>
                <select
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value as UserRole })}
                  className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900 focus:bg-white"
                >
                  <option value="account_holder">Account Holder (Standard User)</option>
                  <option value="auditor">Auditor (Read-Only Compliance)</option>
                  <option value="admin">Admin (Full System Privilege)</option>
                </select>
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-50 rounded-lg shadow-xs"
                >
                  {isSubmitting ? 'Creating...' : 'Create Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
