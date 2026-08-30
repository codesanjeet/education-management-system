# Running these tests

```
pip install pytest pytest-asyncio httpx
pytest
```

`app/core/config.py` and `app/core/storage.py` require a number of env vars
just to *import* the app (`SECRET_KEY`, `DATABASE_URL`, `R2_*`, etc). If you
already run the app locally with a `.env` file, that's picked up
automatically and nothing else is needed. If not, `conftest.py` fills in
harmless placeholder values for anything missing so the test session can
start.

None of these tests connect to a real database or external service. They
cover:

- `test_health.py` — the `/health` endpoint
- `test_auth.py` — login/check-email validation, protected-route 401s, the
  password policy in `auth_router.py`
- `test_permissions.py` — the authorization helpers in `app/deps.py`
  (`require_permission`, `require_any_permission`, `require_permission_or_owner`)
- `test_tenant_isolation.py` — JWTs without a `tenant_id`/`role` are
  rejected, forged and expired tokens fail
- `test_students.py` — `StudentCreate` schema validation, auth-required
  checks on the student endpoints
- `test_fees.py` — the invoice recalculation logic in `fee_crud.py`
  (unpaid/partial/paid/overpaid), `FeeStructureCreate` and `PaymentCreate`
  validation
- `test_institutions.py` — `InstitutionCreate`/`ContactSubmissionCreate`
  validation (including the XSS guard on free-text fields), auth-required
  checks
- `test_validation.py` — the custom exception → HTTP status mapping in
  `app/core/exception_handlers.py`

What's deliberately **not** here: full create → fetch → update → delete
flows against a real database. Several of your models (`fee_model.py`,
others) use Postgres-specific `JSONB` columns, so an in-memory SQLite test
DB won't stand up your schema without extra work, and I didn't want to hand
you tests that pass against a fake DB without proving anything. If you want
that layer next, the natural next step is a `docker-compose` Postgres
service (or similar) for CI and a fixture that creates/tears down a schema
per test run.
