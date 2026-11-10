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

  const isSystemAccount = (acc: Account) => {
    return (
      acc.account_type === 'system_reserve' ||
      acc.account_type === 'internal_clearing' ||
      acc.account_number === 'ACC-SYSTEM01' ||
      acc.account_number === 'ACC-SYSTEM02' ||
      acc.account_number.startsWith('ACC-SYSTEM')
    );
  };

  const statusBadge = (status: AccountStatus) => {
    switch (status) {
      case 'active':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[#DCE9DF] text-[#245344] border border-[#C5D9C9]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#245344]"></span>
            Active
          </span>
        );
      case 'frozen':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[#F5E9DF] text-[#9B5540] border border-[#E8D5C4]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#9B5540]"></span>
            Frozen
          </span>
        );
      case 'closed':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
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
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-[#E9E2EF] text-[#553C7B] border border-[#D5C7DE]">
            <Building className="w-3 h-3 text-[#553C7B]" />
            System Reserve
          </span>
        );
      case 'internal_clearing':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-[#E9E2EF] text-[#553C7B] border border-[#D5C7DE]">
            <Building className="w-3 h-3 text-[#553C7B]" />
            Internal Clearing
          </span>
        );
      case 'customer_savings':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-[#DCE9DF] text-[#245344] border border-[#C5D9C9]">
            Savings
          </span>
        );
      case 'customer_checking':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-[#F1F4EF] text-[#1D2B27] border border-[#E3E9E2]">
            Checking
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 font-sans">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-6 rounded-2xl border border-[#E3E9E2] shadow-xs">
        <div className="flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-[#245344] flex items-center justify-center text-white shadow-xs">
            <BookOpen className="w-5 h-5 text-[#DCE9DF]" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-serif font-bold text-[#1D2B27]">Your Accounts</h1>
            </div>
            <p className="text-xs text-[#6D7C73] mt-0.5">
              {user?.role === 'account_holder'
                ? 'Manage your personal accounts and view running balances'
                : `System-wide accounts directory (${total} registered)`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchAccounts}
            disabled={loading}
            className="p-2.5 rounded-xl border border-[#E3E9E2] hover:bg-[#F1F4EF] text-[#6D7C73] transition cursor-pointer"
            title="Refresh accounts directory"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-[#245344]' : ''}`} />
          </button>

          {user?.role !== 'auditor' ? (
            <button
              onClick={() => {
                setCreateError(null);
                setShowCreateModal(true);
              }}
              className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-[#245344] hover:bg-[#1B3F34] text-white text-xs font-semibold shadow-xs transition cursor-pointer"
            >
              <PlusCircle className="w-3.5 h-3.5 text-[#DCE9DF]" />
              <span>Open New Account</span>
            </button>
          ) : (
            <div className="text-[11px] font-medium text-[#6D7C73] bg-[#F1F4EF] px-3 py-1.5 rounded-xl border border-[#E3E9E2] flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-[#245344]" />
              <span>Auditor Mode (Read-Only)</span>
            </div>
          )}
        </div>
      </div>

      {/* Account Integrity & Balance Protection */}
      <div className="p-4 bg-[#DCE9DF]/40 border border-[#C5D9C9] rounded-2xl text-[#1D2B27] text-xs flex items-start gap-3">
        <Building className="w-4 h-4 text-[#245344] shrink-0 mt-0.5" />
        <div className="space-y-0.5">
          <span className="font-semibold text-[#1D2B27]">Your Accounts</span>
          <p className="text-[#6D7C73] text-[11px]">
            All account balances are updated securely through verified transactions with guaranteed balance accuracy.
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
      <div className="bg-white rounded-2xl border border-[#E3E9E2] shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-[#E3E9E2] text-left text-xs">
            <thead className="bg-[#F1F4EF] text-[#6D7C73] font-semibold uppercase tracking-wider">
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
            <tbody className="divide-y divide-[#E3E9E2] bg-white">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-[#6D7C73]">
                    Loading accounts...
                  </td>
                </tr>
              ) : accounts.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-[#6D7C73]">
                    No accounts found. Use 'Open Customer Account' to provision a new account.
                  </td>
                </tr>
              ) : (
                accounts.map((acc) => (
                  <tr key={acc.id} className="hover:bg-[#F1F4EF]/50 transition">
                    <td className="px-4 py-3 font-mono text-xs font-semibold text-[#1D2B27]">
                      {acc.account_number}
                    </td>
                    <td className="px-4 py-3 font-medium text-[#1D2B27]">
                      {acc.name}
                    </td>
                    <td className="px-4 py-3">
                      {typeBadge(acc.account_type)}
                    </td>
                    <td className="px-4 py-3 font-mono">
                      <span className="font-semibold text-[#1D2B27]">
                        ₹{Number(acc.balance).toFixed(2)}
                      </span>
                      <span className="text-[10px] text-[#6D7C73] ml-1 font-sans uppercase">
                        {acc.currency}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {statusBadge(acc.status)}
                    </td>
                    {user?.role !== 'account_holder' && (
                      <td className="px-4 py-3 text-[#6D7C73] font-mono text-[11px]">
                        {acc.owner_id ? (
                          <span className="inline-flex items-center gap-1">
                            <UserIcon className="w-3 h-3 text-[#6D7C73]" />
                            {acc.owner_id.substring(0, 8)}...
                          </span>
                        ) : (
                          <span className="text-[10px] font-semibold text-[#553C7B] bg-[#E9E2EF] px-2 py-0.5 rounded border border-[#D5C7DE]">
                            System Root
                          </span>
                        )}
                      </td>
                    )}
                    <td className="px-4 py-3 text-right space-x-1.5 whitespace-nowrap">
                      {/* View Ledger Button */}
                      <button
                        onClick={() => handleViewLedger(acc)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-[#1D2B27] bg-[#F1F4EF] hover:bg-[#E3E9E2] border border-[#E3E9E2] rounded-lg transition cursor-pointer"
                        title="View ledger entries"
                      >
                        <ListOrdered className="w-3 h-3 text-[#6D7C73]" />
                        <span>Ledger</span>
                      </button>

                      {/* Admin Lifecycle Controls */}
                      {user?.role === 'admin' && (
                        isSystemAccount(acc) ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-[#553C7B] bg-[#E9E2EF] border border-[#D5C7DE] rounded-lg">
                            <Shield className="w-3 h-3" />
                            <span>Protected</span>
                          </span>
                        ) : acc.status !== 'closed' ? (
                          <>
                            {acc.status === 'active' && (
                              <button
                                onClick={() => {
                                  setSelectedAccount(acc);
                                  setStatusAction('frozen');
                                }}
                                className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-[#9B5540] bg-[#F5E9DF] hover:bg-[#ebd5c5] border border-[#E8D5C4] rounded-lg transition cursor-pointer"
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
                                className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-[#245344] bg-[#DCE9DF] hover:bg-[#cbe0cf] border border-[#C5D9C9] rounded-lg transition cursor-pointer"
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
                              className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded-lg transition cursor-pointer"
                              title="Close account (requires ₹0.00 balance)"
                            >
                              <Archive className="w-3 h-3" />
                              <span>Close</span>
                            </button>
                          </>
                        ) : null
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {total > 0 && (
          <div className="px-4 py-2.5 bg-[#F1F4EF]/70 border-t border-[#E3E9E2] flex items-center justify-between text-xs text-[#6D7C73]">
            <span>
              Showing {accounts.length} of {total} registered accounts
            </span>
          </div>
        )}
      </div>

      {/* Provision Account Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 font-sans">
          <div className="bg-white rounded-2xl shadow-xl border border-[#E3E9E2] max-w-md w-full overflow-hidden">
            <div className="p-5 border-b border-[#E3E9E2] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <PlusCircle className="w-4 h-4 text-[#245344]" />
                <h3 className="font-serif font-bold text-[#1D2B27] text-base">Open New Account</h3>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-[#6D7C73] hover:text-[#1D2B27] p-1 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateAccount} className="p-5 space-y-4">
              {createError && (
                <div className="p-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-600" />
                  <span>{createError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1">
                  Account Name
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Primary Savings, Daily Checking"
                  value={createData.name}
                  onChange={(e) => setCreateData({ ...createData, name: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-[#F1F4EF] border border-[#E3E9E2] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#245344] focus:bg-white text-[#1D2B27]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1">
                  Account Type
                </label>
                <select
                  value={createData.account_type}
                  onChange={(e) =>
                    setCreateData({ ...createData, account_type: e.target.value as AccountType })
                  }
                  className="w-full px-3 py-2 text-xs bg-[#F1F4EF] border border-[#E3E9E2] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#245344] focus:bg-white text-[#1D2B27]"
                >
                  <option value="customer_checking">Customer Checking</option>
                  <option value="customer_savings">Customer Savings</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1">
                  Currency
                </label>
                <input
                  type="text"
                  disabled
                  value="INR (Indian Rupee)"
                  className="w-full px-3 py-2 text-xs bg-[#F1F4EF] text-[#6D7C73] border border-[#E3E9E2] rounded-xl cursor-not-allowed"
                />
                <p className="text-[10px] text-[#6D7C73] mt-0.5">
                  Single-currency core model strictly enforces INR.
                </p>
              </div>

              {user?.role === 'admin' && (
                <div>
                  <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1">
                    Owner User UUID (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="Leave empty to assign to current admin"
                    value={createData.owner_id}
                    onChange={(e) => setCreateData({ ...createData, owner_id: e.target.value })}
                    className="w-full px-3 py-2 text-xs bg-[#F1F4EF] border border-[#E3E9E2] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#245344] focus:bg-white font-mono text-[11px] text-[#1D2B27]"
                  />
                </div>
              )}

              <div className="p-3 bg-[#F1F4EF] border border-[#E3E9E2] rounded-xl text-[11px] text-[#6D7C73]">
                <strong className="text-[#1D2B27]">Initial Balance:</strong> ₹0.00 INR. Newly created accounts start with zero balance by database design.
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-3.5 py-2 text-xs font-semibold text-[#6D7C73] hover:bg-[#F1F4EF] rounded-xl transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 text-xs font-semibold text-white bg-[#245344] hover:bg-[#1B3F34] disabled:opacity-50 rounded-xl shadow-xs transition cursor-pointer"
                >
                  {isSubmitting ? 'Opening Account...' : 'Open Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Status Lifecycle Confirmation Modal (Admin only) */}
      {selectedAccount && statusAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 font-sans">
          <div className="bg-white rounded-2xl shadow-xl border border-[#E3E9E2] max-w-sm w-full p-6 space-y-4">
            <div className="flex items-center gap-2">
              <Archive className="w-5 h-5 text-[#245344]" />
              <h3 className="font-serif font-bold text-[#1D2B27] text-base">
                Confirm Status Change
              </h3>
            </div>

            {statusError && (
              <div className="p-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{statusError}</span>
              </div>
            )}

            <p className="text-xs text-[#6D7C73]">
              Are you sure you want to transition account{' '}
              <strong className="text-[#1D2B27] font-mono">{selectedAccount.account_number}</strong> from{' '}
              <span className="font-semibold uppercase text-[#1D2B27]">{selectedAccount.status}</span> to{' '}
              <span className="font-semibold uppercase text-[#245344]">{statusAction}</span>?
            </p>

            {statusAction === 'closed' && (
              <div className="p-2.5 bg-[#F5E9DF] border border-[#E8D5C4] rounded-xl text-[11px] text-[#9B5540]">
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
                className="px-3.5 py-2 text-xs font-semibold text-[#6D7C73] hover:bg-[#F1F4EF] rounded-xl transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isUpdatingStatus}
                onClick={() => handleStatusChange(selectedAccount, statusAction)}
                className="px-4 py-2 text-xs font-semibold text-white bg-[#245344] hover:bg-[#1B3F34] disabled:opacity-50 rounded-xl shadow-xs transition cursor-pointer"
              >
                {isUpdatingStatus ? 'Updating...' : 'Confirm Transition'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Ledger Entries Modal */}
      {ledgerAccount && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 font-sans">
          <div className="bg-white rounded-2xl shadow-xl border border-[#E3E9E2] max-w-2xl w-full overflow-hidden">
            <div className="p-5 border-b border-[#E3E9E2] bg-[#F1F4EF]/40 flex items-center justify-between">
              <div>
                <h3 className="font-serif font-bold text-[#1D2B27] text-base flex items-center gap-2">
                  <ListOrdered className="w-4 h-4 text-[#245344]" />
                  <span>Ledger Entries: {ledgerAccount.account_number}</span>
                </h3>
                <p className="text-xs text-[#6D7C73] mt-0.5">
                  Double-entry posting history ({ledgerAccount.name})
                </p>
              </div>
              <button
                onClick={() => setLedgerAccount(null)}
                className="text-[#6D7C73] hover:text-[#1D2B27] p-1 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5">
              {ledgerError ? (
                <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs">
                  {ledgerError}
                </div>
              ) : loadingLedger ? (
                <div className="py-8 text-center text-xs text-[#6D7C73]">
                  Retrieving ledger records...
                </div>
              ) : ledgerEntries.length === 0 ? (
                <div className="py-8 text-center space-y-2">
                  <div className="w-10 h-10 rounded-full bg-[#F1F4EF] flex items-center justify-center mx-auto text-[#6D7C73]">
                    <BookOpen className="w-5 h-5 text-[#245344]" />
                  </div>
                  <div className="text-xs font-semibold text-[#1D2B27]">No Posted Transactions Yet</div>
                  <p className="text-[11px] text-[#6D7C73] max-w-sm mx-auto">
                    Accounts are initialized with zero balances. Financial movements will appear here once authorized ledger transactions are posted.
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-[#E3E9E2] text-left text-xs">
                    <thead className="bg-[#F1F4EF] text-[#6D7C73] font-semibold uppercase tracking-wider">
                      <tr>
                        <th className="px-3 py-2">Seq</th>
                        <th className="px-3 py-2">Entry Type</th>
                        <th className="px-3 py-2">Amount (INR)</th>
                        <th className="px-3 py-2">Timestamp</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E3E9E2]">
                      {ledgerEntries.map((e) => (
                        <tr key={e.id}>
                          <td className="px-3 py-2 font-mono text-[#1D2B27]">{e.sequence}</td>
                          <td className="px-3 py-2 font-semibold uppercase text-[#1D2B27]">{e.entry_type}</td>
                          <td className="px-3 py-2 font-mono font-semibold text-[#1D2B27]">₹{e.amount}</td>
                          <td className="px-3 py-2 font-mono text-[11px] text-[#6D7C73]">{new Date(e.created_at).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="p-3 bg-[#F1F4EF]/70 border-t border-[#E3E9E2] flex justify-end">
              <button
                onClick={() => setLedgerAccount(null)}
                className="px-4 py-2 text-xs font-semibold text-[#1D2B27] bg-white border border-[#E3E9E2] hover:bg-[#F1F4EF] rounded-xl transition cursor-pointer"
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
