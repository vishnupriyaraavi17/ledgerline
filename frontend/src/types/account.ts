export type AccountType =
  | 'customer_checking'
  | 'customer_savings'
  | 'system_reserve'
  | 'internal_clearing';

export type AccountStatus = 'active' | 'frozen' | 'closed';

export interface Account {
  id: string;
  account_number: string;
  owner_id: string | null;
  name: string;
  account_type: AccountType;
  currency: string;
  balance: string;
  status: AccountStatus;
  created_at: string;
  updated_at: string;
}

export interface AccountCreateInput {
  name: string;
  account_type: AccountType;
  currency?: string;
  owner_id?: string;
}

export interface AccountListResponse {
  items: Account[];
  total: number;
  skip: number;
  limit: number;
}

export type EntryType = 'debit' | 'credit';

export interface LedgerEntry {
  id: string;
  transaction_id: string;
  account_id: string;
  entry_type: EntryType;
  amount: string;
  sequence: number;
  created_at: string;
}

export interface LedgerEntryListResponse {
  items: LedgerEntry[];
  total: number;
  skip: number;
  limit: number;
}
