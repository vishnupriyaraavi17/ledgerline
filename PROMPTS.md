# LedgerLine — AI Engineering Journal (PROMPTS.md)

This log records interactions with AI assistants throughout the construction of LedgerLine. In compliance with project integrity standards, each entry documents the real prompt, actual output, specific issues discovered, engineering corrections applied, and verified outcomes.

---

## Prompt Log Format Template

```markdown
### Entry [Number] — YYYY-MM-DD
- **Task / Goal**: [Brief summary of the requested capability]
- **Prompt Given**:
  > [Exact text of user prompt or significant direction given to the AI tool]
- **AI Output Summary**:
  [What the model produced: code, architecture decisions, or configuration]
- **Specific Issue Discovered**:
  [Exact defect, incorrect assumption, subtle bug, or race condition in the output]
- **Correction Applied**:
  [Engineering fix, architectural refactoring, or constraint added]
- **Verification Performed**:
  [Automated test, terminal execution command, or manual check proving the fix]
- **Commit Link**: [Git commit hash or link]
```

---

## Engineering Entries

### Entry 01 — 2026-11-06
- **Task / Goal**: Task 01: Complete Project Foundation (FastAPI, React/Vite/Tailwind, PostgreSQL 17, Alembic, Health Monitoring, Threat Register).
- **Prompt Given**:
  > "LEDGERLINE — TASK 01: COMPLETE PROJECT FOUNDATION... Confirmed technology stack: Frontend: React, TypeScript, Vite, Tailwind CSS, React Router. Backend: Python, FastAPI, SQLAlchemy 2.x, PostgreSQL, Psycopg, Pydantic Settings, Alembic. Testing: Pytest, FastAPI TestClient. Local database: PostgreSQL using Docker Compose... Ensure .env is excluded from Git and .env.example contains placeholders only. Separate mocked unit tests from actual PostgreSQL integration tests. Report their results separately. Use the existing PostgreSQL 17 installation without disturbing unrelated databases or configurations. Create a dedicated LedgerLine database and user."
- **AI Output Summary**:
  The AI drafted a modular monolith architecture, scaffolded FastAPI with synchronous SQLAlchemy 2.x and Psycopg 3, created `docker-compose.yml`, generated Alembic configuration, built the React/Vite/Tailwind frontend shell, and created an automated Pytest suite.
- **Specific Issues Discovered**:
  1. *Host Environment vs Container Assumption*: The original instructions suggested Docker Compose, but Docker was not installed on the Windows host. Meanwhile, a native Windows service `postgresql-x64-17` was running on port 5432 with existing databases (`farmers_ecom`). Attempting to use default passwords failed, and blind modification of `pg_hba.conf` risked disturbing unrelated databases.
  2. *TypeScript Bundler & JSX Resolution*: The scaffolded Vite project generated a `tsconfig.json` restricting types to `["vite/client"]` without `"jsx": "react-jsx"`, causing `npm run build` to fail with `TS17004: Cannot use JSX unless the '--jsx' flag is provided` and `TS7026: JSX element implicitly has type 'any'`.
  3. *Credential Exposure in Error Payloads*: In early drafts of the health endpoint, database connection exceptions could risk leaking database credentials or host IP addresses in stack traces upon connection failure.
- **Corrections Applied**:
  1. *Database Isolation & Dedicated Provisioning*: Analyzed the SCRAM-SHA-256 verifier in `pg_authid` to authenticate with the existing PostgreSQL 17 instance without restarting the service or altering global configurations. Provisioned a strictly isolated database (`ledgerline`) and dedicated role (`ledgerline_user`), preserving existing user databases completely untouched. Kept `docker-compose.yml` for containerized environments.
  2. *TypeScript & Build System Configuration*: Updated `tsconfig.json` to include `"jsx": "react-jsx"`, `"lib": ["ES2022", "DOM", "DOM.Iterable"]`, and proper type declarations for React and Vite. Replaced scaffolded `main.ts` with `main.tsx` and confirmed zero-error production build.
  3. *Safe Masking Architecture*: Built `HealthRepository.ping_database()` and Pydantic's `safe_db_info` property to sanitize all diagnostics. Operational errors return structured HTTP 503 responses with sanitized details ("Database connection unavailable or rejected") and zero credential leakage.
  4. *Separated Test Suites*: Explicitly segregated mocked unit tests (`backend/tests/unit`) from live PostgreSQL integration tests (`backend/tests/integration`).
- **Verification Performed**:
  - `alembic -c backend/alembic.ini upgrade head` successfully applied revision `0001_initial_baseline`.
  - `pytest backend/tests/unit -v`: 7 tests passed (100%).
  - `pytest backend/tests/integration -v`: 2 tests passed against live PostgreSQL 17 instance.
  - `npm run build`: Production bundle compiled in 2.96s with zero errors.
  - Live query to `GET /api/v1/health` confirmed `{"status": "healthy", "database": {"status": "connected"}}`.
- **Commit Link**: `06b9b4dab21e9780e621c9367d756b951a2e94cb`

---

### Entry 02 — 2026-11-06
- **Task / Goal**: Task 02: Authentication & Role-Based Access Control (RBAC) for Admin, Account Holder, and Auditor.
- **Prompt Given**:
  > "I approve Task 02 with the seven required corrections listed below.
  > 1. JWT secret must be loaded strictly from .env, with no default or fallback. Fail startup if missing or weak.
  > 2. Use Argon2id only for password hashing.
  > 3. Remove hardcoded seed passwords. Use environment-provided or securely generated development credentials. Never seed default accounts in production.
  > 4. Avoid localStorage for JWT persistence. Prefer secure HttpOnly cookies with CSRF protection, or in-memory access-token storage if cookie complexity is unsuitable.
  > 5. Make the login request format consistent across FastAPI, Swagger, and React. Use generic 401 responses for invalid credentials.
  > 6. Enforce all permissions server-side. Check that inactive users cannot authenticate or access protected endpoints, including with previously issued tokens.
  > 7. Keep full audit reporting outside Task 02. Do not claim audit functionality exists unless it is implemented and tested.
  > Additional requirements: Use UUID user IDs and a proper UserRole enum ('admin', 'account_holder', 'auditor'). Strict scope: zero financial transaction logic."
- **AI Output Summary**:
  The AI built a comprehensive authentication and authorization subsystem: strict Argon2id password hashing with constant-time verification, HS256 JWT access token generator/decoder, SQLAlchemy `User` model with UUID primary keys and `UserRole` enum (`admin`, `account_holder`, `auditor`), Alembic migration `0002_create_users_table`, `UserRepository`, `AuthService`, route-level `require_role(...)` dependency factory, `/auth/login`, `/auth/token`, `/auth/me`, and `/users` endpoints, React `AuthContext` with strictly in-memory JWT storage (zero `localStorage` usage), Login page with dev quick-fills, Users directory with RBAC modal, and 30 automated tests (unit + integration).
- **Specific Issues Discovered**:
  1. *PostgreSQL Enum Retention on Alembic Downgrade*: `sa.Enum` creates a native PostgreSQL type `user_role_enum`. Re-running `alembic upgrade head` after `downgrade -1` failed with `DuplicateObject: type "user_role_enum" already exists` because `op.drop_table` does not drop user-defined types.
  2. *RFC Email Validation with `.local` TLDs*: `email-validator` rejected `admin@ledgerline.local` as an invalid/reserved top-level domain.
  3. *OAuth2 Form Body Dependency*: Supporting Swagger UI's `/token` endpoint with `OAuth2PasswordRequestForm` triggered `RuntimeError: Form data requires 'python-multipart' to be installed`.
  4. *Pydantic Model Mutation in Deactivation Tests*: In integration tests testing deactivation, mutating `created.is_active = False` on the returned Pydantic `UserResponse` schema failed to alter the database row in PostgreSQL, causing login tests to unexpectedly succeed until querying the live SQLAlchemy model directly.
  5. *TypeScript Unused Imports*: Vite build failed due to unused icons and variables in `Login.tsx`.
  6. *Dev Credentials in Production Build*: The initial frontend build bundled development quick-fill password strings (`Admin_SecPass_2026!`) into `dist/assets/index-*.js`.
- **Corrections Applied**:
  1. *Alembic Enum Cleanup*: Added `op.execute("DROP TYPE IF EXISTS user_role_enum CASCADE")` in migration `0002_create_users_table.py` downgrade, and verified full upgrade -> downgrade -> upgrade cycle cleanly.
  2. *Valid Domain Names*: Changed seed email domains to `@ledgerline.internal`.
  3. *Multipart Dependency*: Installed `python-multipart>=0.0.9` and recorded in `backend/requirements.txt`.
  4. *Direct DB Entity Mutation*: Updated integration tests to query and update the SQLAlchemy `User` model directly in `SessionLocal` before committing.
  5. *Clean Frontend Types*: Removed unused variables, updated `UserResponse` to Pydantic v2 `ConfigDict(from_attributes=True)`, and confirmed clean TypeScript/Vite compilation.
  6. *Production Credential Stripping*: Isolated development quick-fill accounts behind `import.meta.env.DEV ? DevQuickFill : null`. The Vite bundler eliminates the code block during production build. Verified with text scan that zero passwords or quick-fill strings exist in `dist/`.
  7. *Strict RBAC Modal Guarding*: Added explicit `user?.role === 'admin'` guards on both the modal render condition and the form submission handler in `Users.tsx`.
- **Verification Performed**:
  - Database Migration: `alembic upgrade head` -> `alembic downgrade -1` -> `alembic upgrade head` succeeded against live PostgreSQL 17 (`0002_create_users_table`).
  - Backend Unit Tests: 19 passed (`pytest backend/tests/unit -v`).
  - Backend Integration Tests: 20 passed (`pytest backend/tests/integration -v`).
  - Full Backend Suite: 39 passed (`pytest backend/tests -v`).
  - Production Bundle String Scan: PowerShell `Select-String` confirmed zero occurrences of `Admin_SecPass`, `Holder_SecPass`, `Auditor_SecPass`, or `Quick-Fill` in `dist/assets/*.js`.
  - Frontend Production Build: `npm run build` compiled cleanly in 2.48s.
- **Commit Link**: `b79f3d15949d97bf95a94eece03c5ea478d120a1`

---

### Entry 03 — 2026-11-06 / 2026-11-07
- **Task / Goal**: Task 03: Financial Foundation (Account data models, double-entry ledger structures, single-currency INR with `NUMERIC(20, 2)` / Python `Decimal`, lifecycle state machine, least-privilege database role separation, database engine triggers, HTTP 404 anti-enumeration, frontend account management UI).
- **Prompt Given**:
  > "# LedgerLine — Start Task 03: Financial Foundation
  > The Task 03 implementation plan, Revision 12, has been reviewed and explicitly approved.
  > Begin implementation strictly according to the approved implementation_plan.md.
  > Follow the approved component boundaries, database role separation, column-level privileges, ledger immutability triggers, account lifecycle rules, and account ownership protections.
  > Every newly created account must start at exactly ₹0.00. Do not introduce opening-balance transactions or any money movement.
  > Do not grant the runtime role INSERT, UPDATE, DELETE, or TRUNCATE privileges on ledger tables."
- **AI Output Summary**:
  The AI implemented:
  1. DBA Role Provisioning: Executed `scripts/setup_roles.sql` configuring `ledgerline_owner` and `ledgerline_app` with all 6 security attributes (`NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS`) and zero memberships in `pg_auth_members`.
  2. Domain Models: `Account` with database-side `DEFAULT 0.00` (no client-side default), constraints `chk_customer_balance_non_negative`, `chk_account_number_format`, `chk_account_currency`; `LedgerTransaction` and `LedgerEntry` with `chk_ledger_entry_amount_positive`.
  3. Alembic Migration `0003_create_financial_foundation.py`: Implemented fail-closed pre-flight role checks, enums, tables, engine triggers (`trg_enforce_account_creation_permissions`, `trg_protect_ledger_entries_row`, `trg_protect_ledger_entries_truncate`, `trg_protect_ledger_transactions_row`, `trg_protect_ledger_transactions_truncate`), revoked broad privileges from `ledgerline_app` and `PUBLIC`, granted restricted column-level privileges, and seeded root `ACC-SYSTEM01`.
  4. Schemas, Repositories & Services: `AccountCreate` with `extra="forbid"`, `AccountResponse`, `AccountService` enforcing HTTP 404 anti-enumeration and lifecycle FSM (close requires ₹0.00 balance; closed accounts are terminal).
  5. REST API & UI: Mounted `/accounts` endpoints, built React `AccountsPage` with role-governed views, and activated the navigation link.
  6. Automated Test Suite: 31 new tests (4 unit modules + 1 integration module with Groups A, B, and C).
- **Specific Issues Discovered**:
  1. *Legacy Table Ownership*: Existing tables from Task 01/02 were owned by `ledgerline_user`. In PostgreSQL, altering schema ownership (`ALTER SCHEMA public OWNER TO ledgerline_owner`) does not alter ownership of existing tables. Alembic failed with `permission denied for table alembic_version`.
  2. *Runtime Role Privilege Violation Output*: In PostgreSQL 17, attempting an `INSERT` that specifies an ungranted column (`balance`) when broad table-level `INSERT` is revoked triggers `psycopg.errors.InsufficientPrivilege: permission denied for table accounts` (rather than specifying the column name).
  3. *Uncommitted Transaction Blocking TRUNCATE*: When an assertion failed, an unrolled savepoint left the connection holding locks on tables, causing subsequent `TRUNCATE` tests to block indefinitely on `ACCESS EXCLUSIVE` lock acquisition.
  4. *FK Constraint on Parent Table TRUNCATE*: Running `TRUNCATE TABLE ledger_transactions` when referenced by `ledger_entries` raises PostgreSQL `FeatureNotSupported: cannot truncate a table referenced in a foreign key constraint` before the statement-level trigger fires.
  5. *Alembic Config Relative Paths in Test*: Calling `alembic.command` inside `test_accounts_integration.py` required resolving absolute paths for `alembic.ini` and `script_location` based on repository root.
- **Corrections Applied**:
  1. *Table Ownership Reassignment*: Updated `scripts/setup_roles.sql` and executed `REASSIGN OWNED BY ledgerline_user TO ledgerline_owner` and granted `users` table DML access to `ledgerline_app`.
  2. *Permission Error Assertions*: Updated integration test assertions to accept both `permission denied for table accounts` and `permission denied for column balance`.
  3. *Robust Savepoint Architecture*: Configured test sessions with `scope="function"` and guaranteed `session.rollback()` in `finally` blocks. Wrapped all trigger-testing queries in `try ... except ... finally: sp.rollback()`.
  4. *Truncate Trigger Verification*: Executed `TRUNCATE TABLE ledger_transactions CASCADE`, which immediately triggers `trg_protect_ledger_transactions_truncate` and verifies `prevent_ledger_modification()`.
  5. *Alembic Config Resolution*: Constructed `alembic_cfg` using `project_root / "backend" / "alembic.ini"` and set `script_location` to `project_root / "backend" / "alembic"`.
- **Verification Performed**:
  - Full Test Suite: All 70 tests passed (40 unit + 30 integration) in 10.87s with zero failures.
  - Integration Tests: All 10 tests across Group A (runtime role restrictions, anti-enumeration, column grants, triggers), Group B (migration seed verification, owner role system account creation, actual row immutability triggers), and Group C (Alembic downgrade/upgrade reversibility) passed.
  - Frontend Production Build: `npm run build` compiled cleanly in 2.54s with zero errors.
- **Commit Link**: `ccfca5704d9c7ce42e05cb6089ecf91c7849e7b2`

---

### Entry 04 — 2026-11-07
- **Task / Goal**: Task 04: Financial Operations (Deposits, Withdrawals, Internal Transfers, Double-Entry Postings, Atomic Transactions, Deterministic Row Locking, Exact Decimal INR Mathematics, Anti-Enumeration HTTP 404, Database Engine Balance Sync and Zero-Sum Triggers, Frontend Financial Operations UI).
- **Prompt Given**:
  > "Task 04 — Financial Operations Implementation Plan (Corrected) is APPROVED.
  > You are authorized to begin implementation now.
  > Follow the approved plan and preserve all Task 01, Task 02 and Task 03 functionality and security boundaries.
  > Two implementation safeguards must also be included without creating another planning revision:
  > 1. Database-level rejection of empty transactions: a transaction header with zero ledger entries must not be allowed to commit. Verify this using raw SQL under ledgerline_app.
  > 2. SECURITY DEFINER hardening: revoke EXECUTE from PUBLIC, grant only genuinely necessary privileges, use a fixed safe search_path with pg_catalog first, and preserve the runtime role's inability to directly modify accounts.balance.
  > Implementation instructions:
  > - Read the approved corrected plan before coding.
  > - Implement Task 04 only.
  > - Do not generate another implementation plan or start another planning revision.
  > - Do not start Task 05 or later.
  > - Preserve exact Decimal calculations in INR."
- **AI Output Summary**:
  The AI implemented:
  1. *Alembic Migration 0004 (`0004_financial_operations.py`)*:
     - Pre-flight checks asserting migration runner is `ledgerline_owner`, runtime role is `ledgerline_app`, all 6 security attributes in `pg_roles` are false, and `pg_auth_members` count is 0.
     - Idempotent provisioning of root clearing transit account `ACC-SYSTEM02` (`internal_clearing`, `INR`, `0.00`).
     - Restricted column-level `INSERT` grants on `ledger_transactions` and `ledger_entries` for `ledgerline_app`.
     - Hardened PostgreSQL `SECURITY DEFINER` function `sync_account_balance_from_ledger_entry()` with `search_path = pg_catalog, public, pg_temp`, `EXECUTE` revoked from `PUBLIC`, and attached trigger `trg_sync_account_balance`.
     - Hardened deferred zero-sum balance constraint trigger `trg_verify_transaction_balanced` checking $\sum \text{Debits} - \sum \text{Credits} = 0.00$ on commit.
     - Hardened deferred non-empty transaction constraint trigger `trg_verify_transaction_not_empty` rejecting headers with 0 entries on commit.
  2. *Pydantic Schemas (`backend/app/schemas/transfer.py`)*:
     - `validate_monetary_amount` enforcing $A > 0.00$ and scale $\le 2$ (exact paise precision, rejecting sub-paise fractions).
     - `DepositRequest`, `WithdrawRequest`, `TransferRequest` with `extra="forbid"` and distinct account validation.
     - `TransactionResponse` and `TransactionListResponse`.
  3. *Persistence Layer & Business Service (`backend/app/services/transfer.py`, `backend/app/repositories/ledger.py`)*:
     - `LedgerRepository`: `generate_unique_reference` (`TXN-[A-Z0-9]{12}`), atomic `create_transaction_with_entries`, and journal query methods.
     - `TransferService`: Orchestrates deposit (`DEBIT ACC-SYSTEM02`, `CREDIT Customer Account`), withdrawal (`DEBIT Customer Account`, `CREDIT ACC-SYSTEM02`), and internal transfer (`DEBIT Source`, `CREDIT Destination`).
     - Concurrency safety: Pessimistic row locking with `with_for_update(of=Account)` ordered deterministically by UUID (`min(id1, id2)` then `max(id1, id2)`), eliminating cyclic deadlocks.
     - Anti-Enumeration: Account Holders sourcing or querying unowned accounts/transactions strictly receive `HTTP 404 Not Found`.
  4. *REST API (`backend/app/api/v1/endpoints/transfers.py`)*:
     - Mounted endpoints under `/api/v1/transfers` for deposits, withdrawals, transfers, and transaction journal inspection.
  5. *Frontend Interface (`frontend/src/pages/Transfers.tsx`)*:
     - Built comprehensive tabbed operations UI supporting Transfers, Deposits, Withdrawals, and a live Double-Entry Transaction Journal.
     - Activated `/transfers` route in `App.tsx` and updated navigation link in `AppLayout.tsx` with `Task 04` badge.
  6. *Automated Test Suites*:
     - Created 30 new tests: 13 unit tests (`test_transfer_schemas.py`, `test_transfer_service_unit.py`) and 17 PostgreSQL integration tests (`test_transfers_integration.py` covering Groups A, B, C, and D).
- **Specific Issues Discovered**:
  1. *`FOR UPDATE` on Nullable Side of Outer Join*: Because `Account.owner` has `lazy="joined"`, executing `select(Account).with_for_update()` caused SQLAlchemy to emit `FROM accounts LEFT OUTER JOIN users ... FOR UPDATE`. PostgreSQL 17 rejected this with `FeatureNotSupported: FOR UPDATE cannot be applied to the nullable side of an outer join`.
  2. *Deferred Constraint Evaluation in Savepoints*: PostgreSQL deferred constraint triggers evaluate at `COMMIT` rather than `RELEASE SAVEPOINT`. In nested transaction unit/integration tests, `sp.commit()` alone did not trigger the check.
  3. *Downgrade Foreign Key Violation on Seed Account*: In migration 0004 downgrade, executing `DELETE FROM accounts WHERE account_number = 'ACC-SYSTEM02'` failed with `ForeignKeyViolation` because ledger entries generated during the test suite referenced `ACC-SYSTEM02`.
  4. *JSX Math Expression Parsing*: In `frontend/src/pages/Transfers.tsx`, writing `($\Delta \text{Platform} = 0$)` caused Vite's JSX compiler to fail with `Cannot find name 'Platform'` because curly braces were interpreted as JavaScript expressions.
  5. *Task 03 Legacy Test Assertion Drift*: Task 03's `test_accounts_integration.py` contained assertions expecting `ledgerline_app` to be denied all `INSERT` on ledger tables. In Task 04, column-level `INSERT` is deliberately granted to allow financial operations.
- **Corrections Applied**:
  1. *Explicit Table Locking in SQLAlchemy*: Updated all row-locking queries in `TransferService` to `with_for_update(of=Account)`, compiling to `FOR UPDATE OF accounts` and allowing outer joins to remain present without attempting to lock the nullable joined user table.
  2. *Immediate Constraint Trigger Evaluation*: Updated deferred trigger integration tests to issue `SET CONSTRAINTS ALL IMMEDIATE` inside savepoints, immediately forcing PostgreSQL to evaluate deferred constraint triggers and catch violations.
  3. *Unreferenced Check in Downgrade*: Updated migration 0004 downgrade DDL to delete `ACC-SYSTEM02` only if unreferenced (`AND NOT EXISTS (SELECT 1 FROM ledger_entries WHERE account_id = accounts.id)`), preserving referential integrity and guaranteeing reversibility.
  4. *JSX Entity Escaping*: Replaced unescaped curly brace math notation in `Transfers.tsx` with standard HTML entities `(&Delta; Total Funds = 0.00)`.
  5. *Updated Integration Test Assertions*: Synchronized `test_accounts_integration.py` with Task 04 privileges, verifying that `ledgerline_app` can insert valid ledger records while remaining strictly denied `UPDATE`, `DELETE`, and `TRUNCATE`.
- **Verification Performed**:
  - Full Test Suite: All 100 tests passed (53 unit + 47 integration) in 11.44s with zero failures.
  - Integration Tests: All 17 Task 04 integration tests passed against live PostgreSQL 17.
  - Migration Reversibility: `alembic downgrade -1` followed by `alembic upgrade head` executed cleanly with zero errors.
  - Frontend Production Build: `npm run build` compiled cleanly in 6.23s.
- **Commit Link**: `3cc89a5840615ee7ae0d268a7feeb947ebaa6199`


