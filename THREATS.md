# LedgerLine — Threat Register & Security Architecture

This document tracks all identified attack vectors against LedgerLine's core invariant: **the books always balance, the same request never pays twice, and the ledger provides indisputable cryptographic auditability**.

In accordance with LedgerLine engineering standards, **no threat is marked as "Mitigated" until the corresponding implementation and automated concurrency/integrity tests exist and pass**.

---

## Threat Matrix Overview

| Threat ID | Threat Category | Severity | Current Status |
| :--- | :--- | :--- | :--- |
| **THR-01** | Unauthorised Account Access & Account Enumeration | Critical | **Mitigated (Task 03 & Task 04)** (Identity-bound ownership, HTTP 404 anti-enumeration across accounts and transfers) |
| **THR-02** | Concurrent Withdrawals (Race Conditions) | Critical | **Mitigated (Task 04)** (Deterministic pessimistic row locking `with_for_update(of=Account)`, pre-check sufficiency, and `chk_customer_balance_non_negative`) |
| **THR-03** | Duplicate Money Movement (Replay Attacks) | Critical | **Mitigated (Task 05)** (PostgreSQL-backed idempotency engine, deterministic SHA-256 canonical request fingerprinting, mandatory `Idempotency-Key` header, atomic transaction commit, pessimistic row locking `SELECT ... FOR UPDATE`, permanent audit retention with runtime DELETE denial) |
| **THR-04** | Negative Balances / Overdraft Violations | Critical | **Mitigated (Task 03 & Task 04)** (PostgreSQL check constraint `chk_customer_balance_non_negative`, sufficiency checks, and zero-sum deferred constraint trigger) |
| **THR-05** | Ledger Modification or Deletion (Tampering) | Critical | **Mitigated (Task 03 & Task 04)** (PostgreSQL immutability triggers on row/statement levels, column-level least privilege; hash chaining scheduled for Task 05) |
| **THR-06** | Privilege Escalation | High | **Mitigated (Task 02, Task 03 & Task 04)** (Server-side RBAC dependency factory, financial operations denied to Auditors, lifecycle FSM restricted to Admin) |
| **THR-07** | Forged Requests & Parameter Tampering | High | **Mitigated (Task 03 & Task 04)** (Strict Pydantic v2 validation with `extra="forbid"`, self-transfer rejection, scale $\le 2$, single currency INR, `Decimal(20, 2)` monetary precision) |

| **THR-08** | Database Failure & Connection Outages | High | **Mitigated (Foundation Phase)** (Tested via real PostgreSQL probe, pooling & error masking) |
| **THR-09** | Direct Balance Modification & System Account Spoofing | Critical | **Mitigated (Task 03)** (PostgreSQL column-level grants excluding `balance`, trigger `trg_enforce_account_creation_permissions` guarding system accounts and `ACC-SYSTEM[0-9]{2}`) |

---

## Detailed Threat Register

### THR-01: Unauthorised Account Access & Account Enumeration
- **Attack Scenario**: A malicious actor or authenticated account holder submits a request targeting an account identifier belonging to another customer (`id`), attempting to enumerate existing account numbers or access private balance and transaction data.
- **Implemented Defenses (Task 02 & Task 03)**:
  1. Accounts are strictly bound to authenticated user identities (`owner_id = current_user.id`).
  2. Account Holders querying non-owned accounts (`GET /api/v1/accounts/{id}` or `GET /api/v1/accounts/{id}/ledger`) receive **`HTTP 404 Not Found`**, completely eliminating timing and enumeration side channels.
  3. `GET /api/v1/accounts` automatically filters and returns only self-owned accounts for Account Holders.
- **Verification Tests**:
  - `backend/tests/integration/test_accounts_integration.py::test_group_a_ownership_isolation_and_404_anti_enumeration`.
- **Current Status**: **Mitigated (Task 03)**.

---

### THR-02: Concurrent Withdrawals (Race Condition / Double Spend)
- **Attack Scenario**: Two withdrawal requests of ₹100 arrive simultaneously for an account with an available balance of ₹100. Both requests read the balance concurrently (₹100), both pass the sufficiency check, and both commit debits, driving the account balance to -₹100.
- **Implemented Defenses (Task 04)**:
  1. **Deterministic Pessimistic Row Locking**: All financial operations lock customer accounts via `SELECT ... FOR UPDATE OF accounts`. For inter-account transfers involving two customer accounts, locks are ordered deterministically by UUID (`min(source_id, dest_id)` then `max(source_id, dest_id)`), completely eliminating cyclic deadlocks.
  2. **Atomic Double-Entry Posting**: Every financial movement writes equal and opposite debit and credit entries inside an atomic ACID transaction.
  3. **Application Sufficiency Checks**: In-flight balance sufficiency is verified within the pessimistic row lock before creating ledger entries.
  4. **PostgreSQL Check Constraint**: `chk_customer_balance_non_negative` serves as the final database-level barrier, immediately rolling back any debit that would drive a customer balance negative.
- **Verification Tests**:
  - `backend/tests/integration/test_transfers_integration.py::test_group_a_successful_peer_to_peer_transfer`.
  - `backend/tests/integration/test_transfers_integration.py::test_group_a_overdraft_withdrawal_insufficient_funds`.
  - `backend/tests/integration/test_transfers_integration.py::test_group_a_overdraft_transfer_insufficient_funds`.
- **Current Status**: **Mitigated (Task 04)**.


---

### THR-03: Duplicate Money Movement (Replay Attacks & Retries)
- **Attack Scenario**: A client initiates a ₹500 payment. Due to network latency, the HTTP connection drops before the client receives the response. The client retries the request with the same idempotency key, resulting in two payments sent to the payee. Or a user double-clicks the transfer button, resulting in duplicate transactions.
- **Implemented Defenses (Task 05)**:
  1. **Mandatory Client Idempotency Key**: All financial write endpoints (`/transfers/deposit`, `/transfers/withdraw`, `/transfers/transfer`) strictly mandate an `Idempotency-Key` header (8–128 printable ASCII characters).
  2. **Deterministic SHA-256 Canonical Fingerprinting**: Request parameters are canonicalized (method, path, sorted payload parameters, exact decimal amounts) and hashed with SHA-256. Payload modifications under an existing key are immediately rejected with `HTTP 409 Conflict`.
  3. **Atomic Commit Boundary**: Idempotency records (`idempotency_records`) and ledger transactions/entries are written and committed within the exact same PostgreSQL database transaction. If the operation fails or rolls back, no dangling completed idempotency record remains.
  4. **PostgreSQL Pessimistic Row Locking Concurrency Control**: Concurrent requests for the same key are deduplicated using PostgreSQL row-level locks (`SELECT ... FOR UPDATE` on `idempotency_records`). In-flight duplicates wait for the primary transaction to complete and then safely replay the committed response.
  5. **Idempotent Replay Transparency**: Cached responses are replayed identically with the original status code, response body, and an `Idempotent-Replay: true` HTTP response header.
  6. **Permanent Audit Retention & Least Privilege**: The application runtime role (`ledgerline_app`) is granted `SELECT, INSERT, UPDATE` on `idempotency_records`, while `DELETE` is strictly withheld. Foreign keys enforce `ON DELETE RESTRICT` on `user_id` and `transaction_id`.
- **Verification Tests**:
  - `backend/tests/unit/test_idempotency_fingerprint.py` (canonical deterministic SHA-256 fingerprinting).
  - `backend/tests/unit/test_idempotency_validation.py` (header validation rules).
  - `backend/tests/integration/test_idempotency_integration.py` (Group A: Replay; Group B: 409 Conflict; Group C: Multi-tenant isolation; Group D: Concurrency race deduplication, rollback cleanup, FK ON DELETE RESTRICT, runtime DELETE denial).
- **Current Status**: **Mitigated (Task 05)**.

---

### THR-04: Negative Balances
- **Attack Scenario**: An account balance is driven below zero through rounding errors, fee additions, uncoordinated refunds, or concurrent races.
- **Implemented Defenses (Task 03)**:
  1. SQL Check Constraint: `CONSTRAINT chk_customer_balance_non_negative CHECK (account_type NOT IN ('customer_checking', 'customer_savings') OR balance >= 0)`.
  2. Currency Constraint: `CONSTRAINT chk_account_currency CHECK (currency = 'INR')`.
  3. Account Number Constraint: `CONSTRAINT chk_account_number_format CHECK (account_number ~ '^ACC-[A-Z0-9]{8}$')`.
  4. Positive Ledger Entry Amount: `CONSTRAINT chk_ledger_entry_amount_positive CHECK (amount > 0)`.
  5. Zero-balance initialization: newly created accounts strictly initialize at ₹0.00 via database-side `DEFAULT 0.00`.
- **Verification Tests**:
  - `backend/tests/integration/test_accounts_integration.py::test_group_a_zero_balance_account_creation_api`.
  - `backend/tests/integration/test_accounts_integration.py::test_group_a_privilege_and_trigger_enforcement_under_runtime_role`.
- **Current Status**: **Mitigated (Task 03)**.

---

### THR-05: Ledger Modification or Deletion (Silent Tampering)
- **Attack Scenario**: A rogue database administrator, application bug, or SQL injection executes `UPDATE`, `DELETE`, or `TRUNCATE` on `ledger_entries` or `ledger_transactions` to conceal an illicit disbursement.
- **Implemented Defenses (Task 03)**:
  1. The financial ledger is strictly **append-only**.
  2. PostgreSQL table-level privileges: table-level `INSERT`, `UPDATE`, `DELETE`, and `TRUNCATE` privileges on `ledger_entries` and `ledger_transactions` are revoked from the runtime role (`ledgerline_app`) and `PUBLIC`.
  3. Row-level engine triggers (`trg_protect_ledger_entries_row`, `trg_protect_ledger_transactions_row`) unconditionally raise exceptions on any `UPDATE` or `DELETE`.
  4. Statement-level engine triggers (`trg_protect_ledger_entries_truncate`, `trg_protect_ledger_transactions_truncate`) unconditionally raise exceptions on any `TRUNCATE`.
- **Verification Tests**:
  - `backend/tests/integration/test_accounts_integration.py::test_group_a_effective_postgresql_privileges`.
  - `backend/tests/integration/test_accounts_integration.py::test_group_b_immutability_triggers_on_actual_rows`.
- **Current Status**: **Mitigated (Task 03)** (Cryptographic hash chaining scheduled for Task 05).

---

### THR-06: Privilege Escalation
- **Attack Scenario**: An Account Holder role calls administrative endpoints (e.g. status transition, user provisioning) or an Auditor attempts to create accounts.
- **Implemented Defenses (Task 02 & Task 03)**:
  1. Route-level `require_role(...)` dependency factory verifying token claims against live DB status.
  2. Account lifecycle updates (`PATCH /api/v1/accounts/{id}/status`) strictly require `Admin` role. Account Holders and Auditors receive `HTTP 403 Forbidden`.
  3. Account creation (`POST /api/v1/accounts`) is denied to Auditors (`HTTP 403 Forbidden`).
  4. Closed accounts are strictly terminal; reopening is rejected with `HTTP 400 Bad Request`.
  5. Account closure strictly requires `balance == 0.00`.
- **Verification Tests**:
  - `backend/tests/unit/test_account_lifecycle_unit.py`.
  - `backend/tests/integration/test_accounts_integration.py::test_group_a_role_based_restrictions_and_lifecycle`.
- **Current Status**: **Mitigated (Task 02 & Task 03)**.

---

### THR-07: Forged Requests & Parameter Tampering
- **Attack Scenario**: An attacker submits non-INR currencies, floating-point numbers designed to trigger rounding flaws (`10.0000001`), opening balance amounts in account creation payloads, or malformed schemas.
- **Implemented Defenses (Task 03)**:
  1. Pydantic v2 schemas with `ConfigDict(extra="forbid")` rejecting any extraneous fields (e.g. `balance`).
  2. Currency validation strictly enforcing `"INR"`.
  3. Account type validation strictly permitting only customer accounts (`customer_checking`, `customer_savings`) via API.
  4. Fixed-precision `Decimal(20, 2)` arithmetic eliminating binary float rounding issues.
- **Verification Tests**:
  - `backend/tests/unit/test_monetary_decimal.py`.
  - `backend/tests/unit/test_account_schemas.py`.
- **Current Status**: **Mitigated (Task 03)**.

---

### THR-08: Database Failure & Connection Outages
- **Attack Scenario**: PostgreSQL server crashes or network partitions cause partial transactions or credential exposure.
- **Implemented Defenses**: Synchronous connection pooling with `pool_pre_ping=True`, masked operational errors, and strict transaction rollback.
- **Current Status**: **Mitigated (Foundation Phase)**.

---

### THR-09: Direct Balance Modification & System Account Spoofing
- **Attack Scenario**: An attacker exploits the application database role to directly update `accounts.balance` or insert spoofed system accounts (e.g. `system_reserve` or reserved account numbers `ACC-SYSTEM01`).
- **Implemented Defenses (Task 03)**:
  1. **Column-Level Privilege Isolation**: The application runtime role (`ledgerline_app`) is granted `INSERT` only on approved metadata columns (strictly omitting `balance`), and `UPDATE` only on `(status, updated_at)`. Direct `balance` updates or inserts are rejected at PostgreSQL's permission check.
  2. **System Account Creation Trigger**: `trg_enforce_account_creation_permissions` rejects any insertion of `system_reserve` or `internal_clearing` accounts or account numbers matching `ACC-SYSTEM[0-9]{2}` by any role other than the migration owner (`ledgerline_owner`).
  3. **Role Separation**: Migration owner (`ledgerline_owner`) and runtime role (`ledgerline_app`) are completely isolated with `NOINHERIT`, `NOSUPERUSER`, `NOCREATEROLE`, `NOCREATEDB`, `NOREPLICATION`, `NOBYPASSRLS`, and zero role memberships.
- **Verification Tests**:
  - `backend/tests/integration/test_accounts_integration.py::test_group_a_privilege_and_trigger_enforcement_under_runtime_role`.
  - `backend/tests/integration/test_accounts_integration.py::test_group_b_owner_role_system_account_creation_trigger`.
- **Current Status**: **Mitigated (Task 03)**.

---

## Known Accepted Risks
1. **Plain HTTP in Local Development**: Local testing runs over plain HTTP (`http://127.0.0.1:8000`). TLS termination will be enforced in production deployment via reverse proxy.
2. **Synchronous Request Processing**: Synchronous database drivers (`psycopg`) ensure serializable, predictable ACID transaction lifecycles.
