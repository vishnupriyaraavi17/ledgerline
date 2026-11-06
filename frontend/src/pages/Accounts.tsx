import React, { useState, useEffect } from 'react';
import {
  BookOpen,
  PlusCircle,
  RefreshCw,
  AlertCircle,
  Check,
  X,
  Shield,
  ShieldAlert,
  Lock,
  Unlock,
  Archive,
  ListOrdered,
  Building,
  User as UserIcon,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { apiService } from '../services/api';
import type {
  Account,
  AccountCreateInput,
  AccountType,
  AccountStatus,
  LedgerEntry,
} from '../types/account';

export const AccountsPage: React.FC = () => {
  const { user, isAuthenticated } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Creation modal state
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [createData, setCreateData] = useState<AccountCreateInput>({
    name: '',
    account_type: 'customer_checking',
    currency: 'INR',
    owner_id: '',
  });
  const [createError, setCreateError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Lifecycle status modal state (Admin only)
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [statusAction, setStatusAction] = useState<AccountStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState<boolean>(false);

  // Ledger entries drawer/modal state
  const [ledgerAccount, setLedgerAccount] = useState<Account | null>(null);
  const [ledgerEntries, setLedgerEntries] = useState<LedgerEntry[]>([]);
  const [loadingLedger, setLoadingLedger] = useState<boolean>(false);
  const [ledgerError, setLedgerError] = useState<string | null>(null);

  const fetchAccounts = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiService.getAccounts(0, 50);
      setAccounts(response.items);
      setTotal(response.total);
    } catch (err: any) {
      if (err.response?.status === 401) {
        setError('401 Unauthorized: Please sign in to view accounts.');
      } else {
        setError('Failed to load accounts directory.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      fetchAccounts();
    } else {
      setLoading(false);
    }
  }, [isAuthenticated, user?.role]);

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    if (user?.role === 'auditor') {
      setCreateError('403 Forbidden: Auditors cannot provision accounts.');
      return;
    }
    setCreateError(null);
    setIsSubmitting(true);

    try {
      const payload: AccountCreateInput = {
        name: createData.name.trim(),
        account_type: createData.account_type,
        currency: 'INR',
      };
      if (user?.role === 'admin' && createData.owner_id?.trim()) {
        payload.owner_id = createData.owner_id.trim();
      }

      const created = await apiService.createAccount(payload);
      setSuccessMsg(`Account '${created.account_number}' (${created.name}) provisioned at ₹0.00 balance.`);
      setShowCreateModal(false);
      setCreateData({
        name: '',
        account_type: 'customer_checking',
        currency: 'INR',
        owner_id: '',
      });
      await fetchAccounts();
      setTimeout(() => setSuccessMsg(null), 5000);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setCreateError(typeof detail === 'string' ? detail : 'Failed to provision account.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStatusChange = async (account: Account, newStatus: AccountStatus) => {
    if (user?.role !== 'admin') {
      setError('403 Forbidden: Only administrators can update account status.');
      return;
    }
    setStatusError(null);
    setIsUpdatingStatus(true);

    try {
      await apiService.updateAccountStatus(account.id, newStatus);
      setSuccessMsg(`Account ${account.account_number} transitioned to '${newStatus}'.`);
      setSelectedAccount(null);
      setStatusAction(null);
      await fetchAccounts();
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setStatusError(typeof detail === 'string' ? detail : 'Failed to update account status.');
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const handleViewLedger = async (account: Account) => {
    setLedgerAccount(account);
    setLoadingLedger(true);
    setLedgerError(null);
    try {
      const res = await apiService.getAccountLedger(account.id, 0, 50);
      setLedgerEntries(res.items);
    } catch (err: any) {
      if (err.response?.status === 404) {
        setLedgerError('404 Not Found: Account entries inaccessible or account does not exist.');
      } else {
        setLedgerError('Failed to retrieve ledger entries.');
      }
    } finally {
      setLoadingLedger(false);
    }
  };

  // Unauthenticated view
  if (!isAuthenticated) {
    return (
      <div className="bg-white rounded-xl p-8 border border-slate-200 text-center max-w-lg mx-auto shadow-xs">
        <ShieldAlert className="w-12 h-12 text-amber-500 mx-auto mb-3" />
        <h3 className="text-lg font-bold text-slate-900">Authentication Required</h3>
        <p className="text-xs text-slate-500 mt-1 mb-4">
          Financial accounts and double-entry ledger records require an authenticated session.
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

  const statusBadge = (status: AccountStatus) => {
    switch (status) {
      case 'active':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            Active
          </span>
        );
      case 'frozen':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
            Frozen
          </span>
        );
      case 'closed':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
            Closed
          </span>
        );
    }
  };

  const typeBadge = (type: AccountType) => {
    switch (type) {
      case 'system_reserve':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
            <Building className="w-3 h-3" />
            System Reserve
          </span>
        );
      case 'internal_clearing':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
            <Building className="w-3 h-3" />
            Internal Clearing
          </span>
        );
      case 'customer_savings':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            Savings
          </span>
        );
      case 'customer_checking':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-cyan-50 text-cyan-700 border border-cyan-200">
            Checking
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-slate-900 flex items-center justify-center text-white">
            <BookOpen className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-slate-900">Financial Accounts Foundation</h1>
              <span className="text-[10px] bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded font-semibold">
                Task 03
              </span>
            </div>
            <p className="text-xs text-slate-500">
              {user?.role === 'account_holder'
                ? `Personal customer accounts (${total} active)`
                : `System-wide financial accounts directory (${total} registered)`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchAccounts}
            disabled={loading}
            className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600 transition"
            title="Refresh accounts directory"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>

          {user?.role !== 'auditor' ? (
            <button
              onClick={() => {
                setCreateError(null);
                setShowCreateModal(true);
              }}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shadow-xs transition"
            >
              <PlusCircle className="w-3.5 h-3.5 text-emerald-400" />
              <span>Open Customer Account</span>
            </button>
          ) : (
            <div className="text-[11px] font-medium text-slate-500 bg-slate-100 px-3 py-1.5 rounded-lg border border-slate-200 flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-blue-500" />
              <span>Auditor Mode (Read-Only)</span>
            </div>
          )}
        </div>
      </div>

      {/* Task 03 Invariant Alert */}
      <div className="p-3.5 bg-blue-50/60 border border-blue-200 rounded-xl text-blue-900 text-xs flex items-start gap-3">
        <Building className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
        <div className="space-y-0.5">
          <span className="font-semibold text-blue-950">Zero Financial Postings Foundation:</span>
          <p className="text-blue-800/90 text-[11px]">
            Every account is initialized at strictly ₹0.00 INR via database-side defaults.
            Direct balance updates, opening balance credits, and runtime ledger postings are strictly prohibited at the database engine level.
          </p>
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

      {/* Accounts Directory Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
            <thead className="bg-slate-50 text-slate-600 font-semibold uppercase tracking-wider">
              <tr>
                <th scope="col" className="px-4 py-3">Account Number</th>
                <th scope="col" className="px-4 py-3">Account Name</th>
                <th scope="col" className="px-4 py-3">Type</th>
                <th scope="col" className="px-4 py-3">Currency & Balance</th>
                <th scope="col" className="px-4 py-3">Status</th>
                {user?.role !== 'account_holder' && (
                  <th scope="col" className="px-4 py-3">Owner Principal</th>
                )}
                <th scope="col" className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                    Loading accounts...
                  </td>
                </tr>
              ) : accounts.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                    No accounts found. Use 'Open Customer Account' to provision a new account.
                  </td>
                </tr>
              ) : (
                accounts.map((acc) => (
                  <tr key={acc.id} className="hover:bg-slate-50 transition">
                    <td className="px-4 py-3 font-mono text-xs font-semibold text-slate-900">
                      {acc.account_number}
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-800">
                      {acc.name}
                    </td>
                    <td className="px-4 py-3">
                      {typeBadge(acc.account_type)}
                    </td>
                    <td className="px-4 py-3 font-mono">
                      <span className="font-semibold text-slate-900">
                        ₹{Number(acc.balance).toFixed(2)}
                      </span>
                      <span className="text-[10px] text-slate-400 ml-1 font-sans uppercase">
                        {acc.currency}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {statusBadge(acc.status)}
                    </td>
                    {user?.role !== 'account_holder' && (
                      <td className="px-4 py-3 text-slate-500 font-mono text-[11px]">
                        {acc.owner_id ? (
                          <span className="inline-flex items-center gap-1">
                            <UserIcon className="w-3 h-3 text-slate-400" />
                            {acc.owner_id.substring(0, 8)}...
                          </span>
                        ) : (
                          <span className="text-[10px] font-semibold text-purple-600">
                            Root / System
                          </span>
                        )}
                      </td>
                    )}
                    <td className="px-4 py-3 text-right space-x-1.5 whitespace-nowrap">
                      {/* View Ledger Button */}
                      <button
                        onClick={() => handleViewLedger(acc)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-md transition"
                        title="View ledger entries"
                      >
                        <ListOrdered className="w-3 h-3" />
                        <span>Ledger</span>
                      </button>

                      {/* Admin Lifecycle Controls */}
                      {user?.role === 'admin' && acc.status !== 'closed' && (
                        <>
                          {acc.status === 'active' && (
                            <button
                              onClick={() => {
                                setSelectedAccount(acc);
                                setStatusAction('frozen');
                              }}
                              className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-md transition"
                              title="Freeze account"
                            >
                              <Lock className="w-3 h-3" />
                              <span>Freeze</span>
                            </button>
                          )}

                          {acc.status === 'frozen' && (
                            <button
                              onClick={() => {
                                setSelectedAccount(acc);
                                setStatusAction('active');
                              }}
                              className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-md transition"
                              title="Unfreeze account"
                            >
                              <Unlock className="w-3 h-3" />
                              <span>Unfreeze</span>
                            </button>
                          )}

                          <button
                            onClick={() => {
                              setSelectedAccount(acc);
                              setStatusAction('closed');
                            }}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded-md transition"
                            title="Close account (requires ₹0.00 balance)"
                          >
                            <Archive className="w-3 h-3" />
                            <span>Close</span>
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Provision Account Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full overflow-hidden">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <PlusCircle className="w-4 h-4 text-emerald-600" />
                <h3 className="font-bold text-slate-900 text-sm">Open Customer Account</h3>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateAccount} className="p-5 space-y-4">
              {createError && (
                <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{createError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Account Name
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Primary Savings, Operations Checking"
                  value={createData.name}
                  onChange={(e) => setCreateData({ ...createData, name: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Account Type
                </label>
                <select
                  value={createData.account_type}
                  onChange={(e) =>
                    setCreateData({ ...createData, account_type: e.target.value as AccountType })
                  }
                  className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900 focus:bg-white"
                >
                  <option value="customer_checking">Customer Checking</option>
                  <option value="customer_savings">Customer Savings</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Currency
                </label>
                <input
                  type="text"
                  disabled
                  value="INR (Indian Rupee)"
                  className="w-full px-3 py-2 text-xs bg-slate-100 text-slate-500 border border-slate-200 rounded-lg cursor-not-allowed"
                />
                <p className="text-[10px] text-slate-400 mt-0.5">
                  Single-currency core model strictly enforces INR.
                </p>
              </div>

              {user?.role === 'admin' && (
                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                    Owner User UUID (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="Leave empty to assign to current admin"
                    value={createData.owner_id}
                    onChange={(e) => setCreateData({ ...createData, owner_id: e.target.value })}
                    className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900 focus:bg-white font-mono text-[11px]"
                  />
                </div>
              )}

              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-[11px] text-slate-600">
                <strong>Initial Balance:</strong> ₹0.00 INR. Newly created accounts start with zero balance by database design.
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-50 rounded-lg shadow-xs"
                >
                  {isSubmitting ? 'Provisioning...' : 'Provision Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Status Lifecycle Confirmation Modal (Admin only) */}
      {selectedAccount && statusAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-sm w-full p-5 space-y-4">
            <div className="flex items-center gap-2">
              <Archive className="w-5 h-5 text-slate-800" />
              <h3 className="font-bold text-slate-900 text-sm">
                Confirm Status Change
              </h3>
            </div>

            {statusError && (
              <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{statusError}</span>
              </div>
            )}

            <p className="text-xs text-slate-600">
              Are you sure you want to transition account{' '}
              <strong className="text-slate-900 font-mono">{selectedAccount.account_number}</strong> from{' '}
              <span className="font-semibold uppercase">{selectedAccount.status}</span> to{' '}
              <span className="font-semibold uppercase text-indigo-600">{statusAction}</span>?
            </p>

            {statusAction === 'closed' && (
              <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-lg text-[11px] text-amber-800">
                <strong>Terminal Lifecycle:</strong> Closed accounts cannot be reopened. The account balance must be exactly ₹0.00.
              </div>
            )}

            <div className="pt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setSelectedAccount(null);
                  setStatusAction(null);
                  setStatusError(null);
                }}
                className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isUpdatingStatus}
                onClick={() => handleStatusChange(selectedAccount, statusAction)}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-50 rounded-lg shadow-xs"
              >
                {isUpdatingStatus ? 'Updating...' : 'Confirm Transition'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Ledger Entries Modal */}
      {ledgerAccount && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-2xl w-full overflow-hidden">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3 className="font-bold text-slate-900 text-sm flex items-center gap-2">
                  <ListOrdered className="w-4 h-4 text-emerald-600" />
                  <span>Ledger Entries: {ledgerAccount.account_number}</span>
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Double-entry posting history ({ledgerAccount.name})
                </p>
              </div>
              <button
                onClick={() => setLedgerAccount(null)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5">
              {ledgerError ? (
                <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-lg text-xs">
                  {ledgerError}
                </div>
              ) : loadingLedger ? (
                <div className="py-8 text-center text-xs text-slate-400">
                  Retrieving ledger records...
                </div>
              ) : ledgerEntries.length === 0 ? (
                <div className="py-8 text-center space-y-2">
                  <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400">
                    <BookOpen className="w-5 h-5" />
                  </div>
                  <div className="text-xs font-semibold text-slate-700">Zero Financial Postings</div>
                  <p className="text-[11px] text-slate-500 max-w-sm mx-auto">
                    Task 03 Financial Foundation enforces zero-balance accounts with no opening balance or financial movements.
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
                    <thead className="bg-slate-50 text-slate-600 font-semibold uppercase tracking-wider">
                      <tr>
                        <th className="px-3 py-2">Seq</th>
                        <th className="px-3 py-2">Entry Type</th>
                        <th className="px-3 py-2">Amount (INR)</th>
                        <th className="px-3 py-2">Timestamp</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {ledgerEntries.map((e) => (
                        <tr key={e.id}>
                          <td className="px-3 py-2 font-mono">{e.sequence}</td>
                          <td className="px-3 py-2 font-semibold uppercase">{e.entry_type}</td>
                          <td className="px-3 py-2 font-mono">₹{e.amount}</td>
                          <td className="px-3 py-2 font-mono text-[11px]">{new Date(e.created_at).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="p-3 bg-slate-50 border-t border-slate-100 flex justify-end">
              <button
                onClick={() => setLedgerAccount(null)}
                className="px-4 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-200 rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
