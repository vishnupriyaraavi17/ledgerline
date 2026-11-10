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

  // Helpers to convert datetime-local strings (YYYY-MM-DDTHH:mm) strictly to UTC ISO strings
  const toUtcStartIso = (val: string): string | undefined => {
    if (!val) return undefined;
    if (val.endsWith('Z')) return val;
    if (val.length === 16) return `${val}:00.000Z`;
    if (val.length === 19) return `${val}.000Z`;
    return new Date(val).toISOString();
  };

  const toUtcEndIso = (val: string): string | undefined => {
    if (!val) return undefined;
    if (val.endsWith('Z')) return val;
    // Advance the selected minute to the next minute as an exclusive UTC boundary [start, end)
    if (val.length === 16) {
      const baseDate = new Date(`${val}:00.000Z`);
      if (!isNaN(baseDate.getTime())) {
        return new Date(baseDate.getTime() + 60 * 1000).toISOString();
      }
    }
    if (val.length === 19) {
      const baseDate = new Date(`${val}.000Z`);
      if (!isNaN(baseDate.getTime())) {
        return new Date(baseDate.getTime() + 1000).toISOString();
      }
    }
    return new Date(val).toISOString();
  };

  // Calculate preset date ranges using consistent UTC
  const applyPreset = (p: DatePreset) => {
    setPreset(p);
    const now = new Date();
    let start: Date;

    if (p === '7d') {
      start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    } else if (p === '30d') {
      start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    } else if (p === 'month') {
      start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1, 0, 0, 0));
    } else if (p === 'all') {
      start = new Date('2026-01-01T00:00:00.000Z');
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
      const sUtc = toUtcStartIso(startDateStr);
      const eUtc = toUtcEndIso(endDateStr);

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
      const rawBlob = await apiService.exportAccountStatementCsv(
        selectedAccountId,
        statement.period.start_date,
        statement.period.end_date
      );
      // Prepend UTF-8 BOM (\uFEFF: bytes 0xEF, 0xBB, 0xBF) so Excel and Windows applications detect UTF-8
      const bom = new Uint8Array([0xEF, 0xBB, 0xBF]);
      const exportBlob = new Blob([bom, rawBlob], { type: 'text/csv;charset=utf-8;' });
      const url = window.URL.createObjectURL(exportBlob);
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
    <div className="space-y-6 font-sans">
      {/* Top Banner / Actions */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-[#E3E9E2] pb-5 print:hidden">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-serif font-bold tracking-tight text-[#1D2B27]">
              Account Statements
            </h1>
            <span className="text-[10px] bg-[#DCE9DF] text-[#245344] font-semibold px-2.5 py-0.5 rounded-full border border-[#C5D9C9]">
              Official Record
            </span>
          </div>
          <p className="text-xs text-[#6D7C73] mt-1">
            Periodic double-entry ledger statements, running balances, and verified transaction history
          </p>
        </div>

        {statement && (
          <div className="flex items-center gap-2 print:hidden">
            <button
              onClick={handleExportCsv}
              disabled={exportingCsv}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-white border border-[#E3E9E2] text-[#1D2B27] text-xs font-semibold rounded-xl hover:bg-[#F1F4EF] transition shadow-2xs disabled:opacity-50 cursor-pointer"
              title="Download RFC 4180 CSV export"
            >
              <Download className="w-3.5 h-3.5 text-[#245344]" />
              <span>{exportingCsv ? 'Exporting...' : 'Download CSV'}</span>
            </button>
            <button
              onClick={handlePrint}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-[#245344] hover:bg-[#1B3F34] text-white text-xs font-semibold rounded-xl transition shadow-xs cursor-pointer"
              title="Print official statement"
            >
              <Printer className="w-3.5 h-3.5 text-[#DCE9DF]" />
              <span>Print Statement</span>
            </button>
          </div>
        )}
      </div>

      {/* Account Selector & Date Range Filter Bar (Hidden in Print) */}
      <div className="bg-white border border-[#E3E9E2] rounded-2xl p-5 shadow-xs space-y-4 print:hidden">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
          {/* Account Selector */}
          <div>
            <label className="block text-xs font-semibold text-[#1D2B27] mb-1.5">
              Select Customer Account
            </label>
            {loadingAccounts ? (
              <div className="h-9 bg-[#F1F4EF] animate-pulse rounded-xl" />
            ) : accounts.length === 0 ? (
              <div className="text-xs text-rose-600 p-2 bg-rose-50 border border-rose-200 rounded-xl">
                No customer accounts found.
              </div>
            ) : (
              <select
                value={selectedAccountId}
                onChange={(e) => setSelectedAccountId(e.target.value)}
                className="w-full text-xs font-mono bg-white border border-[#E3E9E2] rounded-xl px-3 py-2 text-[#1D2B27] focus:ring-2 focus:ring-[#245344] focus:outline-hidden"
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
            <label className="block text-xs font-semibold text-[#1D2B27] mb-1.5">
              Statement Interval [Inclusive Start, Exclusive End)
            </label>
            <div className="flex flex-wrap items-center gap-1.5">
              {(['7d', '30d', 'month', 'all', 'custom'] as DatePreset[]).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => applyPreset(p)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-xl transition cursor-pointer ${
                    preset === p
                      ? 'bg-[#245344] text-white shadow-xs'
                      : 'bg-[#F1F4EF] text-[#6D7C73] hover:bg-[#E3E9E2]'
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
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3 border-t border-[#E3E9E2] items-end">
          <div>
            <label className="block text-[11px] font-medium text-[#6D7C73] mb-1">
              Start Date & Time (UTC)
            </label>
            <input
              type="datetime-local"
              value={startDateStr}
              onChange={(e) => {
                setStartDateStr(e.target.value);
                setPreset('custom');
              }}
              className="w-full text-xs font-mono bg-[#F1F4EF] border border-[#E3E9E2] rounded-xl px-3 py-2 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-[#245344] text-[#1D2B27]"
            />
          </div>

          <div>
            <label className="block text-[11px] font-medium text-[#6D7C73] mb-1">
              End Date & Time (UTC)
            </label>
            <input
              type="datetime-local"
              value={endDateStr}
              onChange={(e) => {
                setEndDateStr(e.target.value);
                setPreset('custom');
              }}
              className="w-full text-xs font-mono bg-[#F1F4EF] border border-[#E3E9E2] rounded-xl px-3 py-2 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-[#245344] text-[#1D2B27]"
            />
          </div>

          <div>
            <button
              onClick={() => fetchStatement(1)}
              disabled={loadingStatement || !selectedAccountId}
              className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-2.5 bg-[#245344] text-white text-xs font-semibold rounded-xl hover:bg-[#1B3F34] transition disabled:opacity-50 shadow-xs cursor-pointer"
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
          <div className="hidden print:block border-b-2 border-slate-900 pb-3 mb-4">
            <div className="flex justify-between items-start">
              <div>
                <h1 className="text-xl font-bold tracking-tight text-slate-900 font-mono">
                  LEDGERLINE ACCOUNT STATEMENT
                </h1>
                <p className="text-xs text-slate-600">
                  Conserved Double-Entry Financial Core
                </p>
              </div>
              <div className="text-right text-xs font-mono text-slate-700 space-y-0.5">
                <div><span className="font-semibold text-slate-900">Account:</span> {statement.account.account_number} ({statement.account.name})</div>
                <div><span className="font-semibold text-slate-900">Type:</span> {statement.account.account_type === 'customer_checking' ? 'Customer Checking' : 'Customer Savings'} &bull; Currency: {statement.account.currency}</div>
                <div><span className="font-semibold text-slate-900">Generated:</span> {new Date().toISOString().replace('T', ' ').slice(0, 19)} UTC</div>
              </div>
            </div>
            <div className="mt-2 text-xs font-mono text-slate-700 bg-slate-50 p-2 rounded border border-slate-200">
              <span className="font-semibold text-slate-900">Statement Period (UTC):</span> [{new Date(statement.period.start_date).toUTCString()} to {new Date(statement.period.end_date).toUTCString()})
            </div>
          </div>

          {/* 5-Card Executive Financial Summary */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 print:grid-cols-5 print:gap-2">
            {/* Opening Balance */}
            <div className="bg-white border border-[#E3E9E2] rounded-2xl p-4 print:p-2.5 shadow-xs">
              <span className="text-[11px] print:text-[9px] font-semibold text-[#6D7C73] uppercase tracking-wider block mb-1">
                Opening Balance
              </span>
              <div className="text-xl print:text-sm font-bold font-mono text-[#1D2B27]">
                ₹{Number(statement.summary.opening_balance).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
              <span className="text-[10px] print:text-[8px] text-[#6D7C73] mt-1 block">
                Balance before period start
              </span>
            </div>

            {/* Total Credits */}
            <div className="bg-white border border-[#C5D9C9] rounded-2xl p-4 print:p-2.5 shadow-xs bg-[#DCE9DF]/30">
              <span className="text-[11px] print:text-[9px] font-semibold text-[#245344] uppercase tracking-wider block mb-1">
                Total Money In
              </span>
              <div className="text-xl print:text-sm font-bold font-mono text-[#245344]">
                +₹{Number(statement.summary.total_credits).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
              <span className="text-[10px] print:text-[8px] text-[#245344]/80 mt-1 block">
                Deposits and incoming transfers
              </span>
            </div>

            {/* Total Debits */}
            <div className="bg-white border border-[#E8D5C4] rounded-2xl p-4 print:p-2.5 shadow-xs bg-[#F5E9DF]/30">
              <span className="text-[11px] print:text-[9px] font-semibold text-[#9B5540] uppercase tracking-wider block mb-1">
                Total Money Out
              </span>
              <div className="text-xl print:text-sm font-bold font-mono text-[#9B5540]">
                -₹{Number(statement.summary.total_debits).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
              <span className="text-[10px] print:text-[8px] text-[#9B5540]/80 mt-1 block">
                Withdrawals and outgoing transfers
              </span>
            </div>

            {/* Net Change */}
            <div className="bg-white border border-[#E3E9E2] rounded-2xl p-4 print:p-2.5 shadow-xs">
              <span className="text-[11px] print:text-[9px] font-semibold text-[#6D7C73] uppercase tracking-wider block mb-1">
                Net Change
              </span>
              <div className={`text-xl print:text-sm font-bold font-mono ${
                Number(statement.summary.net_change) >= 0 ? 'text-[#245344]' : 'text-[#9B5540]'
              }`}>
                {Number(statement.summary.net_change) >= 0 ? '+' : ''}
                ₹{Number(statement.summary.net_change).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
              <span className="text-[10px] print:text-[8px] text-[#6D7C73] mt-1 block">
                Money In minus Money Out
              </span>
            </div>

            {/* Closing Balance */}
            <div className="bg-[#245344] border border-[#1B3F34] text-white rounded-2xl p-4 print:p-2.5 shadow-xs col-span-2 sm:col-span-1 print:col-span-1">
              <span className="text-[11px] print:text-[9px] font-semibold text-[#DCE9DF] uppercase tracking-wider block mb-1">
                Closing Balance
              </span>
              <div className="text-xl print:text-sm font-bold font-mono text-white">
                ₹{Number(statement.summary.closing_balance).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
              <span className="text-[10px] print:text-[8px] text-[#DCE9DF]/80 mt-1 block">
                Opening + Net Change
              </span>
            </div>
          </div>

          {/* Activity Tabs Header (Hidden in Print) */}
          <div className="flex items-center gap-2 border-b border-[#E3E9E2] print:hidden">
            <button
              onClick={() => setActiveTab('posted')}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold border-b-2 transition -mb-px cursor-pointer ${
                activeTab === 'posted'
                  ? 'border-[#245344] text-[#245344]'
                  : 'border-transparent text-[#6D7C73] hover:text-[#1D2B27]'
              }`}
            >
              <CheckCircle2 className="w-3.5 h-3.5 text-[#245344]" />
              <span>Completed Transactions</span>
              <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] bg-[#DCE9DF] text-[#245344] border border-[#C5D9C9]">
                {statement.summary.total_posted_transactions}
              </span>
            </button>

            <button
              onClick={() => setActiveTab('refused')}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold border-b-2 transition -mb-px cursor-pointer ${
                activeTab === 'refused'
                  ? 'border-[#245344] text-[#245344]'
                  : 'border-transparent text-[#6D7C73] hover:text-[#1D2B27]'
              }`}
            >
              <ShieldAlert className="w-3.5 h-3.5 text-[#9B5540]" />
              <span>Declined Attempts</span>
              <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] bg-[#F5E9DF] text-[#9B5540] border border-[#E8D5C4]">
                {statement.summary.total_refused_attempts}
              </span>
            </button>
          </div>

          {/* Tab 1: Posted Transactions Table */}
          {activeTab === 'posted' && (
            <div className="bg-white border border-[#E3E9E2] rounded-2xl overflow-hidden shadow-xs">
              {statement.transactions.length === 0 ? (
                <div className="py-12 text-center space-y-2">
                  <div className="w-10 h-10 rounded-full bg-[#F1F4EF] flex items-center justify-center mx-auto text-[#6D7C73]">
                    <Calendar className="w-5 h-5 text-[#245344]" />
                  </div>
                  <p className="text-xs text-[#6D7C73]">
                    No completed transactions found in the requested period.
                  </p>
                  <p className="text-[11px] text-[#6D7C73] font-mono">
                    Opening and closing balance remain identical: ₹{Number(statement.summary.opening_balance).toFixed(2)}
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto print:overflow-visible">
                  <table className="w-full text-left border-collapse text-xs print:text-[10px] print-table">
                    <thead>
                      <tr className="border-b border-[#E3E9E2] bg-[#F1F4EF] print:bg-slate-100 text-[#6D7C73] font-semibold text-[11px] print:text-[10px]">
                        <th className="px-4 py-2.5 print:px-2 print:py-1.5 whitespace-nowrap">Date &amp; Time (UTC)</th>
                        <th className="px-4 py-2.5 print:px-2 print:py-1.5 whitespace-nowrap">Reference</th>
                        <th className="px-4 py-2.5 print:px-2 print:py-1.5 whitespace-nowrap">Type</th>
                        <th className="px-4 py-2.5 print:px-2 print:py-1.5">Counterparty</th>
                        <th className="px-4 py-2.5 print:px-2 print:py-1.5">Description</th>
                        <th className="px-4 py-2.5 print:px-2 print:py-1.5 text-right whitespace-nowrap">Amount (INR)</th>
                        <th className="px-4 py-2.5 print:px-2 print:py-1.5 text-right whitespace-nowrap">Running Balance</th>
                        <th className="px-4 py-2.5 print:px-2 print:py-1.5 text-center whitespace-nowrap print:hidden">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E3E9E2]">
                      {statement.transactions.map((tx) => {
                        const isCredit = tx.direction === 'credit';
                        return (
                          <tr key={tx.entry_id} className="hover:bg-[#F1F4EF]/50 transition">
                            <td className="px-4 py-3 print:px-2 print:py-1.5 font-mono text-[11px] print:text-[9px] text-[#6D7C73] whitespace-nowrap">
                              {new Date(tx.posted_at).toISOString().replace('T', ' ').slice(0, 19)}
                            </td>
                            <td className="px-4 py-3 print:px-2 print:py-1.5 font-mono text-xs print:text-[10px] text-[#1D2B27] whitespace-nowrap">
                              <span className="flex items-center gap-1.5">
                                <span>{tx.reference}</span>
                                <button
                                  onClick={() => handleCopy(tx.reference)}
                                  className="text-[#6D7C73] hover:text-[#1D2B27] p-0.5 rounded transition print:hidden cursor-pointer"
                                  title="Copy reference"
                                >
                                  {copiedRef === tx.reference ? (
                                    <Check className="w-3 h-3 text-[#245344]" />
                                  ) : (
                                    <Copy className="w-3 h-3" />
                                  )}
                                </button>
                              </span>
                            </td>
                            <td className="px-4 py-3 print:px-2 print:py-1.5 whitespace-nowrap">
                              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] print:text-[9px] font-semibold border ${
                                isCredit
                                  ? 'bg-[#DCE9DF] text-[#245344] border-[#C5D9C9]'
                                  : 'bg-[#F5E9DF] text-[#9B5540] border-[#E8D5C4]'
                              }`}>
                                {isCredit ? <ArrowDownLeft className="w-3 h-3 print:hidden" /> : <ArrowUpRight className="w-3 h-3 print:hidden" />}
                                <span>{tx.display_label}</span>
                              </span>
                            </td>
                            <td className="px-4 py-3 print:px-2 print:py-1.5 font-mono text-[11px] print:text-[9px] text-[#6D7C73]">
                              {tx.counterparty_account_number || 'External Clearing (ACC-SYSTEM02)'}
                            </td>
                            <td className="px-4 py-3 print:px-2 print:py-1.5 text-[#1D2B27] print:text-black max-w-xs print:max-w-none whitespace-normal break-words" title={tx.description}>
                              {tx.description}
                            </td>
                            <td className={`px-4 py-3 print:px-2 print:py-1.5 text-right font-mono font-semibold whitespace-nowrap ${
                              isCredit ? 'text-[#245344]' : 'text-[#9B5540]'
                            }`}>
                              {isCredit ? '+' : '-'}₹{Number(tx.amount).toFixed(2)}
                            </td>
                            <td className="px-4 py-3 print:px-2 print:py-1.5 text-right font-mono font-bold text-[#1D2B27] whitespace-nowrap">
                              ₹{Number(tx.running_balance).toFixed(2)}
                            </td>
                            <td className="px-4 py-3 print:px-2 print:py-1.5 text-center whitespace-nowrap print:hidden">
                              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[#DCE9DF] text-[#245344] border border-[#C5D9C9]">
                                Completed
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
                <div className="flex items-center justify-between px-4 py-3 border-t border-[#E3E9E2] bg-[#F1F4EF] print:hidden text-xs text-[#6D7C73]">
                  <div>
                    Page {statement.page} of {statement.total_pages} ({statement.summary.total_posted_transactions} total completed entries)
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => fetchStatement(statement.page - 1)}
                      disabled={statement.page <= 1 || loadingStatement}
                      className="p-1.5 rounded-lg border border-[#E3E9E2] bg-white text-[#1D2B27] hover:bg-[#F1F4EF] disabled:opacity-40 transition cursor-pointer"
                      title="Previous Page"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => fetchStatement(statement.page + 1)}
                      disabled={statement.page >= statement.total_pages || loadingStatement}
                      className="p-1.5 rounded-lg border border-[#E3E9E2] bg-white text-[#1D2B27] hover:bg-[#F1F4EF] disabled:opacity-40 transition cursor-pointer"
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
              <div className="p-3 bg-[#F5E9DF] border border-[#E8D5C4] rounded-xl text-[#9B5540] text-xs flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-[#9B5540] shrink-0 mt-0.5" />
                <div>
                  <span className="font-semibold text-[#1D2B27]">Financial Integrity Invariant: </span>
                  Declined attempts represent unsuccessful operations. In compliance with LedgerLine banking standards,
                  declined operations never alter account balances and never create transaction records.
                </div>
              </div>

              <div className="bg-white border border-[#E3E9E2] rounded-2xl overflow-hidden shadow-xs">
                {statement.refused_attempts.length === 0 ? (
                  <div className="py-12 text-center space-y-2">
                    <div className="w-10 h-10 rounded-full bg-[#DCE9DF] flex items-center justify-center mx-auto text-[#245344]">
                      <CheckCircle2 className="w-5 h-5" />
                    </div>
                    <p className="text-xs text-[#1D2B27] font-medium">
                      Zero declined financial attempts recorded for this account in the requested period.
                    </p>
                    <p className="text-[11px] text-[#6D7C73]">
                      All attempted operations completed cleanly.
                    </p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="border-b border-[#E3E9E2] bg-[#F1F4EF] text-[#6D7C73] font-semibold text-[11px]">
                          <th className="px-4 py-2.5">Attempted At (UTC)</th>
                          <th className="px-4 py-2.5">Type</th>
                          <th className="px-4 py-2.5">Role</th>
                          <th className="px-4 py-2.5">Counterparty</th>
                          <th className="px-4 py-2.5">Requested Amount</th>
                          <th className="px-4 py-2.5">Decline Reason</th>
                          <th className="px-4 py-2.5">Details</th>
                          <th className="px-4 py-2.5 text-center">Outcome</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#E3E9E2]">
                        {statement.refused_attempts.map((ref) => (
                          <tr key={ref.id} className="hover:bg-[#F1F4EF]/50 transition">
                            <td className="px-4 py-3 font-mono text-[11px] text-[#6D7C73] whitespace-nowrap">
                              {new Date(ref.created_at).toISOString().replace('T', ' ').slice(0, 19)}
                            </td>
                            <td className="px-4 py-3 font-semibold uppercase text-[11px] text-[#1D2B27] whitespace-nowrap">
                              {ref.operation_type}
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                                ref.is_source ? 'bg-[#F1F4EF] text-[#1D2B27] border border-[#E3E9E2]' : 'bg-[#E9E2EF] text-[#553C7B] border border-[#D5C7DE]'
                              }`}>
                                {ref.is_source ? 'Initiator / Source' : 'Intended Destination'}
                              </span>
                            </td>
                            <td className="px-4 py-3 font-mono text-[11px] text-[#6D7C73] whitespace-nowrap">
                              {ref.counterparty_account_number || '—'}
                            </td>
                            <td className="px-4 py-3 font-mono text-[#1D2B27] whitespace-nowrap">
                              {ref.amount ? `₹${Number(ref.amount).toFixed(2)}` : '—'}
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#F5E9DF] text-[#9B5540] border border-[#E8D5C4]">
                                {ref.refusal_reason}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-[#6D7C73] max-w-sm truncate" title={ref.error_message}>
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
