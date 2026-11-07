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

  // Active navigation tab
  const [activeTab, setActiveTab] = useState<TabType>(
    user?.role === 'auditor' ? 'journal' : 'transfer'
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

  // Adjust default tab when user is auditor
  useEffect(() => {
    if (user?.role === 'auditor') {
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
        setFormError('Network timeout or connection error. The active idempotency key has been retained. You can safely retry without duplicate posting.');
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
        setFormError('Network timeout or connection error. The active idempotency key has been retained. You can safely retry without duplicate posting.');
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
        setFormError('Network timeout or connection error. The active idempotency key has been retained. You can safely retry without duplicate posting.');
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
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-white border border-finance-border rounded-xl p-6 shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600">
                <ArrowLeftRight className="w-6 h-6" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-2xl font-bold tracking-tight text-slate-900">Financial Operations</h1>
                  <span className="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                    Task 04 Active
                  </span>
                </div>
                <p className="text-sm text-slate-500">
                  Double-entry money movement with deterministic concurrency, exact Decimal math, and zero-sum balance triggers.
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={refreshing || loading}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-indigo-600' : ''}`} />
              <span>Refresh Ledger</span>
            </button>
          </div>
        </div>

        {/* Global Error Banner */}
        {globalError && (
          <div className="mt-4 p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-center gap-2 text-rose-700 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{globalError}</span>
          </div>
        )}

        {/* Auditor Role Alert */}
        {user?.role === 'auditor' && (
          <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center gap-2 text-amber-800 text-xs sm:text-sm">
            <Shield className="w-4 h-4 text-amber-600 shrink-0" />
            <span>
              <strong>Auditor Read-Only Mode:</strong> Financial postings (transfers, deposits, withdrawals) are restricted by RBAC. You have full read-only access to inspect the double-entry transaction journal.
            </span>
          </div>
        )}
      </div>

      {/* Tabs Navigation */}
      <div className="flex border-b border-finance-border bg-white rounded-t-xl px-4 pt-2 gap-2 shadow-xs">
        {user?.role !== 'auditor' && (
          <>
            <button
              onClick={() => {
                setActiveTab('transfer');
                setFormError(null);
                setSuccessMessage(null);
              }}
              className={`pb-3 px-4 text-sm font-semibold border-b-2 flex items-center gap-2 transition ${
                activeTab === 'transfer'
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <ArrowLeftRight className="w-4 h-4" />
              <span>Internal Transfer</span>
            </button>

            <button
              onClick={() => {
                setActiveTab('deposit');
                setFormError(null);
                setSuccessMessage(null);
              }}
              className={`pb-3 px-4 text-sm font-semibold border-b-2 flex items-center gap-2 transition ${
                activeTab === 'deposit'
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <ArrowDownLeft className="w-4 h-4 text-emerald-600" />
              <span>Simulated Deposit</span>
            </button>

            <button
              onClick={() => {
                setActiveTab('withdraw');
                setFormError(null);
                setSuccessMessage(null);
              }}
              className={`pb-3 px-4 text-sm font-semibold border-b-2 flex items-center gap-2 transition ${
                activeTab === 'withdraw'
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <ArrowUpRight className="w-4 h-4 text-amber-600" />
              <span>Simulated Withdrawal</span>
            </button>
          </>
        )}

        <button
          onClick={() => {
            setActiveTab('journal');
            setFormError(null);
            setSuccessMessage(null);
          }}
          className={`pb-3 px-4 text-sm font-semibold border-b-2 flex items-center gap-2 transition ${
            activeTab === 'journal'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <BookOpen className="w-4 h-4" />
          <span>Transaction Journal</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600 font-mono">
            {totalTransactions}
          </span>
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
      <div className="bg-white border border-finance-border rounded-xl p-6 shadow-xs">
        {/* 1. Internal Transfer Form */}
        {activeTab === 'transfer' && (
          <form onSubmit={handleTransfer} className="max-w-2xl space-y-5">
            <div>
              <h2 className="text-base font-bold text-slate-900">Peer-to-Peer Inter-Account Transfer</h2>
              <p className="text-xs text-slate-500">
                Atomically moves funds between two distinct customer accounts with mathematical money conservation (&Delta; Total Funds = 0.00).
              </p>
            </div>

            {/* Active Idempotency Key Audit Badge */}
            <div className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-mono text-slate-600">
              <div className="flex items-center gap-2">
                <Shield className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                <span className="font-medium text-slate-700 font-sans">Active Idempotency Key:</span>
                <span className="text-indigo-600 font-semibold">{transferKey.slice(0, 8)}...{transferKey.slice(-4)}</span>
              </div>
              <button
                type="button"
                onClick={generateNewKeyForActiveTab}
                className="text-[11px] text-slate-500 hover:text-indigo-600 underline font-sans"
                title="Generate fresh UUID key"
              >
                Generate Fresh Key
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Sourcing Account */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Source Account (Debited) *
                </label>
                <select
                  value={transferForm.source_id}
                  onChange={(e) => updateTransferField('source_id', e.target.value)}
                  className="w-full text-xs font-medium border border-slate-300 rounded-lg p-2.5 bg-white focus:ring-2 focus:ring-indigo-500"
                  required
                >
                  {customerAccounts.map((acc) => (
                    <option key={acc.id} value={acc.id}>
                      {acc.account_number} ({acc.name}) — {formatCurrency(acc.balance)}
                    </option>
                  ))}
                </select>
                {transferForm.source_id && (
                  <div className="mt-1 text-[11px] text-slate-500">
                    Available: <span className="font-semibold font-mono text-slate-800">
                      {formatCurrency(findAccount(transferForm.source_id)?.balance || 0)}
                    </span>
                  </div>
                )}
              </div>

              {/* Destination Account */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Destination Account (Credited) *
                </label>
                <select
                  value={transferForm.destination_id}
                  onChange={(e) => updateTransferField('destination_id', e.target.value)}
                  className="w-full text-xs font-medium border border-slate-300 rounded-lg p-2.5 bg-white focus:ring-2 focus:ring-indigo-500"
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
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Amount in INR (₹) *
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400 font-mono text-sm">₹</span>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="0.00"
                  value={transferForm.amount}
                  onChange={(e) => updateTransferField('amount', e.target.value)}
                  className="w-full pl-8 text-sm font-mono border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-indigo-500"
                  required
                />
              </div>
            </div>

            {/* Description */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Transaction Description (Optional Memo)
              </label>
              <input
                type="text"
                maxLength={255}
                placeholder="e.g. Invoice payment, personal settlement"
                value={transferForm.description}
                onChange={(e) => updateTransferField('description', e.target.value)}
                className="w-full text-xs border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={formSubmitting || !transferForm.source_id || !transferForm.destination_id}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 transition disabled:opacity-50 shadow-xs"
              >
                {formSubmitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Executing Double-Entry Posting...</span>
                  </>
                ) : (
                  <>
                    <ArrowLeftRight className="w-3.5 h-3.5" />
                    <span>Post Atomic Transfer</span>
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
              <h2 className="text-base font-bold text-slate-900">Simulated External Deposit</h2>
              <p className="text-xs text-slate-500">
                Injects simulated funds into a customer account counterbalanced against platform clearing transit (<span className="font-mono font-semibold">ACC-SYSTEM02</span>).
              </p>
            </div>

            {/* Active Idempotency Key Audit Badge */}
            <div className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-mono text-slate-600">
              <div className="flex items-center gap-2">
                <Shield className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                <span className="font-medium text-slate-700 font-sans">Active Idempotency Key:</span>
                <span className="text-emerald-600 font-semibold">{depositKey.slice(0, 8)}...{depositKey.slice(-4)}</span>
              </div>
              <button
                type="button"
                onClick={generateNewKeyForActiveTab}
                className="text-[11px] text-slate-500 hover:text-emerald-600 underline font-sans"
                title="Generate fresh UUID key"
              >
                Generate Fresh Key
              </button>
            </div>

            <div className="p-3 bg-indigo-50 border border-indigo-100 rounded-lg text-xs text-indigo-900 flex items-start gap-2">
              <Info className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
              <span>
                <strong>Accounting Flow:</strong> DEBIT ACC-SYSTEM02 (Transit Asset +₹A) &rarr; CREDIT Customer Account (Liability +₹A). Preserves the double-entry equation.
              </span>
            </div>

            {/* Target Account */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Target Account (Credited) *
              </label>
              <select
                value={depositForm.account_id}
                onChange={(e) => updateDepositField('account_id', e.target.value)}
                className="w-full text-xs font-medium border border-slate-300 rounded-lg p-2.5 bg-white focus:ring-2 focus:ring-indigo-500"
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
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Deposit Amount in INR (₹) *
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400 font-mono text-sm">₹</span>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="0.00"
                  value={depositForm.amount}
                  onChange={(e) => updateDepositField('amount', e.target.value)}
                  className="w-full pl-8 text-sm font-mono border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-indigo-500"
                  required
                />
              </div>
            </div>

            {/* Description */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Deposit Memo (Optional)
              </label>
              <input
                type="text"
                maxLength={255}
                placeholder="e.g. Initial funding, wire settlement"
                value={depositForm.description}
                onChange={(e) => updateDepositField('description', e.target.value)}
                className="w-full text-xs border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={formSubmitting || !depositForm.account_id}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 transition disabled:opacity-50 shadow-xs"
              >
                {formSubmitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Posting Deposit...</span>
                  </>
                ) : (
                  <>
                    <ArrowDownLeft className="w-3.5 h-3.5" />
                    <span>Post Deposit</span>
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
              <h2 className="text-base font-bold text-slate-900">Simulated External Withdrawal</h2>
              <p className="text-xs text-slate-500">
                Disburses funds from a customer account back to platform clearing transit (<span className="font-mono font-semibold">ACC-SYSTEM02</span>), strictly guarded against overdrafts.
              </p>
            </div>

            {/* Active Idempotency Key Audit Badge */}
            <div className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-mono text-slate-600">
              <div className="flex items-center gap-2">
                <Shield className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                <span className="font-medium text-slate-700 font-sans">Active Idempotency Key:</span>
                <span className="text-amber-600 font-semibold">{withdrawKey.slice(0, 8)}...{withdrawKey.slice(-4)}</span>
              </div>
              <button
                type="button"
                onClick={generateNewKeyForActiveTab}
                className="text-[11px] text-slate-500 hover:text-amber-600 underline font-sans"
                title="Generate fresh UUID key"
              >
                Generate Fresh Key
              </button>
            </div>

            <div className="p-3 bg-amber-50 border border-amber-100 rounded-lg text-xs text-amber-900 flex items-start gap-2">
              <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <span>
                <strong>Accounting Flow:</strong> DEBIT Customer Account (Liability -₹A) &rarr; CREDIT ACC-SYSTEM02 (Transit Asset -₹A). Overdrafts are rejected with zero balance change.
              </span>
            </div>

            {/* Source Account */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Source Account (Debited) *
              </label>
              <select
                value={withdrawForm.account_id}
                onChange={(e) => updateWithdrawField('account_id', e.target.value)}
                className="w-full text-xs font-medium border border-slate-300 rounded-lg p-2.5 bg-white focus:ring-2 focus:ring-indigo-500"
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
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Withdrawal Amount in INR (₹) *
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400 font-mono text-sm">₹</span>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="0.00"
                  value={withdrawForm.amount}
                  onChange={(e) => updateWithdrawField('amount', e.target.value)}
                  className="w-full pl-8 text-sm font-mono border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-indigo-500"
                  required
                />
              </div>
            </div>

            {/* Description */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Withdrawal Memo (Optional)
              </label>
              <input
                type="text"
                maxLength={255}
                placeholder="e.g. ATM withdrawal, vendor payout"
                value={withdrawForm.description}
                onChange={(e) => updateWithdrawField('description', e.target.value)}
                className="w-full text-xs border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={formSubmitting || !withdrawForm.account_id}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-amber-600 text-white text-xs font-semibold hover:bg-amber-700 transition disabled:opacity-50 shadow-xs"
              >
                {formSubmitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Posting Withdrawal...</span>
                  </>
                ) : (
                  <>
                    <ArrowUpRight className="w-3.5 h-3.5" />
                    <span>Disburse Withdrawal</span>
                  </>
                )}
              </button>
            </div>
          </form>
        )}

        {/* 4. Transaction Journal */}
        {activeTab === 'journal' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-bold text-slate-900">Double-Entry Transaction Journal</h2>
                <p className="text-xs text-slate-500">
                  Chronological, immutable ledger of all debits and credits recorded under zero-sum balance constraints.
                </p>
              </div>
              <span className="text-xs text-slate-400 font-mono">
                Showing {transactions.length} of {totalTransactions}
              </span>
            </div>

            {loading ? (
              <div className="py-12 text-center text-slate-400 text-sm">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-500" />
                Loading ledger records...
              </div>
            ) : transactions.length === 0 ? (
              <div className="py-12 text-center text-slate-400 text-sm border-2 border-dashed border-slate-200 rounded-xl">
                <Wallet className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                <div className="font-semibold text-slate-600">No transactions recorded yet</div>
                <div className="text-xs text-slate-400">Perform a deposit or transfer to generate double-entry entries.</div>
              </div>
            ) : (
              <div className="divide-y divide-slate-100 border border-slate-200 rounded-xl overflow-hidden">
                {transactions.map((txn) => (
                  <div key={txn.id} className="p-4 hover:bg-slate-50 transition">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-slate-900 px-2 py-0.5 rounded bg-slate-100 border border-slate-200">
                          {txn.reference}
                        </span>
                        <span
                          className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded ${
                            txn.transaction_type === 'transfer'
                              ? 'bg-indigo-100 text-indigo-800'
                              : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {txn.transaction_type}
                        </span>
                        <span className="text-xs text-slate-700 font-medium">{txn.description}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-slate-400 text-xs">
                        <Clock className="w-3.5 h-3.5" />
                        <span>{new Date(txn.posted_at).toLocaleString('en-IN')}</span>
                      </div>
                    </div>

                    {/* Double-Entry Legs Subtable */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2 pt-2 border-t border-slate-100">
                      {txn.entries.map((entry) => {
                        const targetAcc = accounts.find((a) => a.id === entry.account_id);
                        const isDebit = entry.entry_type === 'debit';
                        return (
                          <div
                            key={entry.id}
                            className={`flex items-center justify-between p-2 rounded-lg text-xs font-mono border ${
                              isDebit
                                ? 'bg-indigo-50/50 border-indigo-100 text-indigo-900'
                                : 'bg-emerald-50/50 border-emerald-100 text-emerald-900'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <span
                                className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${
                                  isDebit ? 'bg-indigo-600 text-white' : 'bg-emerald-600 text-white'
                                }`}
                              >
                                {entry.entry_type}
                              </span>
                              <span className="font-semibold">
                                {targetAcc ? targetAcc.account_number : entry.account_id.slice(0, 8) + '...'}
                              </span>
                              {targetAcc && (
                                <span className="text-[11px] text-slate-500 font-sans truncate max-w-[120px]">
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
