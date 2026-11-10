# LedgerLine — Money Movement with a Ledger You Can Prove

> **Snovasys Fresher Hiring Challenge 2026**
> **Demonstration Notice**: LedgerLine is an educational banking prototype operating strictly with simulated/virtual balances and internal accounts. It does not connect to external payment clearing rails (RTGS/NEFT/IMPS/UPI/SWIFT) and does not process real-world monetary settlements.

LedgerLine is a modern digital banking platform built on an immutable, double-entry financial core. It guarantees mathematical conservation of funds ($\sum \Delta = 0$), eliminates race conditions and double-spending via deterministic pessimistic locking, provides idempotent replay transparency, and records every security and financial operation into a cryptographically verifiable SHA-256 recursive hash chain.

---

## 1. System Features & Highlights

### Modern Fintech Experience
- **Restrained Banking Palette**: Deep forest green (`#102F28`), warm cream (`#F6F7F4`), subtle borders (`#E8EBE6`), and serif headings.
- **Role-Tailored Dashboards**:
  - **Account Holder**: Aggregated customer net worth, quick-action account tiles, transfers, statements, and transaction history.
  - **Admin**: System-wide customer deposit totals, customer count, system liquidity metrics, and user management.
  - **Auditor**: Read-only oversight, cryptographic audit trail explorer, and interactive live hash-chain verifier.
- **Customer-Friendly Language**: Clean banking terminology ("Send Money", "Account Statement", "Declined Attempts") free of developer-facing jargon.

### Financial Core & Accounting Invariants
- **Conserved Double-Entry Accounting**: Every financial operation (Deposit, Withdrawal, Transfer) creates equal and opposite debit and credit entries inside an atomic ACID transaction.
- **Deterministic Pessimistic Row Locking**: Accounts locked via `SELECT ... FOR UPDATE` ordered deterministically by UUID (`min(id_a, id_b)` then `max(id_a, id_b)`) to eliminate cyclic deadlocks.
- **Strict Non-Negative Balance Enforcement**: In-flight balance sufficiency pre-checks backed by database-level check constraint `chk_customer_balance_non_negative`.
- **Single Currency Monetary Precision**: `Decimal(20, 2)` arithmetic strictly anchored to Indian Rupee (`INR`).

### Idempotency & Replay Protection
- **Mandatory Idempotency Keys**: All financial write endpoints require an `Idempotency-Key` header (8–128 characters).
- **Deterministic SHA-256 Fingerprinting**: Request method, path, and sorted payload parameters are hashed; payload tampering under an existing key returns `HTTP 409 Conflict`.
- **Atomic Deduplication**: Pessimistic row locking on `idempotency_records` deduplicates concurrent requests; replays return the cached response with an `Idempotent-Replay: true` header.

### Cryptographic Audit Trail
- **Recursive SHA-256 Hash Chain**: Every security and financial event is bound to a linear hash chain:
  $$H_n = \text{SHA-256}(\text{CanonicalJSON}(E_n, H_{n-1})) \quad \text{with} \quad H_0 = 0^{64}$$
- **SECURITY DEFINER Gatekeeper**: Direct inserts or updates to audit tables are revoked from the runtime application role; appends are strictly mediated by `append_audit_event()`.
- **Database Immutability Triggers**: Row-level and statement-level triggers unconditionally reject any `UPDATE`, `DELETE`, or `TRUNCATE` on ledger and audit rows.
- **Streaming Verification Service**: Detects hash mismatches, broken chains, sequence gaps, or head desynchronization.

### Account Statements & Reporting
- **Derived Balances**: Statements dynamically compute opening balance, credits, debits, net change, and closing balance from immutable ledger entries.
- **Snapshot Isolation**: Generated under `REPEATABLE READ READ ONLY` transaction isolation.
- **Refused Operations History**: Declined attempts (insufficient funds, frozen/closed accounts, idempotency conflicts) are recorded in an isolated table without contaminating ledger books.
- **RFC 4180 CSV Export**: Neutralizes spreadsheet formula injection (CWE-1236) and prepends UTF-8 Byte Order Mark (`0xEF, 0xBB, 0xBF`) for correct display of the ₹ symbol.
- **Print Optimization**: A4 landscape print preview hiding navigation chrome, buttons, and pagination controls.

### Security & Public Registration
- **Argon2id Password Hashing**: Memory cost 64 MB, 3 iterations, 4 parallel threads.
- **Stateless JWTs with Immediate Revocation**: Every authenticated request verifies active user status in the database.
- **Secure Public Self-Registration**: Public registration endpoint strictly forces `role = ACCOUNT_HOLDER`.
- **Registration Rate Limiting**: In-memory sliding-window limiter enforcing 5 registrations/hour per IP and 3 attempts/hour per username/email with HTTP 429 responses.

---

## 2. Technology Stack

### Backend
- **Language / Runtime**: Python 3.11+
- **Framework**: FastAPI
- **Database ORM & Driver**: SQLAlchemy 2.x with Psycopg 3 (synchronous driver)
- **Settings & Validation**: Pydantic v2 & Pydantic Settings
- **Password Hashing**: Argon2id via `passlib[argon2]` and `argon2-cffi`
- **Authentication**: JWT (`python-jose` with HS256)
- **Database Migrations**: Alembic (7 versioned migrations)
- **Testing**: Pytest, FastAPI TestClient (HTTPX)

### Frontend
- **Framework**: React 19 + TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS (Custom Fintech Palette)
- **Routing**: React Router v7
- **HTTP Client**: Axios (In-memory token management, zero localStorage token storage)
- **Icons**: Lucide React

### Database
- **Engine**: PostgreSQL 17
- **Containerization**: Docker Compose (`docker-compose.yml`)

---

## 3. Project Structure

```text
ledgerline/
├── .env.example              # Canonical environment configuration template
├── .env                      # Local environment secrets (gitignored)
├── .gitignore                # Git exclusions (credentials, node_modules, .venv, caches)
├── docker-compose.yml        # PostgreSQL 17 container service
├── pytest.ini                # Pytest configuration and warning filters
├── README.md                 # Complete project documentation and guide
├── THREATS.md                # 16-threat security architecture and mitigations register
├── PROMPTS.md                # Dated prompts journal tracking AI collaboration
│
├── backend/                  # FastAPI Backend
│   ├── alembic.ini           # Alembic migration configuration
│   ├── requirements.txt      # Pinned Python dependencies
│   ├── alembic/              # DDL migrations (0001 through 0007)
│   ├── app/
│   │   ├── main.py           # FastAPI entrypoint, CORS & route mounting
│   │   ├── core/             # Pydantic Settings & security primitives
│   │   ├── db/               # Database engine, session, & demo reset scripts
│   │   ├── models/           # SQLAlchemy models (User, Account, Ledger, Audit, Refusal)
│   │   ├── schemas/          # Pydantic v2 validation schemas
│   │   ├── repositories/     # Data access layer & SQL queries
│   │   ├── services/         # Business domain services (Transfer, Statement, Audit, Auth)
│   │   ├── security/         # Registration rate limiter & token helpers
│   │   └── api/              # API v1 routes (/auth, /accounts, /transfers, /audit, /users)
│   └── tests/                # Automated verification suite (176 tests)
│       ├── conftest.py       # TestClient fixtures & fail-closed safety guard
│       ├── unit/             # Isolated unit tests
│       └── integration/      # PostgreSQL integration tests
│
└── frontend/                 # React + TypeScript + Vite Frontend
    ├── package.json          # Node dependencies and scripts
    ├── tsconfig.json         # TypeScript compiler configuration
    ├── vite.config.ts        # Vite configuration
    ├── tailwind.config.js    # Forest-green & warm-cream theme configuration
    └── src/
        ├── App.tsx           # React Router route registry
        ├── index.css         # Base styles & A4 landscape print media queries
        ├── context/          # React AuthContext (in-memory token storage)
        ├── layouts/          # AppLayout with role-based navigation header & footer
        ├── pages/            # Role dashboards (Dashboard, Accounts, Transfers, Statements, Audit, Users, Login)
        ├── services/         # Axios API client with interceptors
        └── types/            # TypeScript interfaces matching backend schemas
```

---

## 4. Local Installation & Setup

### Prerequisites
- Python 3.11 or higher
- Node.js 20 or higher & `npm`
- PostgreSQL 16 or 17 (local service or Docker)
- Git

### Step 1: Clone Repository & Configure Environment
```bash
git clone <repository_url> ledgerline
cd ledgerline

# Copy configuration template
cp .env.example .env
```

Review `.env` and verify database and authentication settings:
```ini
PROJECT_NAME="LedgerLine"
ENVIRONMENT="development"
DEBUG=true

BACKEND_HOST="127.0.0.1"
BACKEND_PORT=8000
BACKEND_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"

POSTGRES_SERVER="127.0.0.1"
POSTGRES_PORT=5432
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="your_password"
POSTGRES_DB="ledgerline"

# Minimum 32-character secret key for JWT signing
JWT_SECRET_KEY="your_super_secret_signing_key_at_least_32_characters_long"

# Seed credentials for initial demo users
SEED_ADMIN_PASSWORD="your_admin_seed_password"
SEED_HOLDER_PASSWORD="your_holder_seed_password"
SEED_AUDITOR_PASSWORD="your_auditor_seed_password"
```

### Step 2: Database Setup & Migrations
Ensure PostgreSQL is running on port 5432.

```bash
# Set up Python virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Run Alembic migrations to apply all 7 database revisions
alembic -c backend/alembic.ini upgrade head
```

### Step 3: Frontend Setup
```bash
cd frontend
npm install
cd ..
```

---

## 5. Running the Application

### Start the Backend
From the project root:
```bash
.\.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
- API Base URL: `http://127.0.0.1:8000`
- Interactive API Docs (Swagger): `http://127.0.0.1:8000/docs`
- Health Check: `http://127.0.0.1:8000/api/v1/health`

### Start the Frontend
In a second terminal:
```bash
cd frontend
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 6. Demo User Roles & Accounts Guide

The system includes three pre-configured role tiers. **Login credentials correspond to the seed passwords configured in your local `.env` file.**

| Role | Demo Username | Permitted Actions | Primary Use Case |
| :--- | :--- | :--- | :--- |
| **Account Holder** | `holder` | View personal accounts, deposit, withdraw, transfer between accounts, view statements, download CSV, print reports | Everyday customer banking workflows |
| **Admin** | `admin` | View all users, provision new Admin/Auditor users, view all accounts, update account status (Freeze/Close), view system liquidity | Operational and supervisory management |
| **Auditor** | `auditor` | Read-only access to all accounts, inspect immutable audit chain, trigger live cryptographic hash-chain verification | Regulatory compliance and independent oversight |

*Note: For self-registration, navigate to the Login page and click **"Open an account"** to register a new Account Holder account.*

---

## 7. Testing & Verification

The test suite contains **176 automated tests** with 100% pass rate:
- **Unit Tests**: Schema validation, decimal precision, canonical hash canonicalization, statement math, rate limiting.
- **Integration Tests**: Real PostgreSQL transactions, pessimistic row locking, concurrent transfer race conditions, idempotency deduplication, audit chain verification, account lifecycle FSM, and CSV export protection.

### Fail-Closed Safety Guard
All automated tests strictly connect to `ledgerline_test`. The test harness in `backend/tests/conftest.py` inspects the active database name and aborts immediately if pointed at the `ledgerline` demo database.

### Execute Test Suite
```bash
# Run full Pytest suite
.\.venv\Scripts\pytest backend/tests -v

# Run Frontend production build
npm --prefix frontend run build
```

---

## 8. Deployment Readiness

| Component | Target Platform | Build Command / Entrypoint | Key Environment Variables |
| :--- | :--- | :--- | :--- |
| **Frontend** | Vercel / Netlify / Cloudflare Pages | `npm run build` (Output: `dist`) | `VITE_API_URL=https://api.yourdomain.com/api/v1` |
| **Backend** | Render / Railway / Fly.io | `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT` | `DATABASE_URL`, `JWT_SECRET_KEY`, `BACKEND_CORS_ORIGINS` |
| **Database** | Managed PostgreSQL (Neon / Supabase / Render) | PostgreSQL 16 or 17 | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` |

*Note: CORS origins can be configured as a comma-separated list via `BACKEND_CORS_ORIGINS`.*

---

## 9. Security & Threat Register
For the complete 16-threat security architecture register, including attack scenarios, potential impact, implemented defenses, verification tests, and residual risk analysis, refer to [THREATS.md](file:///C:/Users/raavivishnupriya/OneDrive/ledgerline/THREATS.md).

For the step-by-step engineering prompt journal and design decisions, refer to [PROMPTS.md](file:///C:/Users/raavivishnupriya/OneDrive/ledgerline/PROMPTS.md).
