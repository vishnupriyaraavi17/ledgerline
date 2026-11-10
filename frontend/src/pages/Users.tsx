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
      <div className="bg-white rounded-2xl p-8 border border-[#E8EBE6] text-center max-w-lg mx-auto shadow-xs font-sans my-12">
        <div className="w-12 h-12 rounded-xl bg-[#FCF1E8] text-[#9B5540] flex items-center justify-center mx-auto mb-3">
          <ShieldAlert className="w-6 h-6" />
        </div>
        <h3 className="text-xl font-serif font-bold text-[#1D2B27]">Access Restricted</h3>
        <p className="text-xs text-[#6D7C73] mt-2 leading-relaxed">
          Your role is <strong className="text-[#1D2B27]">Account Holder</strong>. Identity administration and user directory access are strictly reserved for Administrator and Auditor roles.
        </p>
      </div>
    );
  }

  const roleBadge = (role: UserRole) => {
    switch (role) {
      case 'admin':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[#E9E2EF] text-[#553C7B] border border-[#D5C7DE]">
            Admin
          </span>
        );
      case 'auditor':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[#F5E9DF] text-[#9B5540] border border-[#E8D5C4]">
            Auditor (Read-Only)
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[#DCE9DF] text-[#245344] border border-[#C5D9C9]">
            Account Holder
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 font-sans">
      {/* Top Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-6 rounded-2xl border border-[#E3E9E2] shadow-xs">
        <div className="flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-[#245344] flex items-center justify-center text-white shadow-xs">
            <UsersIcon className="w-5 h-5 text-[#DCE9DF]" />
          </div>
          <div>
            <h1 className="text-xl font-serif font-bold text-[#1D2B27]">User Management</h1>
            <p className="text-xs text-[#6D7C73] mt-0.5">
              View and manage registered user accounts and their assigned roles ({total} registered)
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchUsers}
            disabled={loading}
            className="p-2.5 rounded-xl border border-[#E3E9E2] hover:bg-[#F1F4EF] text-[#6D7C73] transition cursor-pointer"
            title="Refresh user roster"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-[#245344]' : ''}`} />
          </button>

          {user?.role === 'admin' ? (
            <button
              onClick={() => {
                setFormError(null);
                setShowModal(true);
              }}
              className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-[#245344] hover:bg-[#1B3F34] text-white text-xs font-semibold shadow-xs transition cursor-pointer"
            >
              <UserPlus className="w-3.5 h-3.5 text-[#DCE9DF]" />
              <span>Add User</span>
            </button>
          ) : (
            <div className="text-[11px] font-medium text-[#6D7C73] bg-[#F1F4EF] px-3 py-1.5 rounded-xl border border-[#E3E9E2] flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-[#245344]" />
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
      <div className="bg-white rounded-2xl border border-[#E3E9E2] shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-[#E3E9E2] text-left text-xs">
            <thead className="bg-[#F1F4EF] text-[#6D7C73] font-semibold uppercase tracking-wider">
              <tr>
                <th scope="col" className="px-4 py-3">UUID</th>
                <th scope="col" className="px-4 py-3">Username</th>
                <th scope="col" className="px-4 py-3">Email</th>
                <th scope="col" className="px-4 py-3">Role</th>
                <th scope="col" className="px-4 py-3">Status</th>
                <th scope="col" className="px-4 py-3">Registered At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E3E9E2] bg-white">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-[#6D7C73]">
                    Loading directory...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-[#6D7C73]">
                    No users found.
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="hover:bg-[#F1F4EF]/50 transition">
                    <td className="px-4 py-3 font-mono text-[11px] text-[#6D7C73]">
                      {u.id.substring(0, 8)}...
                    </td>
                    <td className="px-4 py-3 font-semibold text-[#1D2B27]">
                      {u.username}
                    </td>
                    <td className="px-4 py-3 text-[#6D7C73] font-mono text-[11px]">
                      {u.email}
                    </td>
                    <td className="px-4 py-3">
                      {roleBadge(u.role)}
                    </td>
                    <td className="px-4 py-3">
                      {u.is_active ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#245344]">
                          <span className="w-1.5 h-1.5 rounded-full bg-[#245344]"></span>
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-rose-700">
                          <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                          Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-[#6D7C73] font-mono text-[11px]">
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 font-sans">
          <div className="bg-white rounded-2xl shadow-xl border border-[#E3E9E2] max-w-md w-full overflow-hidden">
            <div className="p-5 border-b border-[#E3E9E2] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <KeyRound className="w-4 h-4 text-[#245344]" />
                <h3 className="font-serif font-bold text-[#1D2B27] text-base">Add New User</h3>
              </div>
              <button
                onClick={() => setShowModal(false)}
                className="text-[#6D7C73] hover:text-[#1D2B27] p-1 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateUser} className="p-5 space-y-4">
              {formError && (
                <div className="p-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-600" />
                  <span>{formError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1">
                  Username
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. jdoe_ops"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-[#F1F4EF] border border-[#E3E9E2] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#245344] focus:bg-white text-[#1D2B27]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1">
                  Email Address
                </label>
                <input
                  type="email"
                  required
                  placeholder="e.g. jdoe@ledgerline.internal"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-[#F1F4EF] border border-[#E3E9E2] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#245344] focus:bg-white text-[#1D2B27]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1">
                  Password
                </label>
                <input
                  type="password"
                  required
                  placeholder="Min 8 characters"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-[#F1F4EF] border border-[#E3E9E2] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#245344] focus:bg-white text-[#1D2B27]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1">
                  Assigned Role
                </label>
                <select
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value as UserRole })}
                  className="w-full px-3 py-2 text-xs bg-[#F1F4EF] border border-[#E3E9E2] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#245344] focus:bg-white text-[#1D2B27]"
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
                  className="px-3.5 py-2 text-xs font-semibold text-[#6D7C73] hover:bg-[#F1F4EF] rounded-xl transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 text-xs font-semibold text-white bg-[#245344] hover:bg-[#1B3F34] disabled:opacity-50 rounded-xl shadow-xs transition cursor-pointer"
                >
                  {isSubmitting ? 'Adding User...' : 'Add User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
