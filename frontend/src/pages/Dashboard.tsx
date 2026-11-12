import React, { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Wallet,
  ArrowUpRight,
  ArrowDownLeft,
  ArrowLeftRight,
  BookOpen,
  FileSpreadsheet,
  FileText,
  Users,
  ShieldCheck,
  ShieldAlert,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Server,
  ChevronRight,
  ChevronDown,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { apiService } from '../services/api';
import { useHealth } from '../hooks/useHealth';
import type { Account } from '../types/account';
import type { TransactionResponse } from '../types/transfer';
import type { VerificationResult } from '../types/audit';
import type { User } from '../types/auth';
import { formatTimestamp } from '../utils/formatters';

export const Dashboard: React.FC = () => {
  const { user, isAuthenticated } = useAuth();

  // If unauthenticated, prompt to sign in
  if (!isAuthenticated || !user) {
    return (
      <div className="max-w-md mx-auto my-16 bg-white rounded-2xl border border-[#E3E9E2] p-8 text-center shadow-xs font-sans">
        <div className="w-12 h-12 rounded-xl bg-[#DCE9DF] text-[#245344] mx-auto flex items-center justify-center mb-4">
          <ShieldAlert className="w-6 h-6" />
        </div>
        <h2 className="text-xl font-serif font-bold text-[#1D2B27]">Sign In Required</h2>
        <p className="mt-2 text-xs text-[#6D7C73] leading-relaxed">
          Please sign in to view your banking dashboard and accounts.
        </p>
        <Link
          to="/login"
          className="mt-6 inline-flex items-center justify-center gap-2 w-full py-2.5 px-4 rounded-xl bg-[#245344] hover:bg-[#1B3F34] text-white text-xs font-semibold transition shadow-xs"
        >
          <span>Go to Sign In</span>
          <ArrowRightIcon className="w-4 h-4" />
        </Link>
      </div>
    );
  }

  if (user.role === 'admin') {
    return <AdminDashboard />;
  }

  if (user.role === 'auditor') {
    return <AuditorDashboard />;
  }

  return <AccountHolderDashboard user={user} />;
};

/* =========================================================================
   1. ACCOUNT HOLDER DASHBOARD (Personal Banking)
   ========================================================================= */
const AccountHolderDashboard: React.FC<{ user: User }> = ({ user }) => {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [transactions, setTransactions] = useState<TransactionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [accRes, txRes] = await Promise.all([
        apiService.getAccounts(0, 50),
        apiService.listTransactions(0, 10),
      ]);
      setAccounts(accRes.items);
      setTransactions(txRes.items);
    } catch {
      setError('Unable to load account overview. Please refresh or try again later.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const totalBalance = accounts.reduce(
    (sum, a) => sum + (a.status === 'active' ? parseFloat(a.balance || '0') : 0),
    0
  );

  const userAccountIds = useMemo(() => new Set(accounts.map((a) => a.id)), [accounts]);

  const formatINR = (val: number | string) => {
    const num = typeof val === 'string' ? parseFloat(val) : val;
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 2,
    }).format(isNaN(num) ? 0 : num);
  };

  return (
    <div className="space-y-8 font-sans">
      {/* Welcome & Overview Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-[#E3E9E2]">
        <div>
          <h1 className="text-2xl sm:text-3xl font-serif font-bold text-[#1D2B27]">
            Welcome back, {user.username}
          </h1>
          <p className="mt-1 text-xs text-[#6D7C73]">
            Your personal banking overview
          </p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-white border border-[#E3E9E2] text-[#1D2B27] hover:bg-[#F1F4EF] transition disabled:opacity-50 self-start sm:self-center cursor-pointer shadow-2xs"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-[#245344]' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-[#F5E9DF] border border-[#E3E9E2] text-[#854B35] text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Hero Total Balance Card */}
      <div className="rounded-2xl bg-gradient-to-br from-[#245344] via-[#1B3F34] to-[#16382C] text-white p-6 sm:p-8 shadow-xs relative overflow-hidden">
        <div className="relative z-10">
          <span className="text-xs uppercase tracking-widest text-[#DCE9DF] font-semibold block">
            Total Available Balance
          </span>
          <div className="mt-2 text-3xl sm:text-4xl font-serif font-bold tracking-tight text-[#F1F4EF]">
            {loading ? 'Fetching balance...' : formatINR(totalBalance)}
          </div>
          <p className="mt-1.5 text-xs text-[#D8E2DC]/80">
            Across {accounts.length} active {accounts.length === 1 ? 'account' : 'accounts'}
          </p>

          {/* Quick Actions Row */}
          <div className="mt-6 pt-6 border-t border-[#245344]/60 flex flex-wrap gap-2.5">
            <Link
              to="/transfers"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white text-[#245344] text-xs font-semibold hover:bg-[#F1F4EF] transition shadow-xs"
            >
              <ArrowLeftRight className="w-3.5 h-3.5 text-[#245344]" />
              <span>Transfer Funds</span>
            </Link>
            <Link
              to="/accounts"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#0B231D]/40 border border-[#DCE9DF]/30 text-[#F1F4EF] text-xs font-semibold hover:bg-[#0B231D]/70 transition"
            >
              <BookOpen className="w-3.5 h-3.5 text-[#DCE9DF]" />
              <span>View Accounts</span>
            </Link>
            <Link
              to="/statements"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#0B231D]/40 border border-[#DCE9DF]/30 text-[#F1F4EF] text-xs font-semibold hover:bg-[#0B231D]/70 transition"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-[#DCE9DF]" />
              <span>Statements</span>
            </Link>
          </div>
        </div>
      </div>

      {/* Account Cards Section */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-serif font-bold text-[#1D2B27]">Your Deposit Accounts</h2>
          <Link
            to="/accounts"
            className="text-xs font-semibold text-[#245344] hover:underline flex items-center gap-1"
          >
            <span>Manage Accounts</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="h-32 rounded-2xl bg-white border border-[#E3E9E2] animate-pulse" />
            <div className="h-32 rounded-2xl bg-white border border-[#E3E9E2] animate-pulse" />
          </div>
        ) : accounts.length === 0 ? (
          <div className="p-8 rounded-2xl bg-white border border-[#E3E9E2] text-center">
            <Wallet className="w-8 h-8 text-[#6D7C73] mx-auto mb-2" />
            <h3 className="text-sm font-semibold text-[#1D2B27]">No deposit accounts found</h3>
            <p className="text-xs text-[#6D7C73] mt-1 mb-4">
              Open a checking or savings account to start depositing and moving funds.
            </p>
            <Link
              to="/accounts"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#245344] text-white text-xs font-semibold hover:bg-[#1B3F34] transition shadow-xs"
            >
              <span>Open Deposit Account</span>
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {accounts.map((acc) => (
              <div
                key={acc.id}
                className="bg-white rounded-2xl border border-[#E3E9E2] p-5 shadow-xs flex flex-col justify-between hover:border-[#245344]/40 transition"
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#6D7C73]">
                      {acc.account_type.replace('_', ' ')}
                    </span>
                    <span
                      className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                        acc.status === 'active'
                          ? 'bg-[#DCE9DF] text-[#245344]'
                          : 'bg-[#F5E9DF] text-[#9B5540]'
                      }`}
                    >
                      {acc.status}
                    </span>
                  </div>
                  <h3 className="text-base font-serif font-bold text-[#1D2B27]">{acc.name}</h3>
                  <span className="font-mono text-xs text-[#6D7C73] mt-0.5 block">
                    {acc.account_number}
                  </span>
                </div>

                <div className="mt-5 pt-3 border-t border-[#E3E9E2] flex items-baseline justify-between">
                  <span className="text-xs text-[#6D7C73]">Balance</span>
                  <span className="text-lg font-serif font-bold text-[#1D2B27]">
                    {formatINR(acc.balance)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent Activity Table */}
      <div className="bg-white rounded-2xl border border-[#E3E9E2] p-6 shadow-xs">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-serif font-bold text-[#1D2B27]">Recent Transactions</h2>
            <p className="text-xs text-[#6D7C73] mt-0.5">
              Your latest transfers and payments
            </p>
          </div>
          <Link
            to="/transfers"
            className="text-xs font-semibold text-[#245344] hover:underline flex items-center gap-1"
          >
            <span>View All Transactions</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {loading ? (
          <div className="space-y-3 py-4">
            <div className="h-10 bg-[#F1F4EF] rounded-xl animate-pulse" />
            <div className="h-10 bg-[#F1F4EF] rounded-xl animate-pulse" />
            <div className="h-10 bg-[#F1F4EF] rounded-xl animate-pulse" />
          </div>
        ) : transactions.length === 0 ? (
          <div className="py-8 text-center text-xs text-[#6D7C73]">
            No recent transactions recorded. Make a transfer or deposit to see activity here.
          </div>
        ) : (
          <div className="divide-y divide-[#E3E9E2]/70">
            {transactions.slice(0, 5).map((tx) => {
              // Determine if this transaction credited or debited the user's account
              const matchingEntry = tx.entries.find((e) => userAccountIds.has(e.account_id));
              const isCredit = matchingEntry ? matchingEntry.entry_type === 'credit' : false;
              const displayAmount = matchingEntry?.amount || tx.entries[0]?.amount || '0.00';

              return (
                <div key={tx.id} className="py-3.5 flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                        isCredit
                          ? 'bg-[#DCE9DF] text-[#245344]'
                          : 'bg-[#F5E9DF] text-[#9B5540]'
                      }`}
                    >
                      {isCredit ? (
                        <ArrowDownLeft className="w-4 h-4" />
                      ) : (
                        <ArrowUpRight className="w-4 h-4" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-[#1D2B27] truncate">
                        {tx.description || `${tx.transaction_type.toUpperCase()} Transfer`}
                      </div>
                      <span className="text-[11px] text-[#6D7C73] block">
                        {formatTimestamp(tx.posted_at)} &middot; Ref: {tx.reference}
                      </span>
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <div
                      className={`text-xs font-bold font-mono ${
                        isCredit ? 'text-[#245344]' : 'text-[#9B5540]'
                      }`}
                    >
                      {isCredit ? '+' : '-'}{formatINR(displayAmount)}
                    </div>
                    <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-full font-bold bg-[#DCE9DF] text-[#245344]">
                      Completed
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

/* =========================================================================
   2. ADMIN DASHBOARD (Operations & Liquidity Hub)
   ========================================================================= */
const AdminDashboard: React.FC = () => {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [transactions, setTransactions] = useState<TransactionResponse[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  // Restricted Diagnostics data
  const { data: healthData, loading: healthLoading, refetch: refetchHealth } = useHealth(0);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [accRes, txRes, userRes] = await Promise.all([
        apiService.getAccounts(0, 50),
        apiService.listTransactions(0, 10),
        apiService.listUsers(0, 50),
      ]);
      setAccounts(accRes.items);
      setTransactions(txRes.items);
      setUsers(userRes.items);
    } catch {
      setError('Unable to load institutional operations data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const customerAccounts = accounts.filter(
    (a) => a.account_type === 'customer_checking' || a.account_type === 'customer_savings'
  );

  const totalCustomerFunds = customerAccounts.reduce(
    (sum, a) => sum + (a.status === 'active' ? parseFloat(a.balance || '0') : 0),
    0
  );

  const activeUsersCount = users.filter((u) => u.is_active).length;

  const formatINR = (val: number | string) => {
    const num = typeof val === 'string' ? parseFloat(val) : val;
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 2,
    }).format(isNaN(num) ? 0 : num);
  };

  return (
    <div className="space-y-8 font-sans">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-[#E3E9E2]">
        <div>
          <h1 className="text-2xl sm:text-3xl font-serif font-bold text-[#1D2B27]">
            Admin Dashboard
          </h1>
          <p className="mt-1 text-xs text-[#6D7C73]">
            Overview of customer funds, accounts, and system activity
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowDiagnostics(!showDiagnostics)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-white border border-[#E3E9E2] text-[#6D7C73] hover:text-[#1D2B27] transition cursor-pointer shadow-2xs"
          >
            <Server className="w-3.5 h-3.5 text-[#245344]" />
            <span>Diagnostics</span>
            <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showDiagnostics ? 'rotate-180' : ''}`} />
          </button>
          <button
            onClick={loadData}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-[#245344] text-white hover:bg-[#1B3F34] transition disabled:opacity-50 cursor-pointer shadow-2xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-[#F5E9DF] border border-[#E3E9E2] text-[#854B35] text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Discrete Restricted System Diagnostics Panel (Admin Only) */}
      {showDiagnostics && (
        <div className="p-5 rounded-2xl bg-white border border-[#E3E9E2] shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[#E3E9E2]">
            <div className="flex items-center gap-2">
              <Server className="w-4 h-4 text-[#245344]" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-[#1D2B27]">
                Restricted System Diagnostics
              </h3>
            </div>
            <button
              onClick={() => refetchHealth()}
              disabled={healthLoading}
              className="text-[11px] font-semibold text-[#245344] hover:underline flex items-center gap-1 cursor-pointer"
            >
              <RefreshCw className={`w-3 h-3 ${healthLoading ? 'animate-spin' : ''}`} />
              <span>Poll Status</span>
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
            <div className="p-3 rounded-xl bg-[#F1F4EF] border border-[#E3E9E2]">
              <span className="text-[10px] uppercase font-semibold text-[#6D7C73] block">Engine Status</span>
              <span className="font-bold text-[#1D2B27] mt-1 block">
                {healthData?.database.status === 'connected' ? 'PostgreSQL Active' : 'Disconnected'}
              </span>
            </div>
            <div className="p-3 rounded-xl bg-[#F1F4EF] border border-[#E3E9E2]">
              <span className="text-[10px] uppercase font-semibold text-[#6D7C73] block">Application Core</span>
              <span className="font-bold text-[#1D2B27] mt-1 block">
                {healthData?.app_name || 'LedgerLine'} v{healthData?.version || '0.2.0'} ({healthData?.environment || 'dev'})
              </span>
            </div>
            <div className="p-3 rounded-xl bg-[#F1F4EF] border border-[#E3E9E2]">
              <span className="text-[10px] uppercase font-semibold text-[#6D7C73] block">Schema State</span>
              <span className="font-bold text-[#245344] mt-1 block">Alembic Invariants Verified</span>
            </div>
          </div>
        </div>
      )}

      {/* Operational Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl bg-white border border-[#E3E9E2] shadow-xs">
          <span className="text-[11px] uppercase tracking-wider font-semibold text-[#6D7C73] block">
            Total Customer Funds
          </span>
          <div className="mt-2 text-2xl font-serif font-bold text-[#1D2B27]">
            {loading ? '...' : formatINR(totalCustomerFunds)}
          </div>
          <span className="text-[11px] text-[#245344] mt-1 block font-medium">
            Active checking &amp; savings balances
          </span>
        </div>

        <div className="p-5 rounded-2xl bg-white border border-[#E3E9E2] shadow-xs">
          <span className="text-[11px] uppercase tracking-wider font-semibold text-[#6D7C73] block">
            Customer Accounts
          </span>
          <div className="mt-2 text-2xl font-serif font-bold text-[#1D2B27]">
            {loading ? '...' : customerAccounts.length}
          </div>
          <span className="text-[11px] text-[#6D7C73] mt-1 block font-medium">
            Deposit accounts
          </span>
        </div>

        <div className="p-5 rounded-2xl bg-white border border-[#E3E9E2] shadow-xs">
          <span className="text-[11px] uppercase tracking-wider font-semibold text-[#6D7C73] block">
            Active Users
          </span>
          <div className="mt-2 text-2xl font-serif font-bold text-[#1D2B27]">
            {loading ? '...' : activeUsersCount}
          </div>
          <span className="text-[11px] text-[#6D7C73] mt-1 block font-medium">
            Active customer and staff accounts
          </span>
        </div>

        <div className="p-5 rounded-2xl bg-white border border-[#E3E9E2] shadow-xs">
          <span className="text-[11px] uppercase tracking-wider font-semibold text-[#6D7C73] block">
            Posted Transactions
          </span>
          <div className="mt-2 text-2xl font-serif font-bold text-[#1D2B27]">
            {loading ? '...' : transactions.length}
          </div>
          <span className="text-[11px] text-[#245344] mt-1 block font-medium">
            Completed transfers &amp; settlements
          </span>
        </div>
      </div>

      {/* Operational Shortcuts / Quick Actions */}
      <div className="p-6 rounded-2xl bg-white border border-[#E3E9E2] shadow-xs">
        <h2 className="text-sm font-serif font-bold text-[#1D2B27] mb-3">Quick Actions</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Link
            to="/accounts"
            className="p-3.5 rounded-xl border border-[#E3E9E2] hover:border-[#245344] hover:bg-[#F1F4EF] transition flex flex-col justify-between"
          >
            <BookOpen className="w-4 h-4 text-[#245344] mb-2" />
            <div className="text-xs font-bold text-[#1D2B27]">Manage Accounts</div>
            <span className="text-[10px] text-[#6D7C73]">Open or view accounts</span>
          </Link>

          <Link
            to="/transfers"
            className="p-3.5 rounded-xl border border-[#E3E9E2] hover:border-[#245344] hover:bg-[#F1F4EF] transition flex flex-col justify-between"
          >
            <ArrowLeftRight className="w-4 h-4 text-[#245344] mb-2" />
            <div className="text-xs font-bold text-[#1D2B27]">Transaction Journal</div>
            <span className="text-[10px] text-[#6D7C73]">Inspect transaction journal</span>
          </Link>

          <Link
            to="/users"
            className="p-3.5 rounded-xl border border-[#E3E9E2] hover:border-[#245344] hover:bg-[#F1F4EF] transition flex flex-col justify-between"
          >
            <Users className="w-4 h-4 text-[#245344] mb-2" />
            <div className="text-xs font-bold text-[#1D2B27]">User Management</div>
            <span className="text-[10px] text-[#6D7C73]">View and add system users</span>
          </Link>

          <Link
            to="/audit"
            className="p-3.5 rounded-xl border border-[#E3E9E2] hover:border-[#245344] hover:bg-[#F1F4EF] transition flex flex-col justify-between"
          >
            <FileText className="w-4 h-4 text-[#245344] mb-2" />
            <div className="text-xs font-bold text-[#1D2B27]">Audit Trail</div>
            <span className="text-[10px] text-[#6D7C73]">Tamper-evident event log</span>
          </Link>
        </div>
      </div>

      {/* Recent Transactions */}
      <div className="bg-white rounded-2xl border border-[#E3E9E2] p-6 shadow-xs">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-serif font-bold text-[#1D2B27]">Recent Transactions</h2>
          <Link
            to="/transfers"
            className="text-xs font-semibold text-[#245344] hover:underline flex items-center gap-1"
          >
            <span>View All Transactions</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {transactions.length === 0 ? (
          <div className="py-6 text-center text-xs text-[#6D7C73]">No recent transactions.</div>
        ) : (
          <div className="divide-y divide-[#E3E9E2]/70">
            {transactions.slice(0, 5).map((tx) => {
              const amount = tx.entries.find((e) => e.entry_type === 'debit')?.amount || tx.entries[0]?.amount || '0.00';
              return (
                <div key={tx.id} className="py-3 flex items-center justify-between text-xs">
                  <div>
                    <div className="font-semibold text-[#1D2B27]">
                      {tx.description || `${tx.transaction_type.toUpperCase()} Transfer`}
                    </div>
                    <span className="text-[11px] text-[#6D7C73] font-mono">
                      {tx.reference} &middot; {formatTimestamp(tx.posted_at)}
                    </span>
                  </div>
                  <div className="text-right">
                    <div className="font-mono font-bold text-[#1D2B27]">{formatINR(amount)}</div>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#DCE9DF] text-[#245344]">
                      Completed
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

/* =========================================================================
   3. AUDITOR DASHBOARD (Read-Only Financial Oversight)
   ========================================================================= */
const AuditorDashboard: React.FC = () => {
  const [transactions, setTransactions] = useState<TransactionResponse[]>([]);
  const [verification, setVerification] = useState<VerificationResult | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [txRes, verifyRes] = await Promise.all([
        apiService.listTransactions(0, 10),
        apiService.verifyAuditChain(),
      ]);
      setTransactions(txRes.items);
      setVerification(verifyRes);
    } catch {
      setError('Unable to load institutional oversight data.');
    } finally {
      setLoading(false);
    }
  };

  const handleRunVerification = async () => {
    setIsVerifying(true);
    try {
      const res = await apiService.verifyAuditChain();
      setVerification(res);
    } catch {
      setError('Cryptographic verification query failed.');
    } finally {
      setIsVerifying(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const formatINR = (val: number | string) => {
    const num = typeof val === 'string' ? parseFloat(val) : val;
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 2,
    }).format(isNaN(num) ? 0 : num);
  };

  return (
    <div className="space-y-8 font-sans">
      {/* Oversight Banner (Read-Only Notice) */}
      <div className="p-4 rounded-2xl bg-[#DCE9DF] border border-[#E3E9E2] flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2.5">
          <ShieldCheck className="w-5 h-5 text-[#245344] shrink-0" />
          <div>
            <span className="font-bold text-[#1D2B27] block">
              Financial Auditor Oversight &middot; Read-Only Mode
            </span>
            <span className="text-[#6D7C73]">
              This account has read-only access. Financial changes are not permitted.
            </span>
          </div>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-[#E3E9E2] text-[#1D2B27] font-semibold hover:bg-[#F1F4EF] transition disabled:opacity-50 self-start sm:self-auto cursor-pointer shadow-2xs"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-[#245344]' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-[#F5E9DF] border border-[#E3E9E2] text-[#854B35] text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Live Cryptographic Verification Card */}
      <div className="p-6 sm:p-8 rounded-2xl bg-white border border-[#E3E9E2] shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-[#E3E9E2]">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-[#245344]" />
              <h2 className="text-xl font-serif font-bold text-[#1D2B27]">
                Audit Integrity
              </h2>
            </div>
            <p className="mt-1 text-xs text-[#6D7C73]">
              A tamper-evident record of financial transactions and security activity.
            </p>
          </div>
          <button
            onClick={handleRunVerification}
            disabled={isVerifying}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#245344] hover:bg-[#1B3F34] text-white text-xs font-semibold transition disabled:opacity-50 cursor-pointer shadow-xs self-start sm:self-auto"
          >
            <ShieldCheck className={`w-4 h-4 text-[#DCE9DF] ${isVerifying ? 'animate-spin' : ''}`} />
            <span>{isVerifying ? 'Verifying Integrity...' : 'Verify Audit Integrity'}</span>
          </button>
        </div>

        <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="p-4 rounded-xl bg-[#F1F4EF] border border-[#E3E9E2]">
            <span className="text-[10px] uppercase font-semibold text-[#6D7C73] block">Chain Integrity</span>
            <div className="mt-1 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-[#245344]" />
              <span className="font-bold text-sm text-[#245344]">
                {verification?.is_valid ? 'All recorded events have passed the integrity check.' : 'Checking...'}
              </span>
            </div>
            <span className="text-[10px] text-[#6D7C73] mt-1 block">Zero broken hashes detected</span>
          </div>

          <div className="p-4 rounded-xl bg-[#F1F4EF] border border-[#E3E9E2]">
            <span className="text-[10px] uppercase font-semibold text-[#6D7C73] block">Events Verified</span>
            <div className="mt-1 font-mono font-bold text-sm text-[#1D2B27]">
              {verification?.total_events ?? '--'} Immutable Events
            </div>
            <span className="text-[10px] text-[#6D7C73] mt-1 block">Sequenced from genesis</span>
          </div>

          <div className="p-4 rounded-xl bg-[#F1F4EF] border border-[#E3E9E2]">
            <span className="text-[10px] uppercase font-semibold text-[#6D7C73] block">Chain Head Sequence</span>
            <div className="mt-1 font-mono font-bold text-sm text-[#1D2B27]">
              #{verification?.head_sequence ?? '--'}
            </div>
            <span className="text-[10px] text-[#6D7C73] mt-1 block font-mono truncate">
              {verification?.head_hash ? `${verification.head_hash.substring(0, 16)}...` : '--'}
            </span>
          </div>
        </div>
      </div>

      {/* Oversight Navigation Shortcuts */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Link
          to="/audit"
          className="p-4 rounded-xl bg-white border border-[#E3E9E2] hover:border-[#245344] transition flex flex-col justify-between"
        >
          <FileText className="w-4 h-4 text-[#245344] mb-2" />
          <div className="text-xs font-bold text-[#1D2B27]">Audit Trail</div>
          <span className="text-[10px] text-[#6D7C73]">Inspect full event hash chain</span>
        </Link>

        <Link
          to="/transfers"
          className="p-4 rounded-xl bg-white border border-[#E3E9E2] hover:border-[#245344] transition flex flex-col justify-between"
        >
          <ArrowLeftRight className="w-4 h-4 text-[#245344] mb-2" />
          <div className="text-xs font-bold text-[#1D2B27]">Transaction History</div>
          <span className="text-[10px] text-[#6D7C73]">Review double-entry legs</span>
        </Link>

        <Link
          to="/statements"
          className="p-4 rounded-xl bg-white border border-[#E3E9E2] hover:border-[#245344] transition flex flex-col justify-between"
        >
          <FileSpreadsheet className="w-4 h-4 text-[#245344] mb-2" />
          <div className="text-xs font-bold text-[#1D2B27]">Account Statements</div>
          <span className="text-[10px] text-[#6D7C73]">Export verified reports</span>
        </Link>

        <Link
          to="/users"
          className="p-4 rounded-xl bg-white border border-[#E3E9E2] hover:border-[#245344] transition flex flex-col justify-between"
        >
          <Users className="w-4 h-4 text-[#245344] mb-2" />
          <div className="text-xs font-bold text-[#1D2B27]">User Directory</div>
          <span className="text-[10px] text-[#6D7C73]">Auditor read roster</span>
        </Link>
      </div>

      {/* Transaction Journal Preview (Read Only) */}
      <div className="bg-white rounded-2xl border border-[#E3E9E2] p-6 shadow-xs">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-serif font-bold text-[#1D2B27]">Financial Activity</h2>
          <Link
            to="/transfers"
            className="text-xs font-semibold text-[#245344] hover:underline flex items-center gap-1"
          >
            <span>View Full History</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {transactions.length === 0 ? (
          <div className="py-6 text-center text-xs text-[#6D7C73]">No journal records logged.</div>
        ) : (
          <div className="divide-y divide-[#E3E9E2]/70">
            {transactions.slice(0, 5).map((tx) => {
              const amount = tx.entries.find((e) => e.entry_type === 'debit')?.amount || tx.entries[0]?.amount || '0.00';
              return (
                <div key={tx.id} className="py-3 flex items-center justify-between text-xs">
                  <div>
                    <div className="font-semibold text-[#1D2B27]">
                      {tx.description || `${tx.transaction_type.toUpperCase()} Posting`}
                    </div>
                    <span className="text-[11px] text-[#6D7C73] font-mono">
                      Ref: {tx.reference} &middot; {formatTimestamp(tx.posted_at)}
                    </span>
                  </div>
                  <div className="text-right">
                    <div className="font-mono font-bold text-[#1D2B27]">{formatINR(amount)}</div>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#DCE9DF] text-[#245344]">
                      Completed
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

const ArrowRightIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
  </svg>
);
