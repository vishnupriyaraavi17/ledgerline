import { useState, useEffect, useCallback } from 'react';
import type { HealthResponse } from '../types/health';
import { apiService } from '../services/api';

export function useHealth(pollIntervalMs: number = 10000) {
  const [data, setData] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await apiService.getHealth();
      setData(res);
      setLastChecked(new Date());
    } catch (err: any) {
      const errorMsg =
        err.response?.data?.database?.details ||
        err.response?.data?.detail ||
        err.message ||
        'Unable to connect to backend service';
      setError(errorMsg);
      // If backend returned a structured degraded response
      if (err.response?.data?.database) {
        setData(err.response.data as HealthResponse);
      } else {
        setData(null);
      }
      setLastChecked(new Date());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    if (pollIntervalMs > 0) {
      const timer = setInterval(fetchHealth, pollIntervalMs);
      return () => clearInterval(timer);
    }
  }, [fetchHealth, pollIntervalMs]);

  return { data, loading, error, lastChecked, refetch: fetchHealth };
}
