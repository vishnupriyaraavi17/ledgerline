export type TamperFailureType =
  | 'HASH_MISMATCH'
  | 'BROKEN_CHAIN'
  | 'SEQUENCE_GAP'
  | 'HEAD_DESYNC';

export interface TamperDetail {
  failure_type: TamperFailureType;
  sequence_number: number;
  event_id?: string | null;
  expected_value: string;
  actual_value: string;
  message: string;
}

export interface VerificationResult {
  is_valid: boolean;
  total_events: number;
  verified_at: string;
  head_sequence: number;
  head_hash: string;
  tamper_details?: TamperDetail | null;
}

export interface AuditEvent {
  id: string;
  sequence_number: number;
  event_type: string;
  actor_id?: string | null;
  actor_role?: string | null;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  current_hash: string;
  created_at: string;
}

export interface AuditListResponse {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditHead {
  sequence_number: number;
  current_hash: string;
  updated_at: string;
}
