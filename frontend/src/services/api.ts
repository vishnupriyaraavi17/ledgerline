import axios from 'axios';
import type { AxiosInstance } from 'axios';
import type { HealthResponse } from '../types/health';
import type { LoginCredentials, TokenResponse, User, UserCreateInput, UserListResponse } from '../types/auth';
import type {
  Account,
  AccountCreateInput,
  AccountListResponse,
  AccountStatus,
  LedgerEntryListResponse,
} from '../types/account';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1';

// Strictly in-memory access token storage (XSS resilient, never stored in localStorage)
let inMemoryAccessToken: string | null = null;

export const setAuthToken = (token: string | null) => {
  inMemoryAccessToken = token;
};

export const getAuthToken = (): string | null => {
  return inMemoryAccessToken;
};

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 5000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Dynamic Authorization header attachment from memory
apiClient.interceptors.request.use(
  (config) => {
    if (inMemoryAccessToken) {
      config.headers.Authorization = `Bearer ${inMemoryAccessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

export const apiService = {
  /**
   * Fetches the current application and database health status.
   */
  async getHealth(): Promise<HealthResponse> {
    const response = await apiClient.get<HealthResponse>('/health');
    return response.data;
  },

  /**
   * Authenticates user credentials and returns an access token + profile.
   */
  async login(credentials: LoginCredentials): Promise<TokenResponse> {
    const response = await apiClient.post<TokenResponse>('/auth/login', credentials);
    return response.data;
  },

  /**
   * Retrieves the current authenticated user profile using the active token.
   */
  async getMe(): Promise<User> {
    const response = await apiClient.get<User>('/auth/me');
    return response.data;
  },

  /**
   * Lists registered users (Admin and Auditor only).
   */
  async listUsers(skip: number = 0, limit: number = 50): Promise<UserListResponse> {
    const response = await apiClient.get<UserListResponse>('/users', {
      params: { skip, limit },
    });
    return response.data;
  },

  /**
   * Provisions a new user account (Admin only).
   */
  async createUser(userData: UserCreateInput): Promise<User> {
    const response = await apiClient.post<User>('/users', userData);
    return response.data;
  },

  /**
   * Lists accounts (Account Holder receives own accounts, Admin/Auditor receives all).
   */
  async getAccounts(skip: number = 0, limit: number = 50): Promise<AccountListResponse> {
    const response = await apiClient.get<AccountListResponse>('/accounts', {
      params: { skip, limit },
    });
    return response.data;
  },

  /**
   * Retrieves details for a specific account.
   */
  async getAccount(id: string): Promise<Account> {
    const response = await apiClient.get<Account>(`/accounts/${id}`);
    return response.data;
  },

  /**
   * Provisions a new customer account (₹0.00 initial balance).
   */
  async createAccount(data: AccountCreateInput): Promise<Account> {
    const response = await apiClient.post<Account>('/accounts', data);
    return response.data;
  },

  /**
   * Updates account lifecycle status (Admin only).
   */
  async updateAccountStatus(id: string, status: AccountStatus): Promise<Account> {
    const response = await apiClient.patch<Account>(`/accounts/${id}/status`, { status });
    return response.data;
  },

  /**
   * Retrieves ledger entries for an account.
   */
  async getAccountLedger(id: string, skip: number = 0, limit: number = 50): Promise<LedgerEntryListResponse> {
    const response = await apiClient.get<LedgerEntryListResponse>(`/accounts/${id}/ledger`, {
      params: { skip, limit },
    });
    return response.data;
  },
};
