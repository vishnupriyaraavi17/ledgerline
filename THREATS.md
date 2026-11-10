# LedgerLine — Threat Register & Security Architecture

> **VIRTUAL-MONEY DEMONSTRATION SYSTEM BOUNDARY**
> LedgerLine is an educational, demonstration banking prototype built for the Snovasys Fresher Hiring Challenge 2026.
> All balances, transfers, deposits, and accounts operate on **virtual, simulated currency (INR)** within a closed double-entry database core.
> LedgerLine **does not connect to real banking networks** (such as RBI RTGS/NEFT/IMPS, UPI, SWIFT, or payment gateway APIs) and does not hold or process real-world legal tender.

---

## 1. Threat Matrix Overview

| Threat ID | Threat Category | Severity | Implemented Defense | Status |
| :--- | :--- | :--- | :--- | :--- |
| **THR-01** | Password Hashing Weakness | Critical | Argon2id with memory cost 64MB, 3 iterations, 4 parallel threads, constant-time verification | **Mitigated** |
| **THR-02** | Stale / Revoked JWT Token Usage | High | Stateless HS256 JWTs paired with live DB user active status check on every authenticated request | **Mitigated** |
| **THR-03** | Privilege Escalation (RBAC Bypass) | Critical | Server-side `require_role(...)` dependency factory; Auditor financial write denial; Admin-only lifecycle | **Mitigated** |
| **THR-04** | Role Tampering in Public Registration | Critical | Registration endpoint strictly forces `role = ACCOUNT_HOLDER`; client payload cannot supply role | **Mitigated** |
| **THR-05** | Automated Account Registration Flooding | Medium | In-memory sliding-window rate limiter on IP (5/hr) and username/email (3/hr) with HTTP 429 | **Mitigated** |
| **THR-06** | Unauthorised Account Access & ID Enumeration | Critical | Strict user ownership filter (`owner_id = user.id`); cross-user accesses return uniform `HTTP 404` | **Mitigated** |
| **THR-07** | Double-Entry Imbalance / Phantom Money | Critical | Conserved double-entry ledger; every transaction requires equal debit and credit entries ($\sum \Delta = 0$) | **Mitigated** |
| **THR-08** | Negative Balances & Overdraft Violations | Critical | PostgreSQL check constraint `chk_customer_balance_non_negative`, sufficiency check, atomic posting | **Mitigated** |
| **THR-09** | Concurrent Withdrawals & Race Conditions | Critical | Deterministic pessimistic row locking (`SELECT ... FOR UPDATE OF accounts`) ordered by UUID | **Mitigated** |
| **THR-10** | Duplicate Money Movement & Replay Attacks | Critical | PostgreSQL-backed idempotency engine, mandatory `Idempotency-Key`, canonical SHA-256 fingerprinting | **Mitigated** |
| **THR-11** | Historical Ledger Modification or Deletion | Critical | Append-only SHA-256 cryptographic hash chain, PostgreSQL table & row immutability triggers | **Mitigated** |
| **THR-12** | Database Runtime Role Over-Privilege | High | Separation between migration owner (`ledgerline_owner`) and runtime app role (`ledgerline_app`) | **Mitigated** |
| **THR-13** | SQL Injection via Dynamic Query Construction | Critical | Parameterized queries via SQLAlchemy 2.x ORM / Core bind parameters; zero raw string interpolation | **Mitigated** |
| **THR-14** | CSV Spreadsheet Formula Injection (CWE-1236) | Medium | Automatic formula prefix neutralization with single quote (`'`), UTF-8 BOM (`EF BB BF`) in frontend | **Mitigated** |
| **THR-15** | Environment Secrets & Credential Exposure | High | Pydantic Settings strictly reading `.env`; zero credentials in Git; production bundle string scanning | **Mitigated** |
| **THR-16** | Test Database Contamination / Production Data Loss | Critical | Fail-closed guard in `conftest.py` requiring database name to end with `_test`; rejects `ledgerline` | **Mitigated** |

---

## 2. Detailed Threat Register

### THR-01: Password Hashing Weakness
- **Threat Description**: An attacker obtains a dump of the `users` table and attempts offline dictionary or brute-force attacks to crack user passwords.
- **Potential Impact**: Complete compromise of user credentials, unauthorized account takeover, and fraudulent transfers.
- **Existing Mitigation**:
  - Implemented in `backend/app/core/security.py` using `passlib.context.CryptContext(schemes=["argon2"])` powered by `argon2-cffi`.
  - Configured with memory cost 65,536 KiB (64 MB), time cost 3 iterations, and parallelism 4 lanes.
  - Constant-time password verification prevents side-channel timing attacks.
  - Integration tests in `backend/tests/unit/test_security_core.py` and `backend/tests/integration/test_auth_integration.py`.
- **Residual Risk**: High computational load on constrained containers during rapid successive logins. Mitigated by calibrated cost factors and registration rate limiting.
- **Status**: **Mitigated**.

---

### THR-02: Stale / Revoked JWT Token Usage
- **Threat Description**: A deactivated or deleted user continues accessing sensitive financial endpoints using a previously issued, unexpired JWT access token.
- **Potential Impact**: Unauthorized access by terminated employees, compromised users, or suspended account holders.
- **Existing Mitigation**:
  - Implemented in `backend/app/api/deps.py` (`get_current_user`).
  - While JWT verification (`HS256`, 60-minute expiry) verifies token signature and expiration, the authentication dependency re-queries PostgreSQL on every single request to verify `user.is_active is True`.
  - Immediate deactivation: when an administrator deactivates a user (`is_active = False`), all subsequent requests with that token are rejected with `HTTP 401 Unauthorized` without waiting for token expiry.
  - Verified in `backend/tests/integration/test_auth_integration.py::test_deactivated_user_token_rejection`.
- **Residual Risk**: Stateless JWT cannot be revoked across multiple distributed services without a database lookup or centralized token blacklist. In LedgerLine's modular architecture, the database lookup guarantees immediate revocation.
- **Status**: **Mitigated**.

---

### THR-03: Privilege Escalation (RBAC Bypass)
- **Threat Description**: An Account Holder or Auditor attempts to access administrative endpoints (e.g. user creation, account freezing/closing) or an Auditor attempts to execute financial transactions.
- **Potential Impact**: Unauthorized creation of privileged users, arbitrary account lifecycle state modifications, or unauthorized disbursement of funds.
- **Existing Mitigation**:
  - Implemented via `require_role(...)` dependency factory in `backend/app/api/deps.py`.
  - Roles strictly typed via `UserRole` enum (`admin`, `account_holder`, `auditor`).
  - Financial write endpoints (`/transfers/deposit`, `/transfers/withdraw`, `/transfers/transfer`) strictly require `UserRole.ACCOUNT_HOLDER`. Auditors and Admins attempting financial postings receive `HTTP 403 Forbidden`.
  - Account lifecycle transitions (`PATCH /api/v1/accounts/{id}/status`) strictly require `UserRole.ADMIN`.
  - Verified in `backend/tests/integration/test_rbac_integration.py` and `backend/tests/unit/test_account_lifecycle_unit.py`.
- **Residual Risk**: Role hierarchy is coarse-grained (3 roles); sufficient for application domain requirements.
- **Status**: **Mitigated**.

---

### THR-04: Role Tampering in Public Registration
- **Threat Description**: A malicious user calling the public self-registration endpoint (`POST /api/v1/auth/register`) injects `"role": "admin"` or `"role": "auditor"` into the request payload to self-provision elevated privileges.
- **Potential Impact**: Immediate administrative takeover of the banking platform by anonymous internet actors.
- **Existing Mitigation**:
  - Implemented in `backend/app/schemas/user.py` (`UserRegisterRequest`) and `backend/app/api/v1/endpoints/auth.py`.
  - The public registration schema `UserRegisterRequest` contains only `username`, `email`, and `password`. It does NOT accept a `role` field.
  - The endpoint handler hardcodes `role=UserRole.ACCOUNT_HOLDER` when instantiating the user entity before database insertion.
  - Admin and Auditor accounts can ONLY be provisioned by authenticated Administrators via `POST /api/v1/users`.
  - Verified in `backend/tests/integration/test_registration_integration.py::test_registration_forces_account_holder_role`.
- **Residual Risk**: Newly registered users receive customer accounts upon initial account creation; KYC verification is simulated.
- **Status**: **Mitigated**.

---

### THR-05: Automated Account Registration Flooding
- **Threat Description**: An attacker uses automated bot scripts to flood the public registration endpoint, exhausting database storage, CPU cycles (Argon2id hashing), and polluting the user table.
- **Potential Impact**: Denial of Service (DoS), database bloat, and CPU starvation.
- **Existing Mitigation**:
  - Implemented in `backend/app/security/rate_limiter.py` (`RegistrationRateLimiter`).
  - Tracks registration attempts using an in-memory sliding window:
    - Maximum 5 registrations per client IP address per hour.
    - Maximum 3 registration attempts per username or email per hour.
  - Violations return `HTTP 429 Too Many Requests` with a structured `Retry-After` header.
  - Appends `security.user_registered` event to the cryptographic audit chain for forensic traceability.
  - Verified in `backend/tests/integration/test_registration_integration.py::test_registration_rate_limiting`.
- **Residual Risk**: In-memory rate limiting state resets upon application server restart and is local to a single process instance. Production deployments with multiple replicas would require a shared Redis backend.
- **Status**: **Mitigated**.

---

### THR-06: Unauthorised Account Access & ID Enumeration
- **Threat Description**: An authenticated customer supplies arbitrary UUIDs in account or statement URLs (`/accounts/{id}`, `/accounts/{id}/statement`) to discover other customers' accounts, view private balances, or initiate transfers from third-party funds.
- **Potential Impact**: Breach of banking secrecy, financial privacy leaks, and identity discovery.
- **Existing Mitigation**:
  - Implemented in `backend/app/repositories/account.py`, `backend/app/api/v1/endpoints/accounts.py`, and `backend/app/api/v1/endpoints/statements.py`.
  - Account queries enforce `account.owner_id == current_user.id` for Account Holders.
  - If a user requests an account belonging to someone else, the application responds with **`HTTP 404 Not Found`** rather than `403 Forbidden`, preventing timing-based or existence-based account enumeration.
  - Customer accounts use random UUIDv4 identifiers plus cryptographically uniform `ACC-[A-Z0-9]{8}` account numbers.
  - Verified in `backend/tests/integration/test_accounts_integration.py::test_group_a_ownership_isolation_and_404_anti_enumeration`.
- **Residual Risk**: Admin and Auditor roles can view all accounts by design for supervisory oversight; protected by RBAC.
- **Status**: **Mitigated**.

---

### THR-07: Double-Entry Imbalance / Phantom Money Creation
- **Threat Description**: An operational bug, partial failure, or logic flaw causes money to be credited to a recipient without a corresponding debit to the sender, inflating total system liquidity.
- **Potential Impact**: Corrupted ledger books, unbacked currency creation, failure of accounting reconciliation.
- **Existing Mitigation**:
  - Implemented in `backend/app/services/transfer.py` and `backend/app/models/ledger.py`.
  - Every financial transaction strictly posts equal debit and credit entries inside a single atomic database transaction:
    - Deposit: DEBIT `ACC-SYSTEM02` (Clearing), CREDIT Customer Account.
    - Withdrawal: DEBIT Customer Account, CREDIT `ACC-SYSTEM02` (Clearing).
    - Transfer: DEBIT Source Customer Account, CREDIT Destination Customer Account.
  - Sum of entries in every transaction is mathematically zero: $\sum \text{Credits} - \sum \text{Debits} = 0$.
  - Atomic commit boundary ensures all entries succeed or none do (`db.commit()` or `db.rollback()`).
  - Verified in `backend/tests/integration/test_transfers_integration.py`.
- **Residual Risk**: Reliance on internal clearing account (`ACC-SYSTEM02`) to balance external inflows and outflows.
- **Status**: **Mitigated**.

---

### THR-08: Negative Balances & Overdraft Violations
- **Threat Description**: A withdrawal or transfer exceeds the available account balance, driving a customer account into an unarranged negative balance.
- **Potential Impact**: Bad debt, unauthorized credit extension, and violation of checking/savings account invariants.
- **Existing Mitigation**:
  - Implemented in `backend/app/services/transfer.py` and PostgreSQL schema (`0003_financial_foundation.py`).
  - Multi-layered defense:
    1. Pre-check: In-flight balance sufficiency verified under pessimistic row lock (`balance >= transfer_amount`).
    2. Database Constraint: SQL check constraint `CONSTRAINT chk_customer_balance_non_negative CHECK (account_type NOT IN ('customer_checking', 'customer_savings') OR balance >= 0)`.
    3. Immutable refusal recording: If balance is insufficient, the transaction is rolled back and an event is logged in `refused_operations` without touching ledger tables.
  - Verified in `backend/tests/integration/test_transfers_integration.py::test_group_a_overdraft_withdrawal_insufficient_funds`.
- **Residual Risk**: System clearing accounts (`ACC-SYSTEM02`) are permitted negative balances by design to represent net cumulative external equity/liability.
- **Status**: **Mitigated**.

---

### THR-09: Concurrent Withdrawals & Race Conditions
- **Threat Description**: An attacker sends two simultaneous transfer requests for ₹50,000 from an account holding only ₹50,000, exploiting race conditions between balance read and balance write.
- **Potential Impact**: Double-spending, negative balance, and ledger insolvency.
- **Existing Mitigation**:
  - Implemented in `backend/app/services/transfer.py`.
  - Deterministic pessimistic row locking: All affected accounts are locked via `SELECT ... FOR UPDATE OF accounts`.
  - Deadlock prevention: For inter-account transfers involving two customer accounts, locks are ordered deterministically by UUID (`min(id_a, id_b)` then `max(id_a, id_b)`), completely eliminating circular wait conditions.
  - The second concurrent transaction blocks until the first commits; upon unblocking, it reads the updated balance (₹0.00) and safely fails sufficiency check.
  - Verified in `backend/tests/integration/test_transfers_integration.py::test_group_c_concurrent_transfers`.
- **Residual Risk**: Pessimistic locking serializes operations on a single account; throughput on any individual account is bounded by database transaction round-trip latency.
- **Status**: **Mitigated**.

---

### THR-10: Duplicate Money Movement & Replay Attacks
- **Threat Description**: Network timeouts cause a client to retry a transfer, or an end-user double-clicks the "Send Money" button, causing two distinct transfers for one intended payment.
- **Potential Impact**: Duplicate debit to sender, accidental overpayment to recipient.
- **Existing Mitigation**:
  - Implemented in `backend/app/services/idempotency.py` and `backend/app/models/idempotency.py`.
  - Mandatory client-supplied `Idempotency-Key` header (8 to 128 characters).
  - Deterministic SHA-256 canonical request fingerprinting (HTTP method + endpoint path + sorted payload parameters).
  - Pessimistic row locking on `idempotency_records` deduplicates in-flight concurrent requests.
  - Replays committed responses identically with `Idempotent-Replay: true` header.
  - Payload tampering under an existing key returns `HTTP 409 Conflict`.
  - Verified in `backend/tests/unit/test_idempotency_fingerprint.py` and `backend/tests/integration/test_idempotency_integration.py` (Groups A–D).
- **Residual Risk**: Key namespace collisions between different users are prevented by compound indexing on `(user_id, idempotency_key)`.
- **Status**: **Mitigated**.

---

### THR-11: Historical Ledger Modification or Deletion
- **Threat Description**: A rogue administrator, SQL injection vulnerability, or compromised process attempts to modify or delete historical transactions to conceal theft or alter statements.
- **Potential Impact**: Undetected financial fraud, loss of auditability, and regulatory breach.
- **Existing Mitigation**:
  - Implemented in `backend/app/services/audit.py`, `backend/app/repositories/audit.py`, and PostgreSQL triggers (`0006_audit_trail.py`).
  - Append-only cryptographic hash chain: Every event is bound to a linear recursive SHA-256 hash:
    $$H_n = \text{SHA-256}(\text{CanonicalJSON}(E_n, H_{n-1})) \quad \text{with} \quad H_0 = 0^{64}$$
  - PostgreSQL database triggers: `trg_protect_ledger_entries_row`, `trg_protect_ledger_transactions_row`, and `trg_protect_audit_events_row` unconditionally raise exceptions on any `UPDATE`, `DELETE`, or `TRUNCATE`.
  - Controlled `SECURITY DEFINER` gatekeeper: Direct table inserts are revoked from the application runtime role; events can only be inserted via `append_audit_event()`.
  - Interactive streaming audit verifier detects `HASH_MISMATCH`, `BROKEN_CHAIN`, `SEQUENCE_GAP`, or `HEAD_DESYNC`.
  - Verified in `backend/tests/integration/test_audit_integration.py` (Groups A–E) and `backend/tests/integration/test_accounts_integration.py`.
- **Residual Risk**: A database superuser with raw disk or root PostgreSQL access could theoretically rewrite the entire table and recalculate hashes. In an enterprise production deployment, periodic head hash notarization (RFC 3161 timestamping or public blockchain/S3 Object Lock) provides external anchoring.
- **Status**: **Mitigated**.

---

### THR-12: Database Runtime Role Over-Privilege
- **Threat Description**: The application database connection has `SUPERUSER` or `ALL PRIVILEGES` access, allowing compromised application code to drop tables, bypass constraints, or modify permissions.
- **Potential Impact**: Complete database destruction, privilege bypass, and constraint dismantling.
- **Existing Mitigation**:
  - Implemented in database migrations (`0003_financial_foundation.py`, `0006_audit_trail.py`).
  - Role separation:
    - Migration Owner (`ledgerline_owner`): Owns schemas, tables, functions, and triggers.
    - Runtime Role (`ledgerline_app`): Granted strictly least-privilege `SELECT, INSERT, UPDATE` on necessary tables.
  - Column-level privilege restrictions: `ledgerline_app` has `UPDATE` privilege only on `accounts(status, updated_at)`. It has NO privilege to update `accounts(balance)`.
  - Direct balance modifications without double-entry ledger entries are rejected by PostgreSQL's permission system.
  - Verified in `backend/tests/integration/test_accounts_integration.py::test_group_a_effective_postgresql_privileges`.
- **Residual Risk**: In local developer environments running under the default `postgres` role, column-level restrictions are enforced in integration test fixtures.
- **Status**: **Mitigated**.

---

### THR-13: SQL Injection via Dynamic Query Construction
- **Threat Description**: An attacker inputs malicious SQL fragments (`' OR 1=1 --`) in usernames, search queries, or transfer descriptions to manipulate queries.
- **Potential Impact**: Unauthorized data exfiltration, authentication bypass, or arbitrary database execution.
- **Existing Mitigation**:
  - All database queries strictly use SQLAlchemy 2.x ORM or parameterized Core statements (`text("... WHERE account_id = :id").params(id=val)`).
  - Zero dynamic string interpolation (`f"SELECT ... {input}"`) or unescaped string concatenation anywhere in the codebase.
  - Strict Pydantic v2 schemas reject unexpected fields with `ConfigDict(extra="forbid")`.
  - Verified across the entire test suite (176 tests).
- **Residual Risk**: Negligible when parameterized ORM queries are consistently maintained.
- **Status**: **Mitigated**.

---

### THR-14: CSV Spreadsheet Formula Injection (CWE-1236)
- **Threat Description**: An attacker enters formula payloads (e.g. `=cmd|' /C calc'!A0` or `-2+3+cmd|...`) into transfer descriptions. When an administrator or accountant downloads the account statement CSV and opens it in Microsoft Excel or LibreOffice Calc, the spreadsheet executes the payload.
- **Potential Impact**: Remote code execution (RCE) on staff workstations, unauthorized local process launch, or silent data exfiltration.
- **Existing Mitigation**:
  - Implemented in `backend/app/services/statement.py` (`_sanitize_csv_cell`).
  - All text cells starting with formula trigger characters (`=`, `+`, `-`, `@`, `\t`, `\r`) are sanitized by prepending a single quote (`'`), which forces spreadsheet applications to treat the cell strictly as literal text.
  - Frontend prepends the UTF-8 Byte Order Mark (`0xEF, 0xBB, 0xBF`) to ensure clean rendering of Unicode characters like the Indian Rupee symbol (`₹`) without mojibake.
  - Verified in `backend/tests/integration/test_statements_integration.py::test_group_e_csv_export_and_formula_injection_sanitization` and verified on real downloaded files.
- **Residual Risk**: Prepending a single quote causes the literal quote to be visible in raw text viewers; this is standard safe practice for spreadsheet protection.
- **Status**: **Mitigated**.

---

### THR-15: Environment Secrets & Credential Exposure
- **Threat Description**: Production secrets (JWT signing keys, database passwords, API credentials) are hardcoded in source files, committed to Git repositories, or leaked into frontend production client bundles.
- **Potential Impact**: Complete compromise of token verification, unauthorized database access, and permanent loss of confidentiality.
- **Existing Mitigation**:
  - Implemented via `backend/app/core/config.py` using `pydantic-settings`.
  - Strict validation: Backend startup fails immediately if `SECRET_KEY` or `DATABASE_URL` is missing or uses insecure default values.
  - Repository protection: `.env` is explicitly ignored in `.gitignore`. Only `.env.example` with non-secret placeholder variables is tracked.
  - Frontend production build check: Dev quick-fill credentials are gated behind `import.meta.env.DEV ? ... : null`. Tree-shaking strips development credentials completely from production bundles (`dist/assets/*.js`).
  - Automated string scan verified zero plaintext credentials in production assets.
- **Residual Risk**: Developer workstation `.env` files must be safeguarded out-of-band.
- **Status**: **Mitigated**.

---

### THR-16: Test Database Contamination / Production Data Loss
- **Threat Description**: Automated test suites executing test fixtures (which drop, recreate, or truncate tables) run against the active demonstration database (`ledgerline`), destroying demo accounts and transaction records.
- **Potential Impact**: Loss of demo data, corrupted evaluation state, and irrecoverable historical records.
- **Existing Mitigation**:
  - Implemented in `backend/tests/conftest.py`.
  - Fail-closed database guard: Before any database connection is created or any test fixture executes, `conftest.py` inspects the target database name.
  - If the database name does NOT end with `_test` (e.g. `ledgerline_test`), the test runner unconditionally raises a fatal `RuntimeError`:
    ```python
    if not db_name.endswith("_test"):
        raise RuntimeError(f"SAFETY ABORT: Tests must run against a database ending with '_test', got '{db_name}'.")
    ```
  - Demo database `ledgerline` is completely isolated from all automated test runs.
  - Verified during 176-test suite execution; `ledgerline` database remains untouched with all demo accounts intact.
- **Residual Risk**: Manual scripts executed outside pytest must specify their target database responsibly.
- **Status**: **Mitigated**.

---

## 3. Residual Risk & Future Enhancements

| Area | Current Residual Risk | Recommended Future Production Enhancement |
| :--- | :--- | :--- |
| **External Audit Notarization** | Hash chain is tamper-evident within PostgreSQL, but a root DBA could recalculate hashes. | Anchor chain head periodically to RFC 3161 trusted timestamp authority, AWS S3 Object Lock, or public distributed ledger. |
| **Distributed Rate Limiting** | Rate limiting is held in server memory; restarts reset sliding counters. | Deploy distributed Redis cluster with atomic Lua token-bucket scripts. |
| **Transport Layer Security** | Local development runs over plain HTTP (`http://127.0.0.1:8000`). | Terminate TLS 1.3 via reverse proxy (Nginx / Caddy / Cloudflare) with HSTS headers. |
| **Account KYC & Verification** | Self-registered Account Holders are activated immediately. | Integrate regulatory identity verification APIs (DigiLocker / Aadhaar e-KYC / PAN verification). |
