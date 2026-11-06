import React from 'react';
import { CheckCircle2, AlertTriangle, XCircle, RefreshCw } from 'lucide-react';

interface HealthBadgeProps {
  status?: 'healthy' | 'degraded' | 'connected' | 'disconnected';
  loading?: boolean;
  label?: string;
}

export const HealthBadge: React.FC<HealthBadgeProps> = ({ status, loading, label }) => {
  if (loading) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
        <RefreshCw className="w-3 h-3 animate-spin text-slate-500" />
        {label || 'Checking...'}
      </span>
    );
  }

  if (status === 'healthy' || status === 'connected') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
        {label || 'Operational'}
      </span>
    );
  }

  if (status === 'degraded' || status === 'disconnected') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200">
        <XCircle className="w-3.5 h-3.5 text-rose-600" />
        {label || 'Offline'}
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
      <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
      {label || 'Unknown'}
    </span>
  );
};
