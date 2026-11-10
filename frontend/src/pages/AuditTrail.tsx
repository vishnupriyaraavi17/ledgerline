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
    <div className="space-y-6 font-sans">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 pb-2 border-b border-[#E3E9E2]">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-serif font-bold text-[#1D2B27]">Audit Trail</h1>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[#DCE9DF] text-[#245344] border border-[#C5D9C9]">
              Immutable
            </span>
          </div>
          <p className="text-xs text-[#6D7C73] mt-1">
            A tamper-evident, verified record of financial movements and security events.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => loadData()}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold text-[#1D2B27] bg-white border border-[#E3E9E2] rounded-xl hover:bg-[#F1F4EF] disabled:opacity-50 transition cursor-pointer shadow-2xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-[#245344]' : ''}`} />
            <span>Refresh</span>
          </button>
          <button
            onClick={handleVerify}
            disabled={verifying}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-[#245344] hover:bg-[#1B3F34] rounded-xl disabled:opacity-50 transition shadow-xs cursor-pointer"
          >
            <ShieldCheck className={`w-4 h-4 text-[#DCE9DF] ${verifying ? 'animate-spin' : ''}`} />
            <span>{verifying ? 'Verifying Integrity...' : 'Verify Audit Integrity'}</span>
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
          className={`border rounded-2xl p-5 ${
            verification.is_valid
              ? 'bg-[#DCE9DF]/40 border-[#C5D9C9] text-[#245344]'
              : 'bg-rose-50 border-rose-300 text-rose-900'
          }`}
        >
          <div className="flex items-start gap-4">
            {verification.is_valid ? (
              <CheckCircle2 className="w-6 h-6 text-[#245344] shrink-0 mt-0.5" />
            ) : (
              <ShieldAlert className="w-6 h-6 text-rose-600 shrink-0 mt-0.5" />
            )}
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold text-[#1D2B27]">
                  {verification.is_valid
                    ? 'Cryptographic Chain Verified Intact'
                    : 'Tampering Detected in Cryptographic Audit Chain!'}
                </h3>
                <span className="text-xs font-mono opacity-75">
                  Verified at: {new Date(verification.verified_at).toLocaleTimeString()}
                </span>
              </div>
              <p className="text-sm mt-1 text-[#1D2B27]">
                {verification.is_valid
                  ? `All ${verification.total_events} events sequentially verified from genesis. Every parent hash pointer and SHA-256 payload digest matches.`
                  : `Chain verification failed at sequence #${verification.tamper_details?.sequence_number}: ${verification.tamper_details?.message}`}
              </p>

              {verification.tamper_details && (
                <div className="mt-3 bg-white/80 rounded-xl p-3 text-xs font-mono space-y-1 border border-rose-200">
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
        <div className="bg-white border border-[#E3E9E2] rounded-2xl p-5 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[#6D7C73] uppercase tracking-wider">Total Audit Records</span>
            <FileText className="w-5 h-5 text-[#245344]" />
          </div>
          <div className="mt-2 text-2xl font-serif font-bold text-[#1D2B27]">{totalEvents.toLocaleString()}</div>
          <p className="text-xs text-[#6D7C73] mt-1">Append-only events recorded</p>
        </div>

        <div className="bg-white border border-[#E3E9E2] rounded-2xl p-5 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[#6D7C73] uppercase tracking-wider">Latest Sequence</span>
            <Activity className="w-5 h-5 text-[#245344]" />
          </div>
          <div className="mt-2 text-2xl font-serif font-bold text-[#1D2B27]">
            {head ? `#${head.sequence_number}` : '—'}
          </div>
          <p className="text-xs text-[#6D7C73] mt-1">Monotonic sequential index</p>
        </div>

        <div className="bg-white border border-[#E3E9E2] rounded-2xl p-5 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[#6D7C73] uppercase tracking-wider">Chain Head Hash</span>
            <KeyRound className="w-5 h-5 text-[#245344]" />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="font-mono text-sm font-bold text-[#1D2B27] truncate">
              {head ? `${head.current_hash.slice(0, 16)}...` : '—'}
            </span>
            {head && (
              <button
                onClick={() => copyToClipboard(head.current_hash, 'head')}
                className="p-1 text-[#6D7C73] hover:text-[#1D2B27] rounded transition cursor-pointer"
                title="Copy full 64-char hash"
              >
                {copiedHash === 'head' ? <Check className="w-4 h-4 text-[#245344]" /> : <Copy className="w-4 h-4" />}
              </button>
            )}
          </div>
          <p className="text-xs text-[#6D7C73] mt-1">SHA-256 state digest</p>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="bg-white border border-[#E3E9E2] rounded-2xl p-4 shadow-xs flex flex-wrap gap-4 items-center justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-[#6D7C73]" />
            <span className="text-xs font-semibold text-[#1D2B27] uppercase">Filters:</span>
          </div>

          <select
            value={selectedEventType}
            onChange={(e) => {
              setSelectedEventType(e.target.value);
              setPage(0);
            }}
            className="text-xs border border-[#E3E9E2] rounded-xl px-3 py-1.5 bg-[#F1F4EF] text-[#1D2B27] focus:outline-none focus:ring-2 focus:ring-[#245344]"
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
            className="text-xs border border-[#E3E9E2] rounded-xl px-3 py-1.5 bg-[#F1F4EF] text-[#1D2B27] focus:outline-none focus:ring-2 focus:ring-[#245344]"
          >
            <option value="">All Entities</option>
            <option value="transaction">transaction</option>
            <option value="account">account</option>
            <option value="user">user</option>
            <option value="auth">auth</option>
          </select>
        </div>

        <div className="text-xs text-[#6D7C73]">
          Showing {events.length} of {totalEvents} events
        </div>
      </div>

      {/* Audit Event Table */}
      <div className="bg-white border border-[#E3E9E2] rounded-2xl shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-[#E3E9E2]">
            <thead className="bg-[#F1F4EF]">
              <tr>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-[#6D7C73] uppercase tracking-wider w-16">
                  Seq
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-[#6D7C73] uppercase tracking-wider">
                  Timestamp (UTC)
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-[#6D7C73] uppercase tracking-wider">
                  Event Type
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-[#6D7C73] uppercase tracking-wider">
                  Actor
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-[#6D7C73] uppercase tracking-wider">
                  Entity
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-[#6D7C73] uppercase tracking-wider">
                  Hash / Prev Hash
                </th>
                <th scope="col" className="px-4 py-3 text-center text-xs font-semibold text-[#6D7C73] uppercase tracking-wider w-12">
                  Payload
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-[#E3E9E2] text-sm">
              {loading && events.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-[#6D7C73]">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto text-[#245344] mb-2" />
                    Loading cryptographic audit records...
                  </td>
                </tr>
              ) : events.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-[#6D7C73]">
                    <Search className="w-6 h-6 mx-auto text-[#6D7C73] mb-2" />
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
                      <tr className="hover:bg-[#F1F4EF]/50 transition-colors">
                        <td className="px-4 py-3 font-mono font-bold text-[#1D2B27] text-xs">
                          #{evt.sequence_number}
                        </td>
                        <td className="px-4 py-3 text-[#6D7C73] text-xs whitespace-nowrap font-mono">
                          {new Date(evt.created_at).toISOString().replace('T', ' ').slice(0, 23)}Z
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${
                              isFinancial
                                ? 'bg-[#DCE9DF] text-[#245344] border-[#C5D9C9]'
                                : isSecurity
                                ? evt.event_type.includes('failure')
                                  ? 'bg-[#F5E9DF] text-[#9B5540] border-[#E8D5C4]'
                                  : 'bg-[#E9E2EF] text-[#553C7B] border-[#D5C7DE]'
                                : 'bg-[#F1F4EF] text-[#1D2B27] border-[#E3E9E2]'
                            }`}
                          >
                            {evt.event_type}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-[#1D2B27]">
                          {evt.actor_role ? (
                            <span className="font-medium text-[#1D2B27]">
                              {evt.actor_role}
                            </span>
                          ) : (
                            <span className="text-[#6D7C73] italic">system / unauth</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs font-mono text-[#6D7C73]">
                          <span className="text-[#6D7C73]">{evt.entity_type}:</span> {evt.entity_id}
                        </td>
                        <td className="px-4 py-3 text-xs font-mono space-y-0.5">
                          <div className="flex items-center gap-1">
                            <span className="text-[#6D7C73] text-[10px]">curr:</span>
                            <span className="text-[#1D2B27] font-semibold">{evt.current_hash.slice(0, 10)}...</span>
                            <button
                              onClick={() => copyToClipboard(evt.current_hash, `curr-${evt.id}`)}
                              className="text-[#6D7C73] hover:text-[#1D2B27] cursor-pointer"
                            >
                              {copiedHash === `curr-${evt.id}` ? (
                                <Check className="w-3 h-3 text-[#245344]" />
                              ) : (
                                <Copy className="w-3 h-3" />
                              )}
                            </button>
                          </div>
                          <div className="flex items-center gap-1">
                            <span className="text-[#6D7C73] text-[10px]">prev:</span>
                            <span className="text-[#6D7C73]">{evt.prev_hash.slice(0, 10)}...</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-center">
                          <button
                            onClick={() => setExpandedRow(isExpanded ? null : evt.id)}
                            className="p-1 text-[#6D7C73] hover:text-[#1D2B27] rounded transition cursor-pointer"
                            title="Toggle payload"
                          >
                            {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                          </button>
                        </td>
                      </tr>

                      {/* Expanded Canonical Payload View */}
                      {isExpanded && (
                        <tr className="bg-[#F1F4EF]/50">
                          <td colSpan={7} className="px-6 py-4 border-t border-b border-[#E3E9E2]">
                            <div className="space-y-3">
                              <div className="flex items-center justify-between text-xs text-[#6D7C73]">
                                <span className="font-semibold text-[#1D2B27]">Event ID: {evt.id}</span>
                                <span>Full Hash: <code className="font-mono text-[#1D2B27]">{evt.current_hash}</code></span>
                              </div>
                              <div>
                                <span className="text-xs font-semibold text-[#1D2B27] block mb-1">
                                  Canonical JSON Payload:
                                </span>
                                <pre className="bg-[#1D2B27] text-white p-3 rounded-xl text-xs font-mono overflow-x-auto border border-[#E3E9E2]">
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
          <div className="bg-[#F1F4EF] px-4 py-3 flex items-center justify-between border-t border-[#E3E9E2] sm:px-6">
            <div className="text-xs text-[#6D7C73]">
              Page {page + 1} of {Math.ceil(totalEvents / pageSize)}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(p - 1, 0))}
                disabled={page === 0}
                className="px-3.5 py-1.5 text-xs font-semibold text-[#1D2B27] bg-white border border-[#E3E9E2] rounded-xl hover:bg-[#F1F4EF] disabled:opacity-50 transition cursor-pointer"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={(page + 1) * pageSize >= totalEvents}
                className="px-3.5 py-1.5 text-xs font-semibold text-[#1D2B27] bg-white border border-[#E3E9E2] rounded-xl hover:bg-[#F1F4EF] disabled:opacity-50 transition cursor-pointer"
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
