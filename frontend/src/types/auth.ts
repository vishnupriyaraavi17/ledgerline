export type UserRole = 'admin' | 'account_holder' | 'auditor';

export interface User {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface LoginCredentials {
  username_or_email: string;
  password: string;
}

export interface UserCreateInput {
  username: string;
  email: string;
  password: string;
  role: UserRole;
}

export interface UserListResponse {
  items: User[];
  total: number;
  skip: number;
  limit: number;
}
