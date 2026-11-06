# LedgerLine — Threat Register & Security Architecture

This document tracks all identified attack vectors against LedgerLine's core invariant: **the books always balance, the same request never pays twice, and the ledger provides indisputable cryptographic auditability**.

In accordance with LedgerLine engineering standards, **no threat is marked as "Mitigated" until the corresponding implementation and automated concurrency/integrity tests exist and pass**.

---

## Threat Matrix Overview

| Threat ID | Threat Category | Severity | Current Status |
| :--- | :--- | :--- | :--- |
| **THR-01** | Unauthorised Account Access | Critical | **Partially Mitigated (Task 02)** (Identity, Argon2id auth, JWT, and generic 401s implemented; account binding in Task 03) |
| **THR-02** | Concurrent Withdrawals (Race Conditions) | Critical | **Identified / Foundation Established** (Pessimistic locking & isolation scheduled for Task 03) |
| **THR-03** | Duplicate Money Movement (Replay Attacks) | Critical | **Identified / Foundation Established** (Atomic idempotency engine scheduled for Task 03) |
| **THR-04** | Negative Balances / Overdraft Violations | Critical | **Identified / Foundation Established** (Atomic balance checks & DB check constraints scheduled for Task 03) |
| **THR-05** | Ledger Modification or Deletion (Tampering) | Critical | **Identified / Foundation Established** (Append-only schema, DB triggers & cryptographic hashing scheduled for Task 04) |
| **THR-06** | Privilege Escalation | High | **Mitigated (Task 02)** (Server-side RBAC dependency factory with Admin, Account Holder, Auditor role enforcement) |
| **THR-07** | Forged Requests & Parameter Tampering | High | **Identified / Foundation Established** (Pydantic validation active; request signatures scheduled for Task 03) |
| **THR-08** | Database Failure & Connection Outages | High | **Mitigated (Foundation Phase)** (Tested via real PostgreSQL probe, pooling & error masking) |

---

## Detailed Threat Register

### THR-01: Unauthorised Account Access
- **Attack Scenario**: A malicious actor or authenticated account holder submits a transfer or withdrawal request specifying an account identifier belonging to another customer (`source_account_id`), attempting to drain third-party funds.
- **Planned Mitigation**: Server-side authorization resolution on every request. Accounts will be cryptographically bound to authenticated user identities. The database transaction will verify ownership inside the row lock before evaluating balances or writing ledger debits.
- **Implemented Defenses (Task 02)**: Strict Argon2id password hashing, generic HTTP 401 unauthenticated errors (preventing user enumeration), in-memory JWT storage on client, and server-side `is_active` validation that immediately revokes access if an account is disabled.
- **Verification Tests**:
  - `backend/tests/unit/test_passwords.py`: Argon2id salt randomness, constant-time verification.
  - `backend/tests/unit/test_tokens.py`: JWT signature verification, expiration and tamper rejection.
  - `backend/tests/integration/test_auth_rbac_integration.py`: `test_login_wrong_password_returns_generic_401`, `test_login_nonexistent_user_returns_generic_401`, `test_inactive_user_cannot_login`, `test_inactive_user_with_previously_issued_token_rejected_server_side`.
- **Current Status**: **Partially Mitigated (Task 02)** — Authentication and session controls operational; account-level ownership binding scheduled for Task 03.

---

### THR-02: Concurrent Withdrawals (Race Condition / Double Spend)
- **Attack Scenario**: Two withdrawal requests of \$100 arrive simultaneously for an account with an available balance of \$100. Both requests read the balance concurrently (\$100), both pass the sufficiency check, and both commit debits, driving the account balance to -\$100.
- **Planned Mitigation**: Pessimistic row-level locking (`SELECT ... FOR UPDATE`) ordered deterministically by account ID to prevent deadlocks, combined with database-level check constraints (`CHECK (balance >= 0)`). Balances will be derived or atomically adjusted within strict ACID transactions.
- **Verification Test**: Multithreaded concurrent test using `concurrent.futures` firing 20 simultaneous requests against a single balance; exactly one must succeed, 19 must fail with refused attempt records.
- **Current Status**: **Identified / Planned** — Core transaction manager and row locking scheduled for Task 03.

---

### THR-03: Duplicate Money Movement (Replays & Retries)
- **Attack Scenario**: A client initiates a \$500 payment. Due to network latency, the HTTP connection drops before the client receives the response. The client retries the request with the same idempotency key, resulting in two payments sent to the payee.
- **Planned Mitigation**: Client-supplied `Idempotency-Key` persisted in an atomic idempotency table inside the same database transaction as the financial movement. If a duplicate key arrives:
  - If the original transaction succeeded, the server replays the original response payload without re-executing ledger writes.
  - If the original transaction is currently in-flight, subsequent requests receive an `HTTP 409 Conflict` or await the outcome.
- **Verification Test**: Automated test sending identical requests with identical keys concurrently and sequentially; verifies money moves exactly once and duplicate attempt is flagged in audit logs.
- **Current Status**: **Identified / Planned** — Idempotency repository and lifecycle management scheduled for Task 03.

---

### THR-04: Negative Balances
- **Attack Scenario**: An account balance is driven below zero through rounding errors, fee additions, uncoordinated refunds, or concurrent races.
- **Planned Mitigation**: Enforce zero-floor invariants at three layers:
  1. Application business validation inside the repository layer.
  2. SQL column check constraint: `CONSTRAINT chk_balance_non_negative CHECK (balance >= 0)`.
  3. Double-entry validation: `SUM(debits) - SUM(credits) == 0` for all transactions.
- **Verification Test**: Automated test attempting a withdrawal exceeding the balance by 1 cent, and a direct database SQL update attempting to force a negative balance; both must be rejected.
- **Current Status**: **Identified / Planned** — Account schemas and database constraints scheduled for Task 02.

---

### THR-05: Ledger Modification or Deletion (Silent Tampering)
- **Attack Scenario**: A rogue database administrator, application bug, or SQL injection executes `UPDATE` or `DELETE` on the `ledger_entries` or `statements` tables to conceal an illicit disbursement.
- **Planned Mitigation**: 
  1. The financial ledger is strictly **append-only**.
  2. PostgreSQL table-level privilege revocation: application user is granted only `INSERT` and `SELECT` on `ledger_entries` (no `UPDATE` or `DELETE`).
  3. Database trigger rejecting any `UPDATE` or `DELETE` statement.
  4. Cryptographic chaining: each ledger posting contains a SHA-256 hash of the previous ledger row (`prev_hash`), creating an immutable tamper-evident chain.
- **Verification Test**: Automated test asserting that `UPDATE` or `DELETE` on `ledger_entries` raises an unhandled database exception and fails.
- **Current Status**: **Identified / Planned** — Double-entry ledger architecture scheduled for Task 04.

---

### THR-06: Privilege Escalation
- **Attack Scenario**: An Account Holder role calls administrative endpoints (e.g., user provisioning, account adjustments) or an Auditor attempts to execute money transfers or modify system state.
- **Planned Mitigation**: Role-based access control (RBAC) enforced via FastAPI dependency injection at the endpoint route level before handler execution. Roles:
  - `Admin`: User provisioning, policy management, system monitoring.
  - `AccountHolder`: Transfer, deposit, withdrawal initiation on owned accounts only.
  - `Auditor`: Read-only access to directory, statements, invariants, and compliance records.
- **Implemented Defenses (Task 02)**: Route-level `require_role(...)` dependency factory verifying token claims against live DB status. Administrative creation endpoints restrict non-admins (`HTTP 403 Forbidden`). Directory listing endpoints restrict Account Holders (`HTTP 403 Forbidden`).
- **Verification Tests**:
  - `backend/tests/integration/test_auth_rbac_integration.py`: `test_admin_can_provision_new_user`, `test_auditor_cannot_provision_user`, `test_account_holder_cannot_provision_user`, `test_admin_can_list_users`, `test_auditor_can_list_users`, `test_account_holder_cannot_list_users`.
- **Current Status**: **Mitigated (Task 02)** — RBAC enforcement operational and tested across all roles.

---

### THR-07: Forged Requests & Parameter Tampering
- **Attack Scenario**: An attacker submits negative transfer amounts (`-500.00`), floating-point numbers designed to trigger rounding flaws (`10.0000001`), or oversized payloads to crash the server.
- **Planned Mitigation**: Strict Pydantic v2 schemas validating positive integers (representing minor currency units, e.g. cents/paise) or fixed-precision `Decimal` values. String sanitization and UUID validation on all entity IDs.
- **Verification Test**: Unit and API tests submitting invalid values, negative amounts, zero amounts, and SQL injection strings; all must be rejected at the boundary with HTTP 422 Unprocessable Entity.
- **Current Status**: **Identified / Planned** — Base schemas created; financial transfer schemas scheduled for Task 03.

---

### THR-08: Database Failure & Connection Outages
- **Attack Scenario**: The PostgreSQL server crashes, exhausts its connection pool, or becomes temporarily unreachable due to network partitions, causing transactions to fail halfway or exposing sensitive stack traces and credentials.
- **Planned Mitigation**:
  1. Synchronous SQLAlchemy connection pooling with pre-ping validation (`pool_pre_ping=True`) to detect dropped sockets.
  2. Safe exception handling in repositories: operational exceptions are captured, masked, and returned as HTTP 503 Service Unavailable without leaking credentials, internal paths, or SQL statements.
  3. Strict transaction rollback (`finally: db.close()` / `db.rollback()`) on any error during execution.
- **Verification Test**: `test_real_postgres_invalid_configuration_handled_safely` executed against an unreachable port, confirming HTTP 503 response and zero credential leakage.
- **Current Status**: **Mitigated (Foundation Phase)** — Verified via automated integration tests `test_health_postgres_integration.py`.

---

## Known Accepted Risks (Foundation Phase)
1. **Plain HTTP in Local Development**: Local testing runs over plain HTTP (`http://127.0.0.1:8000`). TLS termination will be enforced in production deployment via reverse proxy (Nginx / Caddy / Cloud Provider).
2. **Synchronous Request Processing**: Synchronous database drivers (`psycopg`) are deliberately chosen to ensure serializable, predictable ACID transaction lifecycles that can be rigorously defended during code review. High-concurrency scalability will be managed via SQLAlchemy connection pooling.
