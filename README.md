# Personal AI Call Agent

A production-oriented Personal AI Call Agent that can answer incoming phone calls on behalf of the user.

## Setup

1. Copy `.env.example` to `.env` and fill in the values.
2. Install dependencies: `make setup`
3. Run migrations: `make db-upgrade`
4. Run the server: `make run`

## Testing

Run tests with `make test`.

---

## Hardening Verification

This project has been hardened with the following utilities:
- **Linting:** Run `ruff check .`
- **Type Checking:** Run `mypy app/`
- **Testing:** Run `pytest`
- **Health Checks:** `/health` and `/ready` endpoints are available.
- **Production Security:** `DATABASE_URL` bindings are strictly used, explicit configuration prevents exposing PostgreSQL/Redis ports in Docker Compose in production mode, and internal exceptions in health checks are masked from external viewers.
