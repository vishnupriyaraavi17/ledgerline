import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  RefreshCw,
  Search,
  Filter,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  KeyRound,
  FileText,
  Activity,
} from 'lucide-react';

import { useAuth } from '../context/AuthContext';
import { apiService } from '../services/api';
import type { AuditEvent, VerificationResult, AuditHead } from '../types/audit';

export const AuditTrailPage: React.FC = () => {
  const { user } = useAuth();

  // State
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [totalEvents, setTotalEvents] = useState<number>(0);
  const [head, setHead] = useState<AuditHead | null>(null);
  const [verification, setVerification] = useState<VerificationResult | null>(null);
  const [verifying, setVerifying] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  // Filters & Pagination
  const [selectedEventType, setSelectedEventType] = useState<string>('');
  const [entityTypeFilter, setEntityTypeFilter] = useState<string>('');
  const [page, setPage] = useState<number>(0);
  const pageSize = 20;

  const isAuthorized = user?.role === 'admin' || user?.role === 'auditor';

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(id);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  const loadData = useCallback(async () => {
    if (!isAuthorized) return;
    setLoading(true);
    setError(null);
    try {
      const [eventsRes, headRes] = await Promise.all([
        apiService.getAuditEvents({
          event_type: selectedEventType || undefined,
          entity_type: entityTypeFilter || undefined,
          limit: pageSize,
          offset: page * pageSize,
        }),
        apiService.getAuditHead(),
      ]);
      setEvents(eventsRes.items);
      setTotalEvents(eventsRes.total);
      setHead(headRes);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load audit trail data';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [isAuthorized, selectedEventType, entityTypeFilter, page]);

  const handleVerify = async () => {
    setVerifying(true);
    setError(null);
    try {
      const result = await apiService.verifyAuditChain();
      setVerification(result);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Cryptographic chain verification failed';
      setError(message);
    } finally {
      setVerifying(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (!isAuthorized) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 text-center">
          <ShieldAlert className="w-12 h-12 text-amber-600 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Access Restricted</h2>
          <p className="text-sm text-gray-600">
            The Cryptographically Verifiable Audit Trail is strictly reserved for Administrator and Auditor roles.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">Cryptographic Audit Trail</h1>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
              Task 06
            </span>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Indisputable, append-only SHA-256 linear hash chain verifying financial movements and security events.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => loadData()}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={handleVerify}
            disabled={verifying}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-slate-900 rounded-lg hover:bg-slate-800 disabled:opacity-50 transition-colors shadow-sm"
          >
            <ShieldCheck className={`w-4 h-4 ${verifying ? 'animate-spin' : ''}`} />
            {verifying ? 'Verifying Chain...' : 'Verify Cryptographic Chain'}
          </button>
        </div>
      </div>

      {/* Global Error Banner */}
      {error && (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-center gap-3 text-rose-800 text-sm">
          <AlertTriangle className="w-5 h-5 shrink-0 text-rose-600" />
          <span>{error}</span>
        </div>
      )}

      {/* Verification Status Banner */}
      {verification && (
        <div
          className={`border rounded-xl p-5 ${
            verification.is_valid
              ? 'bg-emerald-50/80 border-emerald-200 text-emerald-900'
              : 'bg-rose-50 border-rose-300 text-rose-900'
          }`}
        >
          <div className="flex items-start gap-4">
            {verification.is_valid ? (
              <CheckCircle2 className="w-6 h-6 text-emerald-600 shrink-0 mt-0.5" />
            ) : (
              <ShieldAlert className="w-6 h-6 text-rose-600 shrink-0 mt-0.5" />
            )}
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold">
                  {verification.is_valid
                    ? 'Cryptographic Chain Verified Intact'
                    : 'Tampering Detected in Cryptographic Audit Chain!'}
                </h3>
                <span className="text-xs font-mono opacity-75">
                  Verified at: {new Date(verification.verified_at).toLocaleTimeString()}
                </span>
              </div>
              <p className="text-sm mt-1">
                {verification.is_valid
                  ? `All ${verification.total_events} events sequentially verified from genesis. Every parent hash pointer and SHA-256 payload digest matches.`
                  : `Chain verification failed at sequence #${verification.tamper_details?.sequence_number}: ${verification.tamper_details?.message}`}
              </p>

              {verification.tamper_details && (
                <div className="mt-3 bg-white/80 rounded-lg p-3 text-xs font-mono space-y-1 border border-rose-200">
                  <div>
                    <span className="font-semibold text-gray-700">Failure Type:</span>{' '}
                    <span className="text-rose-700 font-bold">{verification.tamper_details.failure_type}</span>
                  </div>
                  <div>
                    <span className="font-semibold text-gray-700">Sequence:</span> #{verification.tamper_details.sequence_number}
                  </div>
                  {verification.tamper_details.event_id && (
                    <div>
                      <span className="font-semibold text-gray-700">Event ID:</span> {verification.tamper_details.event_id}
                    </div>
                  )}
                  <div className="truncate">
                    <span className="font-semibold text-gray-700">Expected:</span> {verification.tamper_details.expected_value}
                  </div>
                  <div className="truncate">
                    <span className="font-semibold text-gray-700">Found:</span> {verification.tamper_details.actual_value}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Total Audit Records</span>
            <FileText className="w-5 h-5 text-gray-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-gray-900">{totalEvents.toLocaleString()}</div>
          <p className="text-xs text-gray-500 mt-1">Append-only events recorded</p>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Latest Sequence</span>
            <Activity className="w-5 h-5 text-gray-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-gray-900">
            {head ? `#${head.sequence_number}` : '—'}
          </div>
          <p className="text-xs text-gray-500 mt-1">Monotonic sequential index</p>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Chain Head Hash</span>
            <KeyRound className="w-5 h-5 text-gray-400" />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="font-mono text-sm font-bold text-gray-800 truncate">
              {head ? `${head.current_hash.slice(0, 16)}...` : '—'}
            </span>
            {head && (
              <button
                onClick={() => copyToClipboard(head.current_hash, 'head')}
                className="p-1 text-gray-400 hover:text-gray-600 rounded transition-colors"
                title="Copy full 64-char hash"
              >
                {copiedHash === 'head' ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
              </button>
            )}
          </div>
          <p className="text-xs text-gray-500 mt-1">SHA-256 state digest</p>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm flex flex-wrap gap-4 items-center justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-400" />
            <span className="text-xs font-semibold text-gray-600 uppercase">Filters:</span>
          </div>

          <select
            value={selectedEventType}
            onChange={(e) => {
              setSelectedEventType(e.target.value);
              setPage(0);
            }}
            className="text-xs border border-gray-300 rounded-lg px-2.5 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-slate-900"
          >
            <option value="">All Event Types</option>
            <option value="financial.deposit">financial.deposit</option>
            <option value="financial.withdraw">financial.withdraw</option>
            <option value="financial.transfer">financial.transfer</option>
            <option value="account.created">account.created</option>
            <option value="account.status_updated">account.status_updated</option>
            <option value="security.user_registered">security.user_registered</option>
            <option value="security.login_success">security.login_success</option>
            <option value="security.login_failure">security.login_failure</option>
          </select>

          <select
            value={entityTypeFilter}
            onChange={(e) => {
              setEntityTypeFilter(e.target.value);
              setPage(0);
            }}
            className="text-xs border border-gray-300 rounded-lg px-2.5 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-slate-900"
          >
            <option value="">All Entities</option>
            <option value="transaction">transaction</option>
            <option value="account">account</option>
            <option value="user">user</option>
            <option value="auth">auth</option>
          </select>
        </div>

        <div className="text-xs text-gray-500">
          Showing {events.length} of {totalEvents} events
        </div>
      </div>

      {/* Audit Event Table */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-16">
                  Seq
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Timestamp (UTC)
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Event Type
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actor
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Entity
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Hash / Prev Hash
                </th>
                <th scope="col" className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider w-12">
                  Payload
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200 text-sm">
              {loading && events.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-gray-500">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto text-gray-400 mb-2" />
                    Loading cryptographic audit records...
                  </td>
                </tr>
              ) : events.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-gray-500">
                    <Search className="w-6 h-6 mx-auto text-gray-400 mb-2" />
                    No audit events match the selected criteria.
                  </td>
                </tr>
              ) : (
                events.map((evt) => {
                  const isExpanded = expandedRow === evt.id;
                  const isFinancial = evt.event_type.startsWith('financial.');
                  const isSecurity = evt.event_type.startsWith('security.');

                  return (
                    <React.Fragment key={evt.id}>
                      <tr className="hover:bg-gray-50 transition-colors">
                        <td className="px-4 py-3 font-mono font-bold text-gray-900 text-xs">
                          #{evt.sequence_number}
                        </td>
                        <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                          {new Date(evt.created_at).toISOString().replace('T', ' ').slice(0, 23)}Z
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                              isFinancial
                                ? 'bg-blue-50 text-blue-700 border border-blue-200'
                                : isSecurity
                                ? evt.event_type.includes('failure')
                                  ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                  : 'bg-purple-50 text-purple-700 border border-purple-200'
                                : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            }`}
                          >
                            {evt.event_type}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-gray-700">
                          {evt.actor_role ? (
                            <span className="font-medium text-gray-900">
                              {evt.actor_role}
                            </span>
                          ) : (
                            <span className="text-gray-400 italic">system / unauth</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs font-mono text-gray-600">
                          <span className="text-gray-400">{evt.entity_type}:</span> {evt.entity_id}
                        </td>
                        <td className="px-4 py-3 text-xs font-mono space-y-0.5">
                          <div className="flex items-center gap-1">
                            <span className="text-gray-400 text-[10px]">curr:</span>
                            <span className="text-gray-900 font-semibold">{evt.current_hash.slice(0, 10)}...</span>
                            <button
                              onClick={() => copyToClipboard(evt.current_hash, `curr-${evt.id}`)}
                              className="text-gray-400 hover:text-gray-600"
                            >
                              {copiedHash === `curr-${evt.id}` ? (
                                <Check className="w-3 h-3 text-emerald-600" />
                              ) : (
                                <Copy className="w-3 h-3" />
                              )}
                            </button>
                          </div>
                          <div className="flex items-center gap-1">
                            <span className="text-gray-400 text-[10px]">prev:</span>
                            <span className="text-gray-500">{evt.prev_hash.slice(0, 10)}...</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-center">
                          <button
                            onClick={() => setExpandedRow(isExpanded ? null : evt.id)}
                            className="p-1 text-gray-500 hover:text-gray-700 rounded transition-colors"
                            title="Toggle payload"
                          >
                            {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                          </button>
                        </td>
                      </tr>

                      {/* Expanded Canonical Payload View */}
                      {isExpanded && (
                        <tr className="bg-slate-50/70">
                          <td colSpan={7} className="px-6 py-4 border-t border-b border-gray-200">
                            <div className="space-y-3">
                              <div className="flex items-center justify-between text-xs text-gray-500">
                                <span className="font-semibold text-gray-700">Event ID: {evt.id}</span>
                                <span>Full Hash: <code className="font-mono">{evt.current_hash}</code></span>
                              </div>
                              <div>
                                <span className="text-xs font-semibold text-gray-700 block mb-1">
                                  Canonical JSON Payload:
                                </span>
                                <pre className="bg-slate-900 text-slate-100 p-3 rounded-lg text-xs font-mono overflow-x-auto">
                                  {JSON.stringify(evt.payload, null, 2)}
                                </pre>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        {totalEvents > pageSize && (
          <div className="bg-gray-50 px-4 py-3 flex items-center justify-between border-t border-gray-200 sm:px-6">
            <div className="text-xs text-gray-600">
              Page {page + 1} of {Math.ceil(totalEvents / pageSize)}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(p - 1, 0))}
                disabled={page === 0}
                className="px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={(page + 1) * pageSize >= totalEvents}
                className="px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
