# LedgerLine — Threat Register & Security Architecture

This document tracks all identified attack vectors against LedgerLine's core invariant: **the books always balance, the same request never pays twice, and the ledger provides indisputable cryptographic auditability**.

In accordance with LedgerLine engineering standards, **no threat is marked as "Mitigated" until the corresponding implementation and automated concurrency/integrity tests exist and pass**.

---

## Threat Matrix Overview

| Threat ID | Threat Category | Severity | Current Status |
| :--- | :--- | :--- | :--- |
| **THR-01** | Unauthorised Account Access | Critical | **Identified / Foundation Established** (Auth & access control scheduled for Task 02) |
| **THR-02** | Concurrent Withdrawals (Race Conditions) | Critical | **Identified / Foundation Established** (Pessimistic locking & isolation scheduled for Task 03) |
| **THR-03** | Duplicate Money Movement (Replay Attacks) | Critical | **Identified / Foundation Established** (Atomic idempotency engine scheduled for Task 03) |
| **THR-04** | Negative Balances / Overdraft Violations | Critical | **Identified / Foundation Established** (Atomic balance checks & DB check constraints scheduled for Task 02) |
| **THR-05** | Ledger Modification or Deletion (Tampering) | Critical | **Identified / Foundation Established** (Append-only schema, DB triggers & cryptographic hashing scheduled for Task 04) |
| **THR-06** | Privilege Escalation | High | **Identified / Foundation Established** (Role-based access control engine scheduled for Task 02) |
| **THR-07** | Forged Requests & Parameter Tampering | High | **Identified / Foundation Established** (Pydantic validation active; request signatures scheduled for Task 03) |
| **THR-08** | Database Failure & Connection Outages | High | **Mitigated (Foundation Phase)** (Tested via real PostgreSQL probe, pooling & error masking) |

---

## Detailed Threat Register

### THR-01: Unauthorised Account Access
- **Attack Scenario**: A malicious actor or authenticated account holder submits a transfer or withdrawal request specifying an account identifier belonging to another customer (`source_account_id`), attempting to drain third-party funds.
- **Planned Mitigation**: Server-side authorization resolution on every request. Accounts will be cryptographically bound to authenticated user identities. The database transaction will verify ownership inside the row lock before evaluating balances or writing ledger debits.
- **Verification Test**: Automated integration test where User A attempts to initiate a debit on User B's account; must return HTTP 403 Forbidden with zero ledger entries generated.
- **Current Status**: **Identified / Planned** — Foundation established; user authentication and account ownership models are scheduled for Task 02.

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
- **Attack Scenario**: An Account Holder role calls administrative endpoints (e.g., account adjustments, freeze accounts) or an Auditor attempts to execute money transfers.
- **Planned Mitigation**: Role-based access control (RBAC) enforced via FastAPI dependency injection at the endpoint route level before handler execution. Roles:
  - `Admin`: Account provisioning, policy management, system monitoring.
  - `AccountHolder`: Transfer, deposit, withdrawal initiation on owned accounts only.
  - `Auditor`: Read-only access to ledger statements, invariants, and threat reports.
- **Verification Test**: Matrix test calling every endpoint with each of the three roles and verifying HTTP 403 Forbidden for unauthorized roles.
- **Current Status**: **Identified / Planned** — Security dependencies and role claims scheduled for Task 02.

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
