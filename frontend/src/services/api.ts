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
};

