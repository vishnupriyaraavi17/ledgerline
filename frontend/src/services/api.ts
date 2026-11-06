import axios from 'axios';
import type { AxiosInstance } from 'axios';
import type { HealthResponse } from '../types/health';
import type { LoginCredentials, TokenResponse, User, UserCreateInput, UserListResponse } from '../types/auth';

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
};
