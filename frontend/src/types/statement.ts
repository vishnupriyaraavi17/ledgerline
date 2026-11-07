import { Account } from './account';

export interface StatementTransactionItem {
  entry_id: string;
  transaction_id: string;
  reference: string;
  transaction_type: string;
  display_label: string;
  direction: 'credit' | 'debit';
  amount: string;
  currency: string;
  running_balance: string;
  status: string;
  description: string;
  posted_at: string;
  counterparty_account_number?: string | null;
  counterparty_name?: string | null;
}

export interface RefusedAttemptItem {
  id: string;
  operation_type: string;
  amount?: string | null;
  currency: string;
  refusal_reason: string;
  error_message: string;
  is_source: boolean;
  counterparty_account_number?: string | null;
  outcome: string;
  created_at: string;
}

export interface StatementSummary {
  opening_balance: string;
  closing_balance: string;
  total_credits: string;
  total_debits: string;
  net_change: string;
  total_posted_transactions: number;
  total_refused_attempts: number;
}

export interface StatementPeriod {
  start_date: string;
  end_date: string;
}

export interface AccountStatementResponse {
  account: Account;
  period: StatementPeriod;
  summary: StatementSummary;
  transactions: StatementTransactionItem[];
  refused_attempts: RefusedAttemptItem[];
  page: number;
  page_size: number;
  total_pages: number;
}
