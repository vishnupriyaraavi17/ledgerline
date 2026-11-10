import React, { useState, useEffect } from 'react';
import {
  ArrowLeftRight,
  ArrowDownLeft,
  ArrowUpRight,
  BookOpen,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Shield,
  ShieldAlert,
  Wallet,
  Clock,
  Info,
} from 'lucide-react';

import { useAuth } from '../context/AuthContext';
import { apiService } from '../services/api';
import type { Account } from '../types/account';
import type {
  TransactionResponse,
  DepositRequest,
  WithdrawRequest,
  TransferRequest,
} from '../types/transfer';

type TabType = 'transfer' | 'deposit' | 'withdraw' | 'journal';

export const TransfersPage: React.FC = () => {
  const { user, isAuthenticated } = useAuth();

  // Active navigation tab - Account holders default to transfer, Admin and Auditor default to journal
  const [activeTab, setActiveTab] = useState<TabType>(
    user?.role === 'account_holder' ? 'transfer' : 'journal'
  );

  // Loaded data
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [transactions, setTransactions] = useState<TransactionResponse[]>([]);
  const [totalTransactions, setTotalTransactions] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [globalError, setGlobalError] = useState<string | null>(null);

  // Form states
  const [transferForm, setTransferForm] = useState<{
    source_id: string;
    destination_id: string;
    amount: string;
    description: string;
  }>({
    source_id: '',
    destination_id: '',
    amount: '',
    description: '',
  });

  const [depositForm, setDepositForm] = useState<{
    account_id: string;
    amount: string;
    description: string;
  }>({
    account_id: '',
    amount: '',
    description: '',
  });

  const [withdrawForm, setWithdrawForm] = useState<{
    account_id: string;
    amount: string;
    description: string;
  }>({
    account_id: '',
    amount: '',
    description: '',
  });

  const [formSubmitting, setFormSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Idempotency state management
  const [transferKey, setTransferKey] = useState<string>(() => crypto.randomUUID());
  const [depositKey, setDepositKey] = useState<string>(() => crypto.randomUUID());
  const [withdrawKey, setWithdrawKey] = useState<string>(() => crypto.randomUUID());
  const [replayMessage, setReplayMessage] = useState<string | null>(null);
  const [conflictError, setConflictError] = useState<string | null>(null);
  const [canRetry, setCanRetry] = useState<boolean>(false);
  const [lastFailedAction, setLastFailedAction] = useState<(() => Promise<void>) | null>(null);

  const generateNewKeyForActiveTab = () => {
    const fresh = crypto.randomUUID();
    if (activeTab === 'transfer') setTransferKey(fresh);
    else if (activeTab === 'deposit') setDepositKey(fresh);
    else if (activeTab === 'withdraw') setWithdrawKey(fresh);
    setConflictError(null);
    setCanRetry(false);
    setLastFailedAction(null);
  };

  const updateTransferField = (field: string, value: string) => {
    setTransferForm((prev) => ({ ...prev, [field]: value }));
    setTransferKey(crypto.randomUUID());
    setFormError(null);
    setConflictError(null);
    setReplayMessage(null);
    setCanRetry(false);
    setLastFailedAction(null);
  };

  const updateDepositField = (field: string, value: string) => {
    setDepositForm((prev) => ({ ...prev, [field]: value }));
    setDepositKey(crypto.randomUUID());
    setFormError(null);
    setConflictError(null);
    setReplayMessage(null);
    setCanRetry(false);
    setLastFailedAction(null);
  };

  const updateWithdrawField = (field: string, value: string) => {
    setWithdrawForm((prev) => ({ ...prev, [field]: value }));
    setWithdrawKey(crypto.randomUUID());
    setFormError(null);
    setConflictError(null);
    setReplayMessage(null);
    setCanRetry(false);
    setLastFailedAction(null);
  };

  // Initial data loader
  const loadData = async (silent: boolean = false) => {
    if (!silent) setLoading(true);
    setGlobalError(null);
    try {
      const [accRes, txnRes] = await Promise.all([
        apiService.getAccounts(0, 100),
        apiService.listTransactions(0, 50),
      ]);
      setAccounts(accRes.items);
      setTransactions(txnRes.items);
      setTotalTransactions(txnRes.total);

      // Pre-select first eligible customer account for forms if not set
      const customerAccs = accRes.items.filter(
        (a) =>
          (a.account_type === 'customer_checking' || a.account_type === 'customer_savings') &&
          a.status === 'active'
      );

      if (customerAccs.length > 0) {
        setTransferForm((prev) => ({
          ...prev,
          source_id: prev.source_id || customerAccs[0].id,
          destination_id: prev.destination_id || (customerAccs[1]?.id || ''),
        }));
        setDepositForm((prev) => ({
          ...prev,
          account_id: prev.account_id || customerAccs[0].id,
        }));
        setWithdrawForm((prev) => ({
          ...prev,
          account_id: prev.account_id || customerAccs[0].id,
        }));
      }
    } catch (err: any) {
      if (err.response?.status === 401) {
        setGlobalError('401 Unauthorized: Please sign in to access financial operations.');
      } else {
        setGlobalError('Failed to load accounts and transaction journal.');
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      loadData();
    } else {
      setLoading(false);
    }
  }, [isAuthenticated, user?.role]);

  // Non-account-holders (Admin and Auditor) are restricted to transaction journal
  useEffect(() => {
    if (user?.role && user.role !== 'account_holder') {
      setActiveTab('journal');
    }
  }, [user?.role]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadData(true);
  };

  // Helper to find selected account
  const findAccount = (id: string) => accounts.find((a) => a.id === id);

  // Format currency
  const formatCurrency = (val: string | number) => {
    const num = typeof val === 'string' ? parseFloat(val) : val;
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 2,
    }).format(isNaN(num) ? 0 : num);
  };

  // 1. Submit Transfer
  const handleTransfer = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setFormError(null);
    setConflictError(null);
    setReplayMessage(null);
    setSuccessMessage(null);

    if (transferForm.source_id === transferForm.destination_id) {
      setFormError('Source and destination accounts must be distinct. Self-transfers are prohibited.');
      return;
    }

    const amt = parseFloat(transferForm.amount);
    if (isNaN(amt) || amt <= 0) {
      setFormError('Amount must be strictly greater than ₹0.00.');
      return;
    }

    const src = findAccount(transferForm.source_id);
    if (src && parseFloat(src.balance) < amt) {
      setFormError(`Insufficient funds: Available balance is ₹${src.balance}, requested ₹${amt.toFixed(2)}.`);
      return;
    }

    setFormSubmitting(true);
    try {
      const payload: TransferRequest = {
        source_account_id: transferForm.source_id,
        destination_account_id: transferForm.destination_id,
        amount: amt.toFixed(2),
        description: transferForm.description.trim() || undefined,
      };

      const res = await apiService.transfer(payload, transferKey);
      if (res.isReplay) {
        setReplayMessage('Replayed Transaction: Idempotency safety verified (No duplicate funds moved).');
        setSuccessMessage(
          `Transfer already processed (Replayed). Reference: ${res.transaction.reference} (Amount: ₹${payload.amount})`
        );
      } else {
        setReplayMessage(null);
        setSuccessMessage(
          `Transfer completed successfully. Reference: ${res.transaction.reference} (Amount: ₹${payload.amount})`
        );
      }

      // Fresh key for subsequent transaction
      setTransferKey(crypto.randomUUID());
      setTransferForm((prev) => ({ ...prev, amount: '', description: '' }));
      setCanRetry(false);
      setLastFailedAction(null);
      await loadData(true);
    } catch (err: any) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;
      if (status === 409) {
        setConflictError(typeof detail === 'string' ? detail : 'Idempotency conflict: Key was previously used with a different request payload.');
        setCanRetry(false);
        setLastFailedAction(null);
      } else if (!err.response || err.code === 'ECONNABORTED' || err.message?.includes('Network Error') || err.message?.includes('timeout')) {
        // Network timeout / connection drop: RETAIN identical key for safe retry
        setFormError('Network timeout or connection error. Your transaction token has been safely retained. You can safely retry without duplicate posting.');
        setCanRetry(true);
        setLastFailedAction(() => () => handleTransfer());
      } else {
        setFormError(typeof detail === 'string' ? detail : 'Transfer request failed.');
        setCanRetry(false);
        setLastFailedAction(null);
      }
    } finally {
      setFormSubmitting(false);
    }
  };

  // 2. Submit Deposit
  const handleDeposit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setFormError(null);
    setConflictError(null);
    setReplayMessage(null);
    setSuccessMessage(null);

    const amt = parseFloat(depositForm.amount);
    if (isNaN(amt) || amt <= 0) {
      setFormError('Amount must be strictly greater than ₹0.00.');
      return;
    }

    setFormSubmitting(true);
    try {
      const payload: DepositRequest = {
        account_id: depositForm.account_id,
        amount: amt.toFixed(2),
        description: depositForm.description.trim() || undefined,
      };

      const res = await apiService.deposit(payload, depositKey);
      if (res.isReplay) {
        setReplayMessage('Replayed Transaction: Idempotency safety verified (No duplicate funds moved).');
        setSuccessMessage(
          `Deposit already processed (Replayed). Reference: ${res.transaction.reference} (Amount: ₹${payload.amount})`
        );
      } else {
        setReplayMessage(null);
        setSuccessMessage(
          `Simulated deposit posted successfully. Reference: ${res.transaction.reference} (Amount: ₹${payload.amount})`
        );
      }

      // Fresh key for subsequent transaction
      setDepositKey(crypto.randomUUID());
      setDepositForm((prev) => ({ ...prev, amount: '', description: '' }));
      setCanRetry(false);
      setLastFailedAction(null);
      await loadData(true);
    } catch (err: any) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;
      if (status === 409) {
        setConflictError(typeof detail === 'string' ? detail : 'Idempotency conflict: Key was previously used with a different request payload.');
        setCanRetry(false);
        setLastFailedAction(null);
      } else if (!err.response || err.code === 'ECONNABORTED' || err.message?.includes('Network Error') || err.message?.includes('timeout')) {
        // Network timeout / connection drop: RETAIN identical key for safe retry
        setFormError('Network timeout or connection error. Your transaction token has been safely retained. You can safely retry without duplicate posting.');
        setCanRetry(true);
        setLastFailedAction(() => () => handleDeposit());
      } else {
        setFormError(typeof detail === 'string' ? detail : 'Deposit request failed.');
        setCanRetry(false);
        setLastFailedAction(null);
      }
    } finally {
      setFormSubmitting(false);
    }
  };

  // 3. Submit Withdrawal
  const handleWithdrawal = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setFormError(null);
    setConflictError(null);
    setReplayMessage(null);
    setSuccessMessage(null);

    const amt = parseFloat(withdrawForm.amount);
    if (isNaN(amt) || amt <= 0) {
      setFormError('Amount must be strictly greater than ₹0.00.');
      return;
    }

    const src = findAccount(withdrawForm.account_id);
    if (src && parseFloat(src.balance) < amt) {
      setFormError(`Insufficient funds: Available balance is ₹${src.balance}, requested ₹${amt.toFixed(2)}.`);
      return;
    }

    setFormSubmitting(true);
    try {
      const payload: WithdrawRequest = {
        account_id: withdrawForm.account_id,
        amount: amt.toFixed(2),
        description: withdrawForm.description.trim() || undefined,
      };

      const res = await apiService.withdraw(payload, withdrawKey);
      if (res.isReplay) {
        setReplayMessage('Replayed Transaction: Idempotency safety verified (No duplicate funds moved).');
        setSuccessMessage(
          `Withdrawal already processed (Replayed). Reference: ${res.transaction.reference} (Amount: ₹${payload.amount})`
        );
      } else {
        setReplayMessage(null);
        setSuccessMessage(
          `Simulated withdrawal disbursed successfully. Reference: ${res.transaction.reference} (Amount: ₹${payload.amount})`
        );
      }

      // Fresh key for subsequent transaction
      setWithdrawKey(crypto.randomUUID());
      setWithdrawForm((prev) => ({ ...prev, amount: '', description: '' }));
      setCanRetry(false);
      setLastFailedAction(null);
      await loadData(true);
    } catch (err: any) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;
      if (status === 409) {
        setConflictError(typeof detail === 'string' ? detail : 'Idempotency conflict: Key was previously used with a different request payload.');
        setCanRetry(false);
        setLastFailedAction(null);
      } else if (!err.response || err.code === 'ECONNABORTED' || err.message?.includes('Network Error') || err.message?.includes('timeout')) {
        // Network timeout / connection drop: RETAIN identical key for safe retry
        setFormError('Network timeout or connection error. Your transaction token has been safely retained. You can safely retry without duplicate posting.');
        setCanRetry(true);
        setLastFailedAction(() => () => handleWithdrawal());
      } else {
        setFormError(typeof detail === 'string' ? detail : 'Withdrawal request failed.');
        setCanRetry(false);
        setLastFailedAction(null);
      }
    } finally {
      setFormSubmitting(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 text-center">
        <ShieldAlert className="w-8 h-8 text-amber-600 mx-auto mb-2" />
        <h2 className="text-lg font-bold text-amber-900 mb-1">Authentication Required</h2>
        <p className="text-sm text-amber-700">Please sign in to access financial operations and ledger records.</p>
      </div>
    );
  }

  // Active customer accounts eligible for selection
  const customerAccounts = accounts.filter(
    (a) =>
      (a.account_type === 'customer_checking' || a.account_type === 'customer_savings') &&
      a.status === 'active'
  );

  return (
    <div className="space-y-6 font-sans">
      {/* Top Banner */}
      <div className="bg-white border border-[#E3E9E2] rounded-2xl p-6 shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3.5">
              <div className="w-11 h-11 rounded-xl bg-[#245344] flex items-center justify-center text-white shadow-xs">
                <ArrowLeftRight className="w-5 h-5 text-[#DCE9DF]" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-xl font-serif font-bold tracking-tight text-[#1D2B27]">
                    {user?.role === 'account_holder'
                      ? 'Transfers'
                      : user?.role === 'admin'
                      ? 'Financial Operations Oversight'
                      : 'Transaction History'}
                  </h1>
                </div>
                <p className="text-xs text-[#6D7C73] mt-0.5">
                  {user?.role === 'account_holder'
                    ? 'Transfer money securely between your accounts.'
                    : user?.role === 'admin'
                    ? 'Administrative supervision and double-entry transaction journal.'
                    : 'Auditor read-only inspection of the double-entry transaction journal.'}
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={refreshing || loading}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-[#1D2B27] bg-[#F1F4EF] hover:bg-[#E3E9E2] border border-[#E3E9E2] rounded-xl transition disabled:opacity-50 cursor-pointer shadow-2xs"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-[#245344]' : ''}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Global Error Banner */}
        {globalError && (
          <div className="mt-4 p-3.5 bg-rose-50 border border-rose-200 rounded-xl flex items-center gap-2 text-rose-800 text-xs">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
            <span>{globalError}</span>
          </div>
        )}

        {/* Admin Role Alert */}
        {user?.role === 'admin' && (
          <div className="mt-4 p-3.5 bg-[#E9E2EF]/70 border border-[#D5C7DE] rounded-xl flex items-center gap-2.5 text-[#553C7B] text-xs">
            <Shield className="w-4 h-4 text-[#553C7B] shrink-0" />
            <span>
              <strong>Administrative Financial Oversight:</strong> Customer transfers can only be initiated by Account Holders. You have supervisory access to inspect all transaction records across the system.
            </span>
          </div>
        )}

        {/* Auditor Role Alert */}
        {user?.role === 'auditor' && (
          <div className="mt-4 p-3.5 bg-[#DCE9DF]/50 border border-[#C5D9C9] rounded-xl flex items-center gap-2.5 text-[#245344] text-xs">
            <Shield className="w-4 h-4 text-[#245344] shrink-0" />
            <span>
              <strong>Auditor Read-Only Mode:</strong> Postings are restricted by RBAC. You have full read-only access to inspect the double-entry transaction journal.
            </span>
          </div>
        )}
      </div>

      {/* Tabs Navigation */}
      <div className="flex border-b border-[#E3E9E2] bg-white rounded-t-2xl px-6 pt-3 gap-3 shadow-xs">
        {user?.role === 'account_holder' && (
          <>
            <button
              onClick={() => {
                setActiveTab('transfer');
                setFormError(null);
                setSuccessMessage(null);
              }}
              className={`pb-3 px-3 text-xs sm:text-sm font-semibold border-b-2 flex items-center gap-2 transition cursor-pointer ${
                activeTab === 'transfer'
                  ? 'border-[#245344] text-[#245344]'
                  : 'border-transparent text-[#6D7C73] hover:text-[#1D2B27]'
              }`}
            >
              <ArrowLeftRight className="w-4 h-4" />
              <span>Transfer Funds</span>
            </button>

            <button
              onClick={() => {
                setActiveTab('deposit');
                setFormError(null);
                setSuccessMessage(null);
              }}
              className={`pb-3 px-3 text-xs sm:text-sm font-semibold border-b-2 flex items-center gap-2 transition cursor-pointer ${
                activeTab === 'deposit'
                  ? 'border-[#245344] text-[#245344]'
                  : 'border-transparent text-[#6D7C73] hover:text-[#1D2B27]'
              }`}
            >
              <ArrowDownLeft className="w-4 h-4" />
              <span>Add Money (Demo)</span>
            </button>

            <button
              onClick={() => {
                setActiveTab('withdraw');
                setFormError(null);
                setSuccessMessage(null);
              }}
              className={`pb-3 px-3 text-xs sm:text-sm font-semibold border-b-2 flex items-center gap-2 transition cursor-pointer ${
                activeTab === 'withdraw'
                  ? 'border-[#245344] text-[#245344]'
                  : 'border-transparent text-[#6D7C73] hover:text-[#1D2B27]'
              }`}
            >
              <ArrowUpRight className="w-4 h-4" />
              <span>Withdraw Money (Demo)</span>
            </button>
          </>
        )}

        <button
          onClick={() => {
            setActiveTab('journal');
            setFormError(null);
            setSuccessMessage(null);
          }}
          className={`pb-3 px-3 text-xs sm:text-sm font-semibold border-b-2 flex items-center gap-2 transition cursor-pointer ${
            activeTab === 'journal'
              ? 'border-[#245344] text-[#245344]'
              : 'border-transparent text-[#6D7C73] hover:text-[#1D2B27]'
          }`}
        >
          <BookOpen className="w-4 h-4" />
          <span>Transaction History ({totalTransactions})</span>
        </button>
      </div>

      {/* Action Notifications */}
      {replayMessage && (
        <div className="p-4 bg-sky-50 border border-sky-200 rounded-xl flex items-center gap-3 text-sky-800 text-sm shadow-xs animate-in fade-in">
          <Shield className="w-5 h-5 text-sky-600 shrink-0" />
          <div>
            <div className="font-semibold flex items-center gap-2">
              <span>Replayed Transaction</span>
              <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 bg-sky-100 text-sky-700 rounded-full">
                Idempotent Replay
              </span>
            </div>
            <div className="text-xs text-sky-700">{replayMessage}</div>
          </div>
        </div>
      )}

      {successMessage && !replayMessage && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-3 text-emerald-800 text-sm shadow-xs animate-in fade-in">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
          <div>
            <div className="font-semibold">Transaction Executed</div>
            <div className="font-mono text-xs text-emerald-700">{successMessage}</div>
          </div>
        </div>
      )}

      {conflictError && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start justify-between gap-3 text-amber-800 text-sm shadow-xs animate-in fade-in">
          <div className="flex items-start gap-3">
            <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-amber-900">Idempotency Conflict (HTTP 409)</div>
              <div className="text-xs text-amber-700 mt-0.5">{conflictError}</div>
              <div className="text-xs text-amber-600 mt-1">
                This idempotency key was previously submitted with different transaction parameters. Click below to generate a fresh key for this payload.
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={generateNewKeyForActiveTab}
            className="px-3 py-1.5 text-xs font-semibold bg-amber-600 hover:bg-amber-700 text-white rounded-lg transition shrink-0"
          >
            Generate Fresh Key
          </button>
        </div>
      )}

      {formError && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl flex items-center justify-between gap-3 text-rose-800 text-sm shadow-xs">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-rose-600 shrink-0" />
            <div>
              <div className="font-semibold">Operation Rejected</div>
              <div className="text-xs text-rose-700">{formError}</div>
            </div>
          </div>
          {canRetry && lastFailedAction && (
            <button
              type="button"
              onClick={() => lastFailedAction()}
              disabled={formSubmitting}
              className="px-3 py-1.5 text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white rounded-lg transition shrink-0 flex items-center gap-1.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${formSubmitting ? 'animate-spin' : ''}`} />
              <span>Retry with Same Key</span>
            </button>
          )}
        </div>
      )}

      {/* Main Tab Panels */}
      <div className="bg-white border border-[#E3E9E2] rounded-2xl p-6 shadow-xs">
        {/* 1. Internal Transfer Form */}
        {activeTab === 'transfer' && (
          <form onSubmit={handleTransfer} className="max-w-2xl space-y-5">
            <div>
              <h2 className="text-base font-serif font-bold text-[#1D2B27]">Transfer Between Your Accounts</h2>
              <p className="text-xs text-[#6D7C73] mt-1">
                Move money between your eligible accounts. Your balances update after a successful transfer.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Sourcing Account */}
              <div>
                <label className="block text-xs font-semibold text-[#1D2B27] mb-1.5">
                  From Account *
                </label>
                <select
                  value={transferForm.source_id}
                  onChange={(e) => updateTransferField('source_id', e.target.value)}
                  className="w-full text-xs font-medium border border-[#E3E9E2] rounded-xl p-2.5 bg-white text-[#1D2B27] focus:ring-2 focus:ring-[#245344] focus:border-[#245344] outline-none"
                  required
                >
                  {customerAccounts.map((acc) => (
                    <option key={acc.id} value={acc.id}>
                      {acc.account_number} ({acc.name}) — {formatCurrency(acc.balance)}
                    </option>
                  ))}
                </select>
                {transferForm.source_id && (
                  <div className="mt-1 text-[11px] text-[#6D7C73]">
                    Available: <span className="font-semibold font-mono text-[#1D2B27]">
                      {formatCurrency(findAccount(transferForm.source_id)?.balance || 0)}
                    </span>
                  </div>
                )}
              </div>

              {/* Destination Account */}
              <div>
                <label className="block text-xs font-semibold text-[#1D2B27] mb-1.5">
                  To Account *
                </label>
                <select
                  value={transferForm.destination_id}
                  onChange={(e) => updateTransferField('destination_id', e.target.value)}
                  className="w-full text-xs font-medium border border-[#E3E9E2] rounded-xl p-2.5 bg-white text-[#1D2B27] focus:ring-2 focus:ring-[#245344] focus:border-[#245344] outline-none"
                  required
                >
                  <option value="">-- Select Destination --</option>
                  {accounts
                    .filter(
                      (a) =>
                        a.id !== transferForm.source_id &&
                        (a.account_type === 'customer_checking' || a.account_type === 'customer_savings') &&
                        a.status === 'active'
                    )
                    .map((acc) => (
                      <option key={acc.id} value={acc.id}>
                        {acc.account_number} ({acc.name})
                      </option>
                    ))}
                </select>
              </div>
            </div>

            {/* Transfer Amount */}
            <div>
              <label className="block text-xs font-semibold text-[#1D2B27] mb-1.5">
                Amount (₹) *
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center text-[#6D7C73] font-mono text-sm">₹</span>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="0.00"
                  value={transferForm.amount}
                  onChange={(e) => updateTransferField('amount', e.target.value)}
                  className="w-full pl-8 text-sm font-mono border border-[#E3E9E2] rounded-xl p-2.5 text-[#1D2B27] focus:ring-2 focus:ring-[#245344] focus:border-[#245344] outline-none"
                  required
                />
              </div>
            </div>

            {/* Description */}
            <div>
              <label className="block text-xs font-semibold text-[#1D2B27] mb-1.5">
                Description (Optional)
              </label>
              <input
                type="text"
                maxLength={255}
                placeholder="e.g. Invoice payment, savings transfer"
                value={transferForm.description}
                onChange={(e) => updateTransferField('description', e.target.value)}
                className="w-full text-xs border border-[#E3E9E2] rounded-xl p-2.5 text-[#1D2B27] focus:ring-2 focus:ring-[#245344] focus:border-[#245344] outline-none"
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={formSubmitting || !transferForm.source_id || !transferForm.destination_id}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#245344] text-white text-xs font-semibold hover:bg-[#1B3F34] transition disabled:opacity-50 shadow-xs cursor-pointer"
              >
                {formSubmitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Processing Transfer...</span>
                  </>
                ) : (
                  <>
                    <ArrowLeftRight className="w-3.5 h-3.5" />
                    <span>Send Money</span>
                  </>
                )}
              </button>
            </div>
          </form>
        )}

        {/* 2. Deposit Form */}
        {activeTab === 'deposit' && (
          <form onSubmit={handleDeposit} className="max-w-2xl space-y-5">
            <div>
              <h2 className="text-base font-serif font-bold text-[#1D2B27]">Add Money (Demo)</h2>
              <p className="text-xs text-[#6D7C73] mt-1">
                Deposit virtual demo funds into your account for testing purposes.
              </p>
            </div>

            <div className="p-3.5 bg-[#DCE9DF]/40 border border-[#C5D9C9] rounded-xl text-xs flex items-start gap-2.5">
              <Info className="w-4 h-4 text-[#245344] shrink-0 mt-0.5" />
              <span className="text-[#245344] font-medium leading-relaxed">
                This is a demonstration feature using virtual funds. No real monetary transactions take place.
              </span>
            </div>

            {/* Target Account */}
            <div>
              <label className="block text-xs font-semibold text-[#1D2B27] mb-1.5">
                Deposit To *
              </label>
              <select
                value={depositForm.account_id}
                onChange={(e) => updateDepositField('account_id', e.target.value)}
                className="w-full text-xs font-medium border border-[#E3E9E2] rounded-xl p-2.5 bg-white text-[#1D2B27] focus:ring-2 focus:ring-[#245344] focus:border-[#245344] outline-none"
                required
              >
                {customerAccounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>
                    {acc.account_number} ({acc.name}) — Current: {formatCurrency(acc.balance)}
                  </option>
                ))}
              </select>
            </div>

            {/* Deposit Amount */}
            <div>
              <label className="block text-xs font-semibold text-[#1D2B27] mb-1.5">
                Amount (₹) *
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center text-[#6D7C73] font-mono text-sm">₹</span>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="0.00"
                  value={depositForm.amount}
                  onChange={(e) => updateDepositField('amount', e.target.value)}
                  className="w-full pl-8 text-sm font-mono border border-[#E3E9E2] rounded-xl p-2.5 text-[#1D2B27] focus:ring-2 focus:ring-[#245344] focus:border-[#245344] outline-none"
                  required
                />
              </div>
            </div>

            {/* Description */}
            <div>
              <label className="block text-xs font-semibold text-[#1D2B27] mb-1.5">
                Description (Optional)
              </label>
              <input
                type="text"
                maxLength={255}
                placeholder="e.g. Initial demo funding, test deposit"
                value={depositForm.description}
                onChange={(e) => updateDepositField('description', e.target.value)}
                className="w-full text-xs border border-[#E3E9E2] rounded-xl p-2.5 text-[#1D2B27] focus:ring-2 focus:ring-[#245344] focus:border-[#245344] outline-none"
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={formSubmitting || !depositForm.account_id}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#245344] text-white text-xs font-semibold hover:bg-[#1B3F34] transition disabled:opacity-50 shadow-xs cursor-pointer"
              >
                {formSubmitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Adding Demo Funds...</span>
                  </>
                ) : (
                  <>
                    <ArrowDownLeft className="w-3.5 h-3.5" />
                    <span>Add Money (Demo)</span>
                  </>
                )}
              </button>
            </div>
          </form>
        )}

        {/* 3. Withdrawal Form */}
        {activeTab === 'withdraw' && (
          <form onSubmit={handleWithdrawal} className="max-w-2xl space-y-5">
            <div>
              <h2 className="text-base font-serif font-bold text-[#1D2B27]">Withdraw Money (Demo)</h2>
              <p className="text-xs text-[#6D7C73] mt-1">
                Withdraw virtual demo funds from your account. Overdrafts are not permitted.
              </p>
            </div>

            <div className="p-3.5 bg-[#F5E9DF]/50 border border-[#E8D5C4] rounded-xl text-xs flex items-start gap-2.5">
              <Info className="w-4 h-4 text-[#9B5540] shrink-0 mt-0.5" />
              <span className="text-[#9B5540] font-medium leading-relaxed">
                This is a demonstration feature using virtual funds. No real monetary transactions take place.
              </span>
            </div>

            {/* Source Account */}
            <div>
              <label className="block text-xs font-semibold text-[#1D2B27] mb-1.5">
                Withdraw From *
              </label>
              <select
                value={withdrawForm.account_id}
                onChange={(e) => updateWithdrawField('account_id', e.target.value)}
                className="w-full text-xs font-medium border border-[#E3E9E2] rounded-xl p-2.5 bg-white text-[#1D2B27] focus:ring-2 focus:ring-[#245344] focus:border-[#245344] outline-none"
                required
              >
                {customerAccounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>
                    {acc.account_number} ({acc.name}) — Available: {formatCurrency(acc.balance)}
                  </option>
                ))}
              </select>
            </div>

            {/* Withdrawal Amount */}
            <div>
              <label className="block text-xs font-semibold text-[#1D2B27] mb-1.5">
                Amount (₹) *
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center text-[#6D7C73] font-mono text-sm">₹</span>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="0.00"
                  value={withdrawForm.amount}
                  onChange={(e) => updateWithdrawField('amount', e.target.value)}
                  className="w-full pl-8 text-sm font-mono border border-[#E3E9E2] rounded-xl p-2.5 text-[#1D2B27] focus:ring-2 focus:ring-[#245344] focus:border-[#245344] outline-none"
                  required
                />
              </div>
            </div>

            {/* Description */}
            <div>
              <label className="block text-xs font-semibold text-[#1D2B27] mb-1.5">
                Description (Optional)
              </label>
              <input
                type="text"
                maxLength={255}
                placeholder="e.g. Test ATM payout, vendor demo withdrawal"
                value={withdrawForm.description}
                onChange={(e) => updateWithdrawField('description', e.target.value)}
                className="w-full text-xs border border-[#E3E9E2] rounded-xl p-2.5 text-[#1D2B27] focus:ring-2 focus:ring-[#245344] focus:border-[#245344] outline-none"
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={formSubmitting || !withdrawForm.account_id}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#245344] text-white text-xs font-semibold hover:bg-[#1B3F34] transition disabled:opacity-50 shadow-xs cursor-pointer"
              >
                {formSubmitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Processing Withdrawal...</span>
                  </>
                ) : (
                  <>
                    <ArrowUpRight className="w-3.5 h-3.5" />
                    <span>Withdraw Money (Demo)</span>
                  </>
                )}
              </button>
            </div>
          </form>
        )}

        {/* 4. Transaction History */}
        {activeTab === 'journal' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-serif font-bold text-[#1D2B27]">Transaction History</h2>
                <p className="text-xs text-[#6D7C73] mt-0.5">
                  A complete record of your completed transactions.
                </p>
              </div>
              <span className="text-xs text-[#6D7C73] font-mono">
                Showing {transactions.length} of {totalTransactions}
              </span>
            </div>

            {loading ? (
              <div className="py-12 text-center text-[#6D7C73] text-sm">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-[#245344]" />
                Loading transaction records...
              </div>
            ) : transactions.length === 0 ? (
              <div className="py-12 text-center text-[#6D7C73] text-sm border-2 border-dashed border-[#E3E9E2] rounded-2xl">
                <Wallet className="w-8 h-8 text-[#6D7C73] mx-auto mb-2" />
                <div className="font-semibold text-[#1D2B27]">No transactions recorded yet</div>
                <div className="text-xs text-[#6D7C73]">Perform a transfer or add money to see activity here.</div>
              </div>
            ) : (
              <div className="divide-y divide-[#E3E9E2] border border-[#E3E9E2] rounded-2xl overflow-hidden">
                {transactions.map((txn) => (
                  <div key={txn.id} className="p-4 hover:bg-[#F1F4EF]/50 transition">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-[#1D2B27] px-2 py-0.5 rounded-lg bg-[#F1F4EF] border border-[#E3E9E2]">
                          {txn.reference}
                        </span>
                        <span
                          className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full border ${
                            txn.transaction_type === 'transfer'
                              ? 'bg-[#DCE9DF] text-[#245344] border-[#C5D9C9]'
                              : 'bg-[#F5E9DF] text-[#9B5540] border-[#E8D5C4]'
                          }`}
                        >
                          {txn.transaction_type}
                        </span>
                        <span className="text-xs text-[#1D2B27] font-medium">{txn.description}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-[#6D7C73] text-xs">
                        <Clock className="w-3.5 h-3.5" />
                        <span>{new Date(txn.posted_at).toLocaleString('en-IN')}</span>
                      </div>
                    </div>

                    {/* Legs Subtable */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2 pt-2 border-t border-[#E3E9E2]">
                      {txn.entries.map((entry) => {
                        const targetAcc = accounts.find((a) => a.id === entry.account_id);
                        const isDebit = entry.entry_type === 'debit';
                        return (
                          <div
                            key={entry.id}
                            className={`flex items-center justify-between p-2 rounded-xl text-xs font-mono border ${
                              isDebit
                                ? 'bg-[#F5E9DF]/30 border-[#E8D5C4] text-[#9B5540]'
                                : 'bg-[#DCE9DF]/30 border-[#C5D9C9] text-[#245344]'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <span
                                className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-md ${
                                  isDebit ? 'bg-[#9B5540] text-white' : 'bg-[#245344] text-white'
                                }`}
                              >
                                {isDebit ? 'Money Out' : 'Money In'}
                              </span>
                              <span className="font-semibold text-[#1D2B27]">
                                {targetAcc ? targetAcc.account_number : entry.account_id.slice(0, 8) + '...'}
                              </span>
                              {targetAcc && (
                                <span className="text-[11px] text-[#6D7C73] font-sans truncate max-w-[120px]">
                                  ({targetAcc.name})
                                </span>
                              )}
                            </div>
                            <span className="font-bold">{formatCurrency(entry.amount)}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
