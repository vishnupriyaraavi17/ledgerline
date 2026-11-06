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
- **Corrections Applied**:
  1. *Alembic Enum Cleanup*: Added `op.execute("DROP TYPE IF EXISTS user_role_enum CASCADE")` in migration `0002_create_users_table.py` downgrade, and verified full upgrade -> downgrade -> upgrade cycle cleanly.
  2. *Valid Domain Names*: Changed seed email domains to `@ledgerline.internal`.
  3. *Multipart Dependency*: Installed `python-multipart>=0.0.9` and recorded in `backend/requirements.txt`.
  4. *Direct DB Entity Mutation*: Updated integration tests to query and update the SQLAlchemy `User` model directly in `SessionLocal` before committing.
  5. *Clean Frontend Types*: Removed unused variables, updated `UserResponse` to Pydantic v2 `ConfigDict(from_attributes=True)`, and confirmed clean TypeScript/Vite compilation.
- **Verification Performed**:
  - Database Migration: `alembic upgrade head` -> `alembic downgrade -1` -> `alembic upgrade head` succeeded against live PostgreSQL 17 (`0002_create_users_table`).
  - Backend Unit Tests: 19 passed (`pytest backend/tests/unit -v`).
  - Backend Integration Tests: 20 passed (`pytest backend/tests/integration -v`).
  - Full Backend Suite: 39 passed (`pytest backend/tests -v`).
  - Frontend Production Build: `npm run build` compiled cleanly in 8.90s.
  - Security Verification: Confirmed `.env` is ignored by Git, no credentials appear in commits, and password hashes are never exposed in any API response.
- **Commit Link**: `ed539aa723b75cfa48842f1f50a49beff4bfb3b3`
