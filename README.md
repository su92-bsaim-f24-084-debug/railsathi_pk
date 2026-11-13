# RailSathi PK — Passenger Railway & Operations Prototype

RailSathi PK is an educational, Pakistan Railways-inspired Passenger Services and Railway Operations Management web application built with Python, modern Flask (Application Factory pattern), SQLAlchemy 2.x, PostgreSQL, and Bootstrap 5.

> **Academic Disclaimer:** RailSathi PK is an independent educational prototype developed for web engineering coursework. It is not officially affiliated with, endorsed by, or integrated into Pakistan Railways (PR). All operations, notifications, and transactions are simulated in an isolated application sandbox.

---

## 1. Technology Stack

- **Backend Framework:** Python 3.10+ & Flask 3.0.3
- **ORM & Database:** Flask-SQLAlchemy 3.1.1, SQLAlchemy 2.0.30, PostgreSQL 15+ (local and Render PostgreSQL)
- **Database Migrations:** Flask-Migrate 4.0.7 (Alembic)
- **Authentication & Security:** Flask-Login 0.6.3, Flask-WTF 1.2.1 (CSRF Protection), WTForms 3.1.2
- **Front-End Design:** Bootstrap 5.3.3, Bootstrap Icons 1.11.3, Jinja2 Template Inheritance
- **Production Server:** Gunicorn 22.0.0
- **Testing:** Pytest 8.2.2

---

## 2. Project Directory Structure

```
railsathi_pk/
│
├── .env.example                     # Environment variables template with safe placeholders
├── .gitignore                       # Git ignore rules (venv, bytecode, secrets, logs)
├── Procfile                         # Render WSGI process execution profile
├── README.md                        # Project documentation and developer manual
├── requirements.txt                 # Explicitly pinned, tested dependencies
├── run.py                           # Application WSGI entrypoint
│
├── app/
│   ├── __init__.py                  # Application Factory (`create_app`) & error handlers
│   ├── config.py                    # Environment configurations (Dev, Test, Prod)
│   ├── extensions.py                # Centralized extension singletons (db, migrate, login, csrf)
│   │
│   ├── auth/                        # Authentication blueprint (/auth)
│   │   ├── __init__.py
│   │   └── routes.py                # Login, register, logout foundation routes
│   │
│   ├── main/                        # Core public blueprint (/)
│   │   ├── __init__.py
│   │   └── routes.py                # Home page (/) and health probe (/healthz)
│   │
│   ├── common/                      # Shared mixins and utilities
│   │   └── __init__.py
│   │
│   ├── models/                      # Domain models package (50 models mapped in Phase 3)
│   │   └── __init__.py
│   │
│   ├── static/                      # Static client assets
│   │   ├── css/
│   │   │   └── custom.css           # Pakistan Railways theme accents (Green/Gold)
│   │   ├── js/
│   │   │   └── main.js              # Global client-side interactions
│   │   └── images/
│   │       └── .gitkeep
│   │
│   └── templates/                   # Jinja2 template hierarchy
│       ├── base.html                # Master HTML5 skeleton layout
│       ├── components/
│       │   └── _flash_messages.html # Reusable dismissible flash message toasts
│       ├── errors/
│       │   ├── 400.html             # Bad request page
│       │   ├── 403.html             # Access restricted page
│       │   ├── 404.html             # Not found page
│       │   └── 500.html             # Internal server error page
│       ├── main/
│       │   └── index.html           # Landing home page
│       └── auth/
│
├── migrations/                      # Flask-Migrate / Alembic version control
│   └── .gitkeep
│
└── tests/                           # Pytest automated test suite
    ├── __init__.py
    ├── conftest.py                  # Isolated testing fixtures and test client
    ├── test_config.py               # Config classes, secrets, booleans, and CSRF tests
    └── test_factory.py              # Application factory, routes, healthz, and error tests
```

---

## 3. Local Setup & Execution Guide

### Prerequisites
- Python 3.10 or higher
- PostgreSQL 15+ (optional for Phase 2; in-memory SQLite handles testing)

### Step 1: Clone and Navigate to Repository
```bash
git clone <repository-url>
cd railsathi_pk
```

### Step 2: Create and Activate Virtual Environment
On Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
On Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure a valid secret key is set for local development or testing.

### Step 5: Run Automated Tests
```bash
pytest -v
```

### Step 6: Start Local Development Server
```bash
python run.py
```
Open your browser and navigate to `http://localhost:5000/`.

---

## 4. Render Deployment Configuration

- **Environment:** Python 3
- **Build Command:**
  ```bash
  pip install --upgrade pip && pip install -r requirements.txt
  ```
- **Pre-Deploy Command (Phase 3 onwards):**
  ```bash
  flask db upgrade
  ```
- **Start Command:**
  ```bash
  gunicorn --workers 3 --threads 2 --timeout 120 "run:app"
  ```
- **Health Check Path:**
  `/healthz`

