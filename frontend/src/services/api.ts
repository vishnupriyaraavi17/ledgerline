import axios from 'axios';
import type { AxiosInstance } from 'axios';
import type { HealthResponse } from '../types/health';
import type { LoginCredentials, TokenResponse, User, UserCreateInput, UserRegisterInput, UserListResponse } from '../types/auth';
import type {
  Account,
  AccountCreateInput,
  AccountListResponse,
  AccountStatus,
  LedgerEntryListResponse,
} from '../types/account';
import type {
  DepositRequest,
  WithdrawRequest,
  TransferRequest,
  TransactionResponse,
  TransactionListResponse,
  FinancialOperationResult,
} from '../types/transfer';
import type {
  AuditListResponse,
  VerificationResult,
  AuditHead,
} from '../types/audit';
import type { AccountStatementResponse } from '../types/statement';


const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '/api/v1' : 'http://127.0.0.1:8000/api/v1');

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
  timeout: 10000,
  withCredentials: true,
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

// Concurrency-safe automatic token renewal queue
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value?: any) => void;
  reject: (reason?: any) => void;
}> = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

// Response interceptor: automatically renew expired access tokens via HttpOnly refresh cookie
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/auth/login') &&
      !originalRequest.url?.includes('/auth/refresh') &&
      !originalRequest.url?.includes('/auth/register')
    ) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return apiClient(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const refreshResponse = await axios.post<TokenResponse>(
          `${API_BASE_URL}/auth/refresh`,
          {},
          { withCredentials: true }
        );
        const newAccessToken = refreshResponse.data.access_token;
        setAuthToken(newAccessToken);
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        processQueue(null, newAccessToken);
        return apiClient(originalRequest);
      } catch (refreshErr) {
        processQueue(refreshErr, null);
        setAuthToken(null);
        return Promise.reject(refreshErr);
      } finally {
        isRefreshing = false;
      }
    }
    return Promise.reject(error);
  }
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
   * Restores an authenticated session via the HttpOnly, Secure refresh cookie.
   */
  async refreshToken(): Promise<TokenResponse> {
    const response = await apiClient.post<TokenResponse>('/auth/refresh');
    return response.data;
  },

  /**
   * Revokes the active server-side session in Redis and clears the HttpOnly cookie.
   */
  async logout(): Promise<void> {
    try {
      await apiClient.post('/auth/logout');
    } finally {
      setAuthToken(null);
    }
  },

  /**
   * Registers a new self-service customer profile (Account Holder only).
   */
  async register(data: UserRegisterInput): Promise<User> {
    const response = await apiClient.post<User>('/auth/register', data);
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

  /**
   * Performs simulated deposit into customer account with mandatory client-generated idempotency key.
   */
  async deposit(data: DepositRequest, idempotencyKey: string): Promise<FinancialOperationResult> {
    const response = await apiClient.post<TransactionResponse>('/transfers/deposit', data, {
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
    });
    const replayHeader = response.headers['idempotent-replay'] || response.headers['Idempotent-Replay'];
    return {
      transaction: response.data,
      isReplay: replayHeader === 'true',
    };
  },

  /**
   * Performs simulated withdrawal from customer account with mandatory client-generated idempotency key.
   */
  async withdraw(data: WithdrawRequest, idempotencyKey: string): Promise<FinancialOperationResult> {
    const response = await apiClient.post<TransactionResponse>('/transfers/withdraw', data, {
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
    });
    const replayHeader = response.headers['idempotent-replay'] || response.headers['Idempotent-Replay'];
    return {
      transaction: response.data,
      isReplay: replayHeader === 'true',
    };
  },

  /**
   * Transfers funds between two customer accounts with mandatory client-generated idempotency key.
   */
  async transfer(data: TransferRequest, idempotencyKey: string): Promise<FinancialOperationResult> {
    const response = await apiClient.post<TransactionResponse>('/transfers/transfer', data, {
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
    });
    const replayHeader = response.headers['idempotent-replay'] || response.headers['Idempotent-Replay'];
    return {
      transaction: response.data,
      isReplay: replayHeader === 'true',
    };
  },

  /**
   * Retrieves transaction details by reference.
   */
  async getTransaction(reference: string): Promise<TransactionResponse> {
    const response = await apiClient.get<TransactionResponse>(`/transfers/${reference}`);
    return response.data;
  },

  /**
   * Retrieves paginated transaction journal entries.
   */
  async listTransactions(skip: number = 0, limit: number = 50): Promise<TransactionListResponse> {
    const response = await apiClient.get<TransactionListResponse>('/transfers', {
      params: { skip, limit },
    });
    return response.data;
  },

  /**
   * Executes full mathematical verification of the cryptographic audit chain.
   */
  async verifyAuditChain(): Promise<VerificationResult> {
    const response = await apiClient.get<VerificationResult>('/audit/verify');
    return response.data;
  },

  /**
   * Retrieves paginated audit trail events.
   */
  async getAuditEvents(
    params?: {
      event_type?: string;
      entity_type?: string;
      entity_id?: string;
      limit?: number;
      offset?: number;
    }
  ): Promise<AuditListResponse> {
    const response = await apiClient.get<AuditListResponse>('/audit/events', { params });
    return response.data;
  },

  /**
   * Retrieves current cryptographic chain head pointer.
   */
  async getAuditHead(): Promise<AuditHead> {
    const response = await apiClient.get<AuditHead>('/audit/head');
    return response.data;
  },

  /**
   * Retrieves mathematically verified account statement for interval [startDate, endDate).
   */
  async getAccountStatement(
    accountId: string,
    startDate?: string,
    endDate?: string,
    page: number = 1,
    pageSize: number = 50
  ): Promise<AccountStatementResponse> {
    const params: Record<string, any> = { page, page_size: pageSize };
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    const response = await apiClient.get<AccountStatementResponse>(`/accounts/${accountId}/statement`, { params });
    return response.data;
  },

  /**
   * Exports account statement as an RFC 4180 CSV blob protected against formula injection.
   */
  async exportAccountStatementCsv(
    accountId: string,
    startDate?: string,
    endDate?: string
  ): Promise<Blob> {
    const params: Record<string, any> = { format: 'csv' };
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    const response = await apiClient.get(`/accounts/${accountId}/statement/export`, {
      params,
      responseType: 'blob',
    });
    return response.data;
  },
};

