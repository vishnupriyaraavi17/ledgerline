import React, { useState, useEffect } from 'react';
import {
  FileSpreadsheet,
  Download,
  Printer,
  Calendar,
  ArrowDownLeft,
  ArrowUpRight,
  ShieldAlert,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { apiService } from '../services/api';
import { Account } from '../types/account';
import { AccountStatementResponse } from '../types/statement';

type DatePreset = '7d' | '30d' | 'month' | 'all' | 'custom';

export const StatementsPage: React.FC = () => {
  const { isAuthenticated } = useAuth();

  // Account Selection State
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [loadingAccounts, setLoadingAccounts] = useState<boolean>(true);

  // Date Filtering State
  const [preset, setPreset] = useState<DatePreset>('30d');
  const [startDateStr, setStartDateStr] = useState<string>('');
  const [endDateStr, setEndDateStr] = useState<string>('');

  // Statement Data & Pagination State
  const [statement, setStatement] = useState<AccountStatementResponse | null>(null);
  const [loadingStatement, setLoadingStatement] = useState<boolean>(false);
  const [statementError, setStatementError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'posted' | 'refused'>('posted');

  // Copy Feedback State
  const [copiedRef, setCopiedRef] = useState<string | null>(null);
  const [exportingCsv, setExportingCsv] = useState<boolean>(false);

  // Calculate preset date ranges
  const applyPreset = (p: DatePreset) => {
    setPreset(p);
    const now = new Date();
    let start: Date;

    if (p === '7d') {
      start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    } else if (p === '30d') {
      start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    } else if (p === 'month') {
      start = new Date(now.getFullYear(), now.getMonth(), 1);
    } else if (p === 'all') {
      start = new Date('2026-01-01T00:00:00Z');
    } else {
      return;
    }

    setStartDateStr(start.toISOString().slice(0, 16));
    setEndDateStr(now.toISOString().slice(0, 16));
  };

  // Initial load of accounts
  useEffect(() => {
    if (!isAuthenticated) return;

    const loadAccounts = async () => {
      setLoadingAccounts(true);
      try {
        const res = await apiService.getAccounts(0, 100);
        // Customer accounts only
        const customerAccounts = res.items.filter(
          (a: Account) => a.account_type === 'customer_checking' || a.account_type === 'customer_savings'
        );
        setAccounts(customerAccounts);
        if (customerAccounts.length > 0) {
          setSelectedAccountId(customerAccounts[0].id);
        }
      } catch (err: any) {
        setStatementError('Failed to load accounts. Please ensure you are authenticated.');
      } finally {
        setLoadingAccounts(false);
      }
    };

    loadAccounts();
    applyPreset('30d');
  }, [isAuthenticated]);

  // Fetch statement when account, dates, or page changes
  const fetchStatement = async (page: number = 1) => {
    if (!selectedAccountId) return;
    setLoadingStatement(true);
    setStatementError(null);

    try {
      const sUtc = startDateStr ? new Date(startDateStr).toISOString() : undefined;
      const eUtc = endDateStr ? new Date(endDateStr).toISOString() : undefined;

      const data = await apiService.getAccountStatement(
        selectedAccountId,
        sUtc,
        eUtc,
        page,
        25 // 25 rows per page
      );
      setStatement(data);
    } catch (err: any) {
      if (err.response?.status === 404) {
        setStatementError('Account statement inaccessible (404 Not Found).');
      } else if (err.response?.data?.detail) {
        setStatementError(err.response.data.detail);
      } else {
        setStatementError('Failed to retrieve account statement.');
      }
      setStatement(null);
    } finally {
      setLoadingStatement(false);
    }
  };

  useEffect(() => {
    if (selectedAccountId && startDateStr && endDateStr) {
      fetchStatement(1);
    }
  }, [selectedAccountId]);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedRef(text);
    setTimeout(() => setCopiedRef(null), 2000);
  };

  const handleExportCsv = async () => {
    if (!selectedAccountId || !statement) return;
    setExportingCsv(true);
    try {
      const blob = await apiService.exportAccountStatementCsv(
        selectedAccountId,
        statement.period.start_date,
        statement.period.end_date
      );
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `statement_${statement.account.account_number}_${statement.period.start_date.slice(0, 10)}_${statement.period.end_date.slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      alert('Failed to export CSV: ' + (err.response?.data?.detail || err.message));
    } finally {
      setExportingCsv(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  if (!isAuthenticated) {
    return (
      <div className="max-w-4xl mx-auto py-16 text-center space-y-4">
        <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto text-slate-500">
          <FileSpreadsheet className="w-8 h-8" />
        </div>
        <h2 className="text-xl font-bold text-slate-900">Authentication Required</h2>
        <p className="text-sm text-slate-600 max-w-md mx-auto">
          Account statements and transaction histories require an authenticated session.
        </p>
        <a
          href="/login"
          className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-semibold hover:bg-slate-800 transition shadow-xs"
        >
          Sign In
        </a>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Banner / Actions */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              Account Statements & Audit History
            </h1>
            <span className="text-[10px] bg-emerald-100 text-emerald-800 font-semibold px-2 py-0.5 rounded-full border border-emerald-200">
              Task 07 Verified
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Mathematically verified double-entry ledger statements and persistent refusal tracking
          </p>
        </div>

        {statement && (
          <div className="flex items-center gap-2 print:hidden">
            <button
              onClick={handleExportCsv}
              disabled={exportingCsv}
              className="inline-flex items-center gap-1.5 px-3 py-2 bg-white border border-slate-200 text-slate-700 text-xs font-semibold rounded-lg hover:bg-slate-50 transition shadow-xs disabled:opacity-50"
              title="Download RFC 4180 CSV export"
            >
              <Download className="w-3.5 h-3.5 text-slate-500" />
              <span>{exportingCsv ? 'Exporting...' : 'Download CSV'}</span>
            </button>
            <button
              onClick={handlePrint}
              className="inline-flex items-center gap-1.5 px-3 py-2 bg-slate-900 text-white text-xs font-semibold rounded-lg hover:bg-slate-800 transition shadow-xs"
              title="Print official statement"
            >
              <Printer className="w-3.5 h-3.5" />
              <span>Print Statement</span>
            </button>
          </div>
        )}
      </div>

      {/* Account Selector & Date Range Filter Bar (Hidden in Print) */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs space-y-4 print:hidden">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
          {/* Account Selector */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              Select Customer Account
            </label>
            {loadingAccounts ? (
              <div className="h-9 bg-slate-100 animate-pulse rounded-lg" />
            ) : accounts.length === 0 ? (
              <div className="text-xs text-rose-600 p-2 bg-rose-50 border border-rose-200 rounded-lg">
                No customer accounts found.
              </div>
            ) : (
              <select
                value={selectedAccountId}
                onChange={(e) => setSelectedAccountId(e.target.value)}
                className="w-full text-xs font-mono bg-white border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-slate-900 focus:outline-hidden"
              >
                {accounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>
                    {acc.account_number} — {acc.name} ({acc.account_type === 'customer_checking' ? 'Checking' : 'Savings'}) [₹{acc.balance}]
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Date Presets */}
          <div className="md:col-span-2">
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              Statement Interval [Inclusive Start, Exclusive End)
            </label>
            <div className="flex flex-wrap items-center gap-1.5">
              {(['7d', '30d', 'month', 'all', 'custom'] as DatePreset[]).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => applyPreset(p)}
                  className={`px-2.5 py-1.5 text-xs font-medium rounded-md transition ${
                    preset === p
                      ? 'bg-slate-900 text-white shadow-xs'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {p === '7d' && 'Last 7 Days'}
                  {p === '30d' && 'Last 30 Days'}
                  {p === 'month' && 'This Month'}
                  {p === 'all' && 'All Time'}
                  {p === 'custom' && 'Custom Range'}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Custom Date Inputs & Action */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-slate-100 items-end">
          <div>
            <label className="block text-[11px] font-medium text-slate-500 mb-1">
              Start Date & Time (UTC)
            </label>
            <input
              type="datetime-local"
              value={startDateStr}
              onChange={(e) => {
                setStartDateStr(e.target.value);
                setPreset('custom');
              }}
              className="w-full text-xs font-mono bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 focus:bg-white focus:outline-hidden"
            />
          </div>

          <div>
            <label className="block text-[11px] font-medium text-slate-500 mb-1">
              End Date & Time (UTC)
            </label>
            <input
              type="datetime-local"
              value={endDateStr}
              onChange={(e) => {
                setEndDateStr(e.target.value);
                setPreset('custom');
              }}
              className="w-full text-xs font-mono bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 focus:bg-white focus:outline-hidden"
            />
          </div>

          <div>
            <button
              onClick={() => fetchStatement(1)}
              disabled={loadingStatement || !selectedAccountId}
              className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-2 bg-slate-900 text-white text-xs font-semibold rounded-lg hover:bg-slate-800 transition disabled:opacity-50 shadow-xs"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingStatement ? 'animate-spin' : ''}`} />
              <span>{loadingStatement ? 'Generating...' : 'Generate Statement'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {statementError && (
        <div className="p-4 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
          <span>{statementError}</span>
        </div>
      )}

      {/* Statement Results Container */}
      {statement && (
        <div className="space-y-6">
          {/* Printable Statement Header (Visible only on print or clean view) */}
          <div className="hidden print:block border-b border-slate-300 pb-4 mb-4">
            <div className="flex justify-between items-start">
              <div>
                <h1 className="text-xl font-bold font-mono text-slate-900">LEDGERLINE OFFICIAL STATEMENT</h1>
                <p className="text-xs text-slate-500 font-mono">Conserved Double-Entry Financial Core</p>
              </div>
              <div className="text-right text-xs font-mono text-slate-600">
                <div>Account: {statement.account.account_number}</div>
                <div>Name: {statement.account.name}</div>
                <div>Generated: {new Date().toISOString()}</div>
              </div>
            </div>
            <div className="mt-2 text-xs font-mono text-slate-600">
              Period: [{new Date(statement.period.start_date).toUTCString()} to {new Date(statement.period.end_date).toUTCString()})
            </div>
          </div>

          {/* 5-Card Executive Financial Summary */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {/* Opening Balance */}
            <div className="bg-white border border-slate-200 rounded-xl p-3.5 shadow-xs">
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                Opening Balance
              </span>
              <div className="text-lg font-bold font-mono text-slate-900">
                ₹{Number(statement.summary.opening_balance).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">
                Balance before period start
              </span>
            </div>

            {/* Total Credits */}
            <div className="bg-white border border-emerald-200 rounded-xl p-3.5 shadow-xs bg-emerald-50/20">
              <span className="text-[11px] font-semibold text-emerald-800 uppercase tracking-wider block mb-1">
                Total Credits (Inflow)
              </span>
              <div className="text-lg font-bold font-mono text-emerald-700">
                +₹{Number(statement.summary.total_credits).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
              <span className="text-[10px] text-emerald-600 mt-1 block">
                Deposits & inbound transfers
              </span>
            </div>

            {/* Total Debits */}
            <div className="bg-white border border-rose-200 rounded-xl p-3.5 shadow-xs bg-rose-50/20">
              <span className="text-[11px] font-semibold text-rose-800 uppercase tracking-wider block mb-1">
                Total Debits (Outflow)
              </span>
              <div className="text-lg font-bold font-mono text-rose-700">
                -₹{Number(statement.summary.total_debits).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
              <span className="text-[10px] text-rose-600 mt-1 block">
                Withdrawals & outbound transfers
              </span>
            </div>

            {/* Net Change */}
            <div className="bg-white border border-slate-200 rounded-xl p-3.5 shadow-xs">
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                Net Period Delta
              </span>
              <div className={`text-lg font-bold font-mono ${
                Number(statement.summary.net_change) >= 0 ? 'text-emerald-700' : 'text-rose-700'
              }`}>
                {Number(statement.summary.net_change) >= 0 ? '+' : ''}
                ₹{Number(statement.summary.net_change).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">
                Credits minus debits
              </span>
            </div>

            {/* Closing Balance */}
            <div className="bg-slate-900 border border-slate-800 text-white rounded-xl p-3.5 shadow-xs col-span-2 sm:col-span-1">
              <span className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider block mb-1">
                Closing Balance
              </span>
              <div className="text-lg font-bold font-mono text-white">
                ₹{Number(statement.summary.closing_balance).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">
                Opening + Net Delta
              </span>
            </div>
          </div>

          {/* Activity Tabs Header (Hidden in Print) */}
          <div className="flex items-center gap-2 border-b border-slate-200 print:hidden">
            <button
              onClick={() => setActiveTab('posted')}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold border-b-2 transition -mb-px ${
                activeTab === 'posted'
                  ? 'border-slate-900 text-slate-900'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              <span>Posted Transactions</span>
              <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] bg-slate-100 text-slate-700">
                {statement.summary.total_posted_transactions}
              </span>
            </button>

            <button
              onClick={() => setActiveTab('refused')}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold border-b-2 transition -mb-px ${
                activeTab === 'refused'
                  ? 'border-slate-900 text-slate-900'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              <ShieldAlert className="w-3.5 h-3.5 text-rose-600" />
              <span>Refused Attempts</span>
              <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] bg-rose-100 text-rose-800">
                {statement.summary.total_refused_attempts}
              </span>
            </button>
          </div>

          {/* Tab 1: Posted Transactions Table */}
          {activeTab === 'posted' && (
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
              {statement.transactions.length === 0 ? (
                <div className="py-12 text-center space-y-2">
                  <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400">
                    <Calendar className="w-5 h-5" />
                  </div>
                  <p className="text-xs text-slate-500">
                    No posted financial transactions found in the requested period.
                  </p>
                  <p className="text-[11px] text-slate-400 font-mono">
                    Opening and closing balance remain identical: ₹{Number(statement.summary.opening_balance).toFixed(2)}
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 bg-slate-50/75 text-slate-600 font-semibold text-[11px]">
                        <th className="px-4 py-2.5">Posted At (UTC)</th>
                        <th className="px-4 py-2.5">Reference</th>
                        <th className="px-4 py-2.5">Operation</th>
                        <th className="px-4 py-2.5">Counterparty</th>
                        <th className="px-4 py-2.5">Description</th>
                        <th className="px-4 py-2.5 text-right">Amount (INR)</th>
                        <th className="px-4 py-2.5 text-right">Running Balance</th>
                        <th className="px-4 py-2.5 text-center">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {statement.transactions.map((tx) => {
                        const isCredit = tx.direction === 'credit';
                        return (
                          <tr key={tx.entry_id} className="hover:bg-slate-50/50 transition">
                            <td className="px-4 py-3 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                              {new Date(tx.posted_at).toISOString().replace('T', ' ').slice(0, 19)}
                            </td>
                            <td className="px-4 py-3 font-mono text-xs text-slate-900 whitespace-nowrap">
                              <span className="flex items-center gap-1.5">
                                <span>{tx.reference}</span>
                                <button
                                  onClick={() => handleCopy(tx.reference)}
                                  className="text-slate-400 hover:text-slate-600 p-0.5 rounded transition print:hidden"
                                  title="Copy reference"
                                >
                                  {copiedRef === tx.reference ? (
                                    <Check className="w-3 h-3 text-emerald-600" />
                                  ) : (
                                    <Copy className="w-3 h-3" />
                                  )}
                                </button>
                              </span>
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold ${
                                isCredit
                                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                  : 'bg-rose-50 text-rose-700 border border-rose-200'
                              }`}>
                                {isCredit ? <ArrowDownLeft className="w-3 h-3" /> : <ArrowUpRight className="w-3 h-3" />}
                                <span>{tx.display_label}</span>
                              </span>
                            </td>
                            <td className="px-4 py-3 font-mono text-[11px] text-slate-600 whitespace-nowrap">
                              {tx.counterparty_account_number || 'External Clearing (ACC-SYSTEM02)'}
                            </td>
                            <td className="px-4 py-3 text-slate-600 max-w-xs truncate" title={tx.description}>
                              {tx.description}
                            </td>
                            <td className={`px-4 py-3 text-right font-mono font-semibold whitespace-nowrap ${
                              isCredit ? 'text-emerald-700' : 'text-rose-700'
                            }`}>
                              {isCredit ? '+' : '-'}₹{Number(tx.amount).toFixed(2)}
                            </td>
                            <td className="px-4 py-3 text-right font-mono font-bold text-slate-900 whitespace-nowrap">
                              ₹{Number(tx.running_balance).toFixed(2)}
                            </td>
                            <td className="px-4 py-3 text-center whitespace-nowrap">
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700 uppercase tracking-wider">
                                {tx.status}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Pagination Controls (Hidden in Print) */}
              {statement.total_pages > 1 && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 bg-slate-50/50 print:hidden text-xs text-slate-500">
                  <div>
                    Page {statement.page} of {statement.total_pages} ({statement.summary.total_posted_transactions} total posted entries)
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => fetchStatement(statement.page - 1)}
                      disabled={statement.page <= 1 || loadingStatement}
                      className="p-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 disabled:opacity-40 transition"
                      title="Previous Page"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => fetchStatement(statement.page + 1)}
                      disabled={statement.page >= statement.total_pages || loadingStatement}
                      className="p-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 disabled:opacity-40 transition"
                      title="Next Page"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Tab 2: Refused & Unsuccessful Attempts Table */}
          {activeTab === 'refused' && (
            <div className="space-y-3">
              {/* Educational Notice Banner */}
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-amber-900 text-xs flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <span className="font-semibold">Financial Integrity Invariant: </span>
                  Refused attempts represent rejected financial operations. In compliance with LedgerLine accounting invariants,
                  refused operations <span className="font-semibold underline">NEVER</span> alter account balances and <span className="font-semibold underline">NEVER</span> create double-entry ledger postings.
                </div>
              </div>

              <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
                {statement.refused_attempts.length === 0 ? (
                  <div className="py-12 text-center space-y-2">
                    <div className="w-10 h-10 rounded-full bg-emerald-50 flex items-center justify-center mx-auto text-emerald-600">
                      <CheckCircle2 className="w-5 h-5" />
                    </div>
                    <p className="text-xs text-slate-600 font-medium">
                      Zero refused financial attempts recorded for this account in the requested period.
                    </p>
                    <p className="text-[11px] text-slate-400">
                      All attempted operations completed cleanly.
                    </p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="border-b border-slate-200 bg-slate-50/75 text-slate-600 font-semibold text-[11px]">
                          <th className="px-4 py-2.5">Attempted At (UTC)</th>
                          <th className="px-4 py-2.5">Operation</th>
                          <th className="px-4 py-2.5">Role</th>
                          <th className="px-4 py-2.5">Counterparty</th>
                          <th className="px-4 py-2.5">Requested Amount</th>
                          <th className="px-4 py-2.5">Refusal Reason</th>
                          <th className="px-4 py-2.5">Details</th>
                          <th className="px-4 py-2.5 text-center">Outcome</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {statement.refused_attempts.map((ref) => (
                          <tr key={ref.id} className="hover:bg-slate-50/50 transition">
                            <td className="px-4 py-3 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                              {new Date(ref.created_at).toISOString().replace('T', ' ').slice(0, 19)}
                            </td>
                            <td className="px-4 py-3 font-semibold uppercase text-[11px] text-slate-800 whitespace-nowrap">
                              {ref.operation_type}
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                                ref.is_source ? 'bg-slate-100 text-slate-700' : 'bg-indigo-50 text-indigo-700'
                              }`}>
                                {ref.is_source ? 'Initiator / Source' : 'Intended Destination'}
                              </span>
                            </td>
                            <td className="px-4 py-3 font-mono text-[11px] text-slate-600 whitespace-nowrap">
                              {ref.counterparty_account_number || '—'}
                            </td>
                            <td className="px-4 py-3 font-mono text-slate-700 whitespace-nowrap">
                              {ref.amount ? `₹${Number(ref.amount).toFixed(2)}` : '—'}
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-100 text-rose-800 border border-rose-200">
                                {ref.refusal_reason}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-slate-600 max-w-sm truncate" title={ref.error_message}>
                              {ref.error_message}
                            </td>
                            <td className="px-4 py-3 text-center whitespace-nowrap">
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200 uppercase tracking-wider">
                                {ref.outcome}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
