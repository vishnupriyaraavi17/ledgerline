# LedgerLine — Money Movement with a Ledger You Can Prove

LedgerLine is a secure, double-entry financial ledger and money movement system designed to guarantee mathematical conservation of funds, eliminate double spending under concurrent load, ensure idempotent replay safety, and provide an immutable, append-only audit trail.

---

## 1. Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **ORM & DBAPI**: SQLAlchemy 2.x with Psycopg (Psycopg 3 synchronous driver)
- **Settings & Validation**: Pydantic v2 & Pydantic Settings
- **Database Migrations**: Alembic
- **Testing**: Pytest, FastAPI TestClient (HTTPX)

### Frontend
- **Framework**: React 19 + TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS (Restrained Financial Palette)
- **Routing**: React Router v7
- **HTTP Client**: Axios
- **Icons**: Lucide React

### Database
- **Engine**: PostgreSQL 17
- **Containerization**: Docker Compose (`docker-compose.yml` with health checks & persistent volumes)
- **Local Native Support**: Configured to run against native local PostgreSQL 17 installations

---

## 2. Project Architecture (Modular Monolith)

```text
ledgerline/
├── .env.example              # Canonical environment template (placeholders only)
├── .env                      # Local development environment configuration (gitignored)
├── .gitignore                # Git exclusions (env files, node_modules, cache, venv)
├── docker-compose.yml        # PostgreSQL 17 container definition with health check
├── README.md                 # Project setup and operations manual
├── THREATS.md                # System threat matrix and security mitigations register
├── PROMPTS.md                # Dated prompts journal tracking AI collaboration
│
├── backend/                  # FastAPI Modular Backend
│   ├── requirements.txt      # Pinned Python dependencies
│   ├── alembic.ini           # Alembic database migration configuration
│   ├── alembic/              # Migration scripts and environment definitions
│   │   ├── env.py            # Dynamic connection loader from app settings
│   │   └── versions/         # Versioned DDL migrations (0001_initial_baseline.py)
│   ├── app/
│   │   ├── main.py           # FastAPI application entry point & CORS configuration
│   │   ├── core/             # Central configuration (Pydantic Settings & safe masking)
│   │   │   └── config.py
│   │   ├── db/               # Database engine, sessionmaker, and declarative base
│   │   │   ├── base.py
│   │   │   └── session.py
│   │   ├── models/           # Domain entity definitions
│   │   ├── schemas/          # Pydantic request/response validation schemas
│   │   │   └── health.py
│   │   ├── repositories/     # Data access layer & low-level SQL probes
│   │   │   └── health.py
│   │   ├── services/         # Business logic coordination & telemetry
│   │   │   └── health.py
│   │   ├── api/              # API versioning and route endpoints
│   │   │   └── v1/
│   │   │       ├── api.py
│   │   │       └── endpoints/
│   │   │           └── health.py
│   │   └── security/         # Authentication & authorization module boundary
│   └── tests/                # Automated verification suite
│       ├── conftest.py       # Reusable test fixtures and client setup
│       ├── unit/             # Isolated unit tests with mocks
│       │   ├── test_config.py
│       │   └── test_health_unit.py
│       └── integration/      # Live PostgreSQL integration tests
│           └── test_health_postgres_integration.py
│
└── frontend/                 # React + TypeScript + Vite Frontend
    ├── package.json          # Node dependencies and scripts
    ├── tsconfig.json         # TypeScript compiler configuration
    ├── vite.config.ts        # Vite configuration
    ├── tailwind.config.js    # Financial design system color palette
    ├── postcss.config.js     # PostCSS configuration
    ├── index.html            # Application entry HTML
    └── src/
        ├── main.tsx          # React application root render
        ├── App.tsx           # React Router route registry
        ├── index.css         # Tailwind base and utility styles
        ├── types/            # TypeScript domain interfaces
        │   └── health.ts
        ├── services/         # API HTTP communication client
        │   └── api.ts
        ├── hooks/            # Custom stateful hooks
        │   └── useHealth.ts
        ├── utils/            # Formatting and helper utilities
        │   └── formatters.ts
        ├── components/       # Reusable UI components
        │   └── HealthBadge.tsx
        ├── layouts/          # Application shell layout
        │   └── AppLayout.tsx
        └── pages/            # View pages
            └── Dashboard.tsx # Foundation telemetry dashboard
```

---

## 3. Prerequisites

Ensure the following tools are installed on your machine:
- **Python**: version 3.11 or later
- **Node.js**: version 20 or later (v22 tested) & `npm`
- **PostgreSQL**: version 16 or 17 (either locally installed or via Docker)
- **Git**: version 2.40+

---

## 4. Local Installation & Setup

### Step 1: Clone and Configure Environment

```bash
git clone <repository_url> ledgerline
cd ledgerline

# Copy configuration template
cp .env.example .env
```

Review `.env` and verify your local PostgreSQL connection credentials:
```ini
PROJECT_NAME="LedgerLine"
ENVIRONMENT="development"
DEBUG=true

API_V1_STR="/api/v1"
BACKEND_HOST="127.0.0.1"
BACKEND_PORT=8000

BACKEND_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"

POSTGRES_SERVER="127.0.0.1"
POSTGRES_PORT=5432
POSTGRES_USER="ledgerline_user"
POSTGRES_PASSWORD="ledgerline_secure_pass_2026"
POSTGRES_DB="ledgerline"

VITE_API_URL="http://127.0.0.1:8000/api/v1"
```

---

### Step 2: Database Provisioning

#### Option A: Using Docker Compose
If Docker is installed:
```bash
docker compose up -d
```
Docker Compose starts PostgreSQL 17 on port 5432 with health checks and persistent volume storage.

#### Option B: Using Existing Native PostgreSQL Installation
If using a native PostgreSQL installation:
```bash
# Connect to PostgreSQL as superuser and create dedicated database and user:
psql -U postgres -h 127.0.0.1 -p 5432 -c "CREATE USER ledgerline_user WITH PASSWORD 'ledgerline_secure_pass_2026';"
psql -U postgres -h 127.0.0.1 -p 5432 -c "CREATE DATABASE ledgerline WITH OWNER = ledgerline_user;"
psql -U postgres -h 127.0.0.1 -p 5432 -c "GRANT ALL PRIVILEGES ON DATABASE ledgerline TO ledgerline_user;"
```

---

### Step 3: Backend Setup & Database Migrations

From the project root:

```bash
# Create and activate Python virtual environment
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Apply initial Alembic migrations to PostgreSQL
alembic -c backend/alembic.ini upgrade head
```

---

### Step 4: Frontend Setup

```bash
cd frontend
npm install
cd ..
```

---

## 5. Starting the Applications

### Start the Backend
From the project root:
```bash
# Windows / Linux:
.\.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
- API Base: `http://127.0.0.1:8000`
- Interactive Swagger UI: `http://127.0.0.1:8000/docs`
- Health Endpoint: `http://127.0.0.1:8000/api/v1/health`

### Start the Frontend
In a separate terminal:
```bash
cd frontend
npm run dev
```
Open `http://localhost:5173` in your browser. The dashboard will automatically connect to the backend and display real-time database connectivity and telemetry.

---

## 6. Testing & Automated Verification

The test suite is split into isolated unit tests and real PostgreSQL integration tests.

### Run Unit Tests (Mocked / Fast)
```bash
.\.venv\Scripts\pytest backend/tests/unit -v
```

### Run PostgreSQL Integration Tests (Live Database)
```bash
.\.venv\Scripts\pytest backend/tests/integration -v
```

### Run Full Test Suite
```bash
.\.venv\Scripts\pytest backend/tests -v
```

---

## 7. Current Project Scope & Non-Goals (Task 01)
In strict compliance with foundation design constraints:
- Financial transactions, accounts, and double-entry postings are **not yet implemented**.
- Authentication, JWT tokens, and user credentials will be introduced in Task 02.
- The threat register (`THREATS.md`) accurately reflects planned mitigations without premature claims.
