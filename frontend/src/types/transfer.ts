import type { LedgerEntry } from './account';

export type TransactionType = 'transfer' | 'adjustment' | 'settlement';

export interface DepositRequest {
  account_id: string;
  amount: string;
  description?: string;
}

export interface WithdrawRequest {
  account_id: string;
  amount: string;
  description?: string;
}

export interface TransferRequest {
  source_account_id: string;
  destination_account_id: string;
  amount: string;
  description?: string;
}

export interface TransactionResponse {
  id: string;
  reference: string;
  transaction_type: TransactionType;
  description: string;
  posted_at: string;
  entries: LedgerEntry[];
}

export interface TransactionListResponse {
  items: TransactionResponse[];
  total: number;
  skip: number;
  limit: number;
}

export interface FinancialOperationResult {
  transaction: TransactionResponse;
  isReplay: boolean;
}
