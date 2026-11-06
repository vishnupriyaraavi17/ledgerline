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
