import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import type { User, LoginCredentials } from '../types/auth';
import { apiService, setAuthToken } from '../services/api';

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  error: string | null;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Restore authenticated session on initial mount / page refresh
  useEffect(() => {
    let isMounted = true;

    const restoreSession = async () => {
      try {
        const response = await apiService.refreshToken();
        if (isMounted && response?.access_token && response?.user) {
          setToken(response.access_token);
          setUser(response.user);
          setAuthToken(response.access_token);
        }
      } catch {
        // No active refresh cookie or expired session - user is unauthenticated
        if (isMounted) {
          setToken(null);
          setUser(null);
          setAuthToken(null);
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    restoreSession();

    return () => {
      isMounted = false;
    };
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const login = useCallback(async (credentials: LoginCredentials) => {
    setError(null);
    try {
      const response = await apiService.login(credentials);
      setToken(response.access_token);
      setUser(response.user);
      setAuthToken(response.access_token);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : 'Authentication failed. Please verify credentials.';
      setError(message);
      throw new Error(message);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiService.logout();
    } catch {
      // Best-effort server logout; always clear local in-memory state
    } finally {
      setUser(null);
      setToken(null);
      setAuthToken(null);
      setError(null);
    }
  }, []);

  const value: AuthContextType = {
    user,
    token,
    isAuthenticated: !!user && !!token,
    isLoading,
    login,
    logout,
    error,
    clearError,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
