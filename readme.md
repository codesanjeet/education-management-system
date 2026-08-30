<div align="center">

# 🎓 Education Management System

**A production-oriented, multi-tenant School/Institution management SaaS backend, built with FastAPI.**

Students, staff, billing, exams, admissions, public landing pages, and multi-channel communication for many institutions on one platform — with a built-in OpenAI-powered support agent and real usage metering baked into the API itself.

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Async-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0%20Async-CC2927)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Async-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![OpenAI](https://img.shields.io/badge/OpenAI-Powered%20AI%20Agent-412991?logo=openai&logoColor=white)](https://platform.openai.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](#license)

</div>

---

## 📖 Overview

This is the backend engine for a full-scale, multi-tenant school/college **SaaS** platform — not a CRUD toy project. It's built the way a real product handling live student and financial data has to be: async end-to-end, tenant-isolated, permission-checked on every route, and instrumented with 30+ typed domain exceptions instead of generic 500s.

A single deployment serves **many institutions independently** — each with its own students, staff, billing, public landing page, and admissions funnel — while a **Super Admin** layer (with its own auth, sessions, and audit trail, kept fully separate from tenant auth) manages institutions and platform oversight, and a per-institution **usage-metering model** (AI credits, email quota, voice-agent minutes, storage) hints at exactly how this would be turned into tiered pricing plans.

Three things make this stand out from a typical school-management project:

1. An **embedded AI support agent running on a dual-provider AI stack** — Google Vertex AI's Gemini 2.5 Flash for chat generation, OpenAI's `text-embedding-3-small` for vector search over a per-institution knowledge base (with a second embedding provider already coded and held in standby) — that institutions configure to answer parent/student questions, escalate what it can't answer, and improve from unanswered-question logs.
2. A **real billing engine** — invoices, payments, discounts, fines, and refunds as distinct, properly-typed tables, with an automated monthly invoice generator that resolves fee structures with fallback logic and duplicate protection.
3. A **marketing automation layer** — public landing pages per institution, an admissions funnel, and a WhatsApp/Email automation-rule engine with delivery-status webhooks — the kind of feature set you'd expect from a dedicated ed-tech growth product, not a back-office admin tool.

---

## ✨ Key Features

### 🏫 Multi-Tenant Institution Management
- Each institution operates in full data isolation via `tenant_id` + `institution_id` scoping enforced at the query layer.
- Institution onboarding, branding, and settings management via dedicated CRUD + service layers.
- **Usage metering built into the data model** (`InstitutionUsageDB`) — every institution tracks its own `ai_credits_balance`, `email_balance`, `ai_voice_agents_balance_min`, and `storage_used_mb`, which is exactly the plumbing a usage-based SaaS billing plan needs.
- A separate **Super Admin** domain — not just a role flag, but its own subsystem:
  - Dedicated `SuperAdminDB` + `SuperAdminSecurityDB` (password hash, TOTP secret, failed-login tracking, password-reset tokens) kept fully isolated from regular user auth.
  - `SuperAdminSessionDB` with JWT `jti` tracking for real session revocation, plus IP/user-agent metadata.
  - `SuperAdminLogDB` — every super-admin login attempt (success or failure) is audited.
  - Granular JSON permission grants (`can_create_institution`, `can_delete_institution`, `can_impersonate_admin`, scoped `accessible_institution_ids`).
- **Platform-wide activity/audit log** (`ActivityLogDB`) — a typed `ActionType` enum (20+ actions: user created/updated/deleted/restored, class changes, schedule changes, permission changes, disciplinary records, etc.) gives every institution a real audit trail, not just server logs.

### 🌐 Public Institution Landing Pages & Admissions Funnel
- Each institution can publish its own **public landing page** (`InstitutionPageDB`) — hero slider, about section, stats bar, feature highlights, contact info, social links, and an admissions on/off toggle — fully data-driven via JSONB, with a unique public `page_name` slug.
- An embedded **public admission form** (`AdmissionFormDB`) captures applicant, guardian, and academic details, and feeds a real review workflow: `pending → reviewed → accepted / rejected / waitlisted`, with reviewer attribution and notes.
- Optional **chatbot widget toggle** per landing page — ties directly into the AI agent platform below.
- A `ContactSubmissionDB` model backs a simple marketing-site lead-capture form, decoupled from any institution.

### 🔐 Authentication & Fine-Grained Authorization
- JWT access + refresh token flow (`app/core/security.py`), with configurable expiry (`ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`).
- **Google OAuth** login support alongside standard credential auth.
- A real **RBAC permission system** — not hardcoded role checks: permissions live in the DB (`PermissionDB`, `UserPermissionDB`), are embedded in the JWT, and are enforced with reusable dependency guards:
  - `require_permission(...)`
  - `require_any_permission(...)`
  - `require_permission_or_owner(...)`
- Five distinct user roles with dedicated data models: **Student, Teacher, Admin, Principal, Other Staff** (`app/models/role_specific/`).
- Optional 2FA method field (email / phone / app) baked into the user model for future rollout.
- **A real permission catalog, not ad-hoc checks**: `DEFAULT_PERMISSIONS_ADMIN`, `DEFAULT_PERMISSIONS_PRINCIPAL`, etc. define 30+ granular permission strings (`student:view_class` vs `student:view_all`, `fee:collection` vs `fee:structure_manage`, `content:full_management` vs `content:basic_management`) organized by domain — meaning access control decisions were designed up front, per role, rather than reverse-engineered from route logic later.

### 🤖 AI Agent Platform (the differentiator)
- **Per-institution AI agents** (`ai_agent_router`, `ai_agent_crud`) with their own knowledge base — add, update, bulk-import, and preview knowledge chunks.
- **Real vector similarity retrieval** — knowledge chunks are matched via `pgvector` (Postgres-native embedding search), grounding answers in institution-specific knowledge before falling back to the LLM, rather than a naive keyword match.
- Full **conversation session lifecycle**: `start_session` → `process_chat_turn` → `end_session`, with persisted conversation history per session.
- **Unanswered-question tracking** — questions the agent couldn't confidently answer are logged, reviewable, and resolvable/ignorable by staff, turning real usage into a feedback loop for the knowledge base.
- A separate **System AI Agent** (`system_ai_agent_router`) — a platform-level assistant for answering general product questions, decoupled from any institution's private data, with its own rate limiting and trusted-proxy IP resolution for accurate client identification behind load balancers.
- Custom in-process rate limiters (chat + bulk operations) to protect the OpenAI spend and prevent abuse — no external dependency required.

### 🎓 Academics & Operations
- **Admissions** pipeline — end-to-end enrollment workflow (`admission_router`, `admission_crud`) feeding directly from the public admission form above.
- **Student attendance** tracking per class, plus a **separate staff attendance system** (`StaffAttendanceDB`) with its own present/late/absent status enum — student and staff attendance are not conflated into one generic table.
- **Classes & Classrooms** management, including scheduling with **conflict detection** (`ScheduleConflictError`) and capacity enforcement (`ClassCapacityExceededError`).
- **Exam scheduling that goes beyond dates**: `ExamSchedule` stores a full JSON-based **exam routine** per subject (date, time, duration, venue, invigilator, marks), photo-ID specifications for admit cards, and structured exam instructions — with model-level status validation (`scheduled → ongoing → completed / cancelled / postponed`).
- **Exam seating engine**: `ClassroomDB` stores a JSON seating **layout config** (columns × rows × seats-per-column), and `ExamSeatingDB` assigns each student a specific row/column/seat — real exam-hall seat allocation, not just a room name.
- **Study materials** — file-backed resource sharing per class/subject, with upload validation (type, size).
- **Remarks** — structured teacher/staff feedback on students.
- **HR basics for staff**: `StaffSalaryDB` tracks salary type (monthly/yearly), total/paid/due amounts, a month-by-month JSON salary breakdown, academic-year tagging, and a full staff lifecycle status (`active, inactive, fired, resigned, retired, on_leave, suspended`).

### 💳 Finance & Billing Engine
This isn't a single "fees" table — it's a proper billing subsystem:
- **Fee Structures** — per class/institution, with a flexible JSON line-item structure and applicable-months array.
- **Invoices** — full lifecycle (`UNPAID → PARTIAL → PAID / OVERDUE / CANCELLED`) with subtotal, discounts, fines, paid amount, and balance due tracked as separate numeric columns (not derived on the fly).
- **Invoice Items, Payments, Discounts, Fines, and Refunds** as first-class related tables — payment method tracking (cash/UPI/card/bank transfer/cheque), transaction references, and refund status all modeled explicitly.
- **Automated invoice generation** (`app/services/invoice_scheduler_service.py`) — resolves the correct fee structure per class (class-specific → institution-wide fallback → explicit error if ambiguous), skips students who already have an invoice for that structure to prevent double-billing on re-runs, and is designed to be dropped straight into a cron job, Windows Task Scheduler, or APScheduler.
- Duplicate fee-structure protection (`DuplicateFeeStructureError`) baked in at the domain-exception level, not left to database constraints alone.

### 📣 Multi-Channel Communication & Marketing Automation
- **Announcements/notifications** with typed categories (`alert`, `official`, `event`, `academic`) and precise audience targeting (all / students / teachers / admins / principals / other staff / parents), backed by **read-receipt tracking** (`NotificationReadDB`) and composite indexes tuned for the exact list/filter queries the API needs.
- A genuine **automation rule engine** (`automation_rules`, `automation_crud`) that triggers outbound messages, logged per send in `NotificationMessageLogDB` with:
  - Channel-specific config (`WhatsAppConfigDB`, `EmailConfigDB`, SMS-ready),
  - Delivery status lifecycle (`queued → sent → delivered → read / failed`),
  - Provider message ID tracking so **webhook callbacks** from WhatsApp/email providers can be matched back to the original send.
- This is infrastructure for real parent/student engagement campaigns, not just a notification bell icon.

### ☁️ File Storage & Media
- **Cloudflare R2** integration (`app/core/storage.py`) with a clean abstraction over public vs. private buckets:
  - Permanent CDN URLs for public assets.
  - **Time-limited presigned URLs** for private/sensitive files.
  - Non-throwing `delete()` and `head()` helpers so storage hiccups never take down a request.
- Used for profile images, study materials, and institution branding assets, with dedicated validation exceptions (`InvalidImageError`, `ImageTooLargeError`, `InvalidFileTypeError`, `FileTooLargeError`).

### 📧 Transactional Email
- HTML email templates sent via **Resend** (`app/services/email.py`) — account activation, notifications, and branded institution communications.

### 🛡️ production-oriented Engineering Details
- **Fully async stack**: FastAPI + SQLAlchemy 2.0 async engine + asyncpg-style connection pooling (`pool_size`, `max_overflow`, `pool_pre_ping`, `pool_recycle` all explicitly tuned).
- **31 custom domain exceptions** (`app/core/exceptions.py`) — `UserNotFoundException`, `ClassCapacityExceededError`, `InstitutionAlreadyExistsError`, `InsufficientPermissionError`, `RateLimitExceededError`, and more — each mapped to a dedicated handler in `app/core/exception_handlers.py` for consistent, predictable API responses instead of leaking stack traces.
- **In-process sliding-window rate limiting** (`app/rate_limiter.py`) with per-IP or per-user keys, `Retry-After` headers, and reverse-proxy-aware IP resolution — no Redis required to get real protection.
- Centralized, environment-driven configuration via `pydantic-settings` (`app/core/config.py`) covering security, OAuth, OpenAI, storage, email, database, and CORS — nothing hardcoded.
- CORS explicitly configured for known frontend origins.
- Dedicated `/health` endpoint and a startup DB connectivity check for zero-guesswork deployments.
- **Dockerized** — a lean `python:3.12-slim` image, ready for any container platform.

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| **Language** | Python 3.12 |
| **Framework** | FastAPI `0.116` (fully async), Uvicorn |
| **ORM** | SQLAlchemy `2.0.43` (async engine + session), Alembic (migrations) |
| **Database** | PostgreSQL — `asyncpg` driver + `pgvector` for embedding/similarity search |
| **Auth** | PyJWT, Passlib + Argon2 password hashing, Google OAuth2, DB-backed RBAC |
| **AI — Generation** | Google Vertex AI, `gemini-2.5-flash` (via `google.genai`) — powers both the per-institution AI agent and the platform-level System AI Agent |
| **AI — Embeddings** | OpenAI `text-embedding-3-small` (1536-dim), active provider; a Gemini embedding path (`text-embedding-004`, 768-dim) is already coded but held in standby pending a paid Google API tier |
| **Vector Search** | `pgvector` — Postgres-native similarity search over knowledge chunks |
| **Storage** | Cloudflare R2 via `boto3` (S3-compatible) |
| **Email** | Resend SDK |
| **Files & Security** | Pillow (image processing), `python-magic` (real MIME sniffing, not trusting client headers), `bleach` (HTML sanitization) |
| **Config** | pydantic-settings (`.env` driven) |
| **Containerization** | Docker (`python:3.12-slim`) |

---

## 🗂️ Project Structure

```
app/
├── core/                  # Config, DB engine, security, storage, exceptions
│   ├── config.py          # Centralized env-driven settings (pydantic-settings)
│   ├── database.py        # Async SQLAlchemy engine + session factory
│   ├── security.py        # Password hashing, JWT creation/decoding
│   ├── storage.py         # Cloudflare R2 client abstraction
│   ├── exceptions.py      # 30+ custom domain exceptions
│   └── exception_handlers.py
├── models/                # SQLAlchemy ORM models
│   └── role_specific/     # Student / Teacher / Admin / Principal / Other Staff
├── schemas/                # Pydantic request/response schemas
├── crud/                  # Database access layer (one module per domain)
├── routers/                # 18 FastAPI routers — one per business domain
├── services/               # Email, storage, automation, user-domain logic
├── deps.py                # Auth & permission dependency injection
├── rate_limiter.py         # In-process sliding-window rate limiter
└── main.py                # App factory, middleware, router & exception wiring

Dockerfile
requirements.txt
```

### API Domains (18 routers)

| Domain | Domain | Domain |
|---|---|---|
| Authentication | Institutions | Students |
| Staff | Classes | Classrooms |
| Attendance | Admissions | Fees |
| Study Materials | Remarks | Notifications |
| Permissions | Settings | Super Admin |
| AI Agents | System AI Agent | — |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.12+
- PostgreSQL instance
- Docker (optional, for containerized run)
- API keys: OpenAI, Google OAuth, Cloudflare R2, Resend

### 1. Clone & install
```bash
git clone https://github.com/codesanjeet/education-management-system.git
cd education-management-system
pip install -r requirements.txt
```

### 2. Configure environment
Create a `.env` file in the project root:

```env
# Security
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=12

# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# OpenAI
OPENAI_API_KEY=your-openai-key

# Cloudflare R2
R2_ACCESS_KEY=your-r2-access-key
R2_SECRET_KEY=your-r2-secret-key
R2_ENDPOINT=your-r2-endpoint
R2_PUBLIC_BASE_URL=your-public-cdn-url
R2_PUBLIC_BASE=your-public-cdn-url
R2_PRIVATE_BUCKET_NAME=your-private-bucket
R2_PUBLIC_BUCKET_NAME=your-public-bucket

# Email (Resend)
RESEND_API_KEY=your-resend-key
EMAIL_FROM_ADDRESS=noreply@yourdomain.com

# Notifications
NOTIFICATION_EMAIL_TOKEN_SECRET=your-notification-secret

# Database
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname

# Application URLs
BACKEND_BASE_URL=http://localhost:8000
FRONTEND_BASE_URL=http://localhost:3000

# Environment
ENVIRONMENT=development
```

> **Note:** `R2_PUBLIC_BASE` is read directly by `app/core/storage.py` and is
> required in addition to `R2_PUBLIC_BASE_URL` (used by `app/core/config.py`).
> Both currently need to be set to the same CDN URL for the app to start.

### 4. Set up the database
This project doesn't ship pre-baked migrations (intentional — schema history isn't tied to any one deployment). Set up your own Alembic environment against the models in `app/models/`, or run a one-off `create_all()` against the async engine for local development.

### 5. Run locally
```bash
uvicorn app.main:app --reload
```
API docs available at `http://localhost:8000/docs` (Swagger) and `http://localhost:8000/redoc`.

### 6. Or run with Docker
```bash
docker build -t education-management-system .
docker run -p 8000:8000 --env-file .env education-management-system
```

### 7. Health check
```bash
curl http://localhost:8000/health
```

---

## ✅ Testing

```bash
pip install pytest pytest-asyncio httpx
pytest
```

The suite doesn't require a live database or external services — it covers
what can be verified without one:

- Auth boundaries — protected routes reject missing/malformed tokens, login
  and check-email input validation, the password policy
- The RBAC dependency layer (`require_permission`, `require_any_permission`,
  `require_permission_or_owner`) exercised directly
- JWT/tenant handling — tokens missing `tenant_id` or `role` are rejected,
  forged and expired tokens fail to decode
- Pydantic schema validation for students, fee structures, payments, and
  institutions (including the XSS guard on free-text contact fields)
- The invoice recalculation logic in `fee_crud.py` (unpaid → partial → paid,
  overpayment, ignoring failed payments)
- The custom exception → HTTP status mapping in `exception_handlers.py`

Not yet covered: full create → fetch → update → delete flows against a real
database. Several models use Postgres-specific `JSONB` columns, so that
layer needs an actual Postgres instance (e.g. via `docker-compose` in CI)
rather than an in-memory SQLite substitute.

---

## 🧭 Design Philosophy

This project intentionally avoids the "one big `main.py`" trap:

- **Layered architecture** — routers only handle HTTP concerns; business logic lives in `crud/` and `services/`; validation lives in `schemas/`.
- **Fail loud, fail typed** — every domain error is a named exception with its own handler, so API consumers always get a predictable, documented error shape.
- **Permission checks are declarative**, not scattered `if user.role == "admin"` checks buried in route bodies — permissions are defined once as a catalog and enforced through reusable dependencies.
- **Multi-tenancy is a first-class concern**, not bolted on — `tenant_id` and `institution_id` flow through the token, the dependency layer, and the data layer consistently.
- **Money is modeled precisely** — `Numeric(12, 2)` columns for every currency field (never `Float`), and invoice totals are stored, not computed on read.
- **Auth surfaces are isolated** — regular users and super admins have entirely separate session, security, and audit tables, so a bug or breach in one can't cascade into the other.

---

## 🗺️ Roadmap Ideas

- [ ] Add CI with GitHub Actions
- [ ] Ship an optional Alembic harness for contributors
- [ ] Add OpenAPI-generated TypeScript client
- [ ] Move automated invoice generation to a managed task queue
- [ ] Complete SMS channel support
- [ ] Wire up the existing 2FA fields
---

## 👤 Author

**Sanjeet** — [@codesanjeet](https://github.com/codesanjeet)

## 📄 License

This project is available under the [MIT License](LICENSE).

---

<div align="center">
<sub>Built with FastAPI, async SQLAlchemy, and a healthy respect for typed exceptions.</sub>
</div>