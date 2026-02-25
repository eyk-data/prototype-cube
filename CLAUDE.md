# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A prototype for Cube.js multi-tenancy, demonstrating dynamic tenant loading with per-tenant database destinations. Built as a proof-of-concept for integrating Cube.js as a caching layer with multi-tenant support (Eyk x Embeddable).

## Running the Prototype

### Full Docker (all services)
```bash
docker compose up
```

### Local Development (recommended for server/webapp changes)
```bash
make dev-setup    # One-time: create .venv, install Python + Node deps
make dev-infra    # Start PostgreSQL + Cube in Docker (background)
make dev-server   # Run FastAPI with hot-reload on port 8000
make dev-webapp   # Run React dev server on port 3001
make dev-stop     # Stop Docker infrastructure
```

**Ports:**
- Webapp: http://localhost:3001 (local dev) / http://localhost:3000 (Docker)
- Server API: http://localhost:8000
- Cube playground: http://localhost:4000

## Architecture

Three services communicate in a chain:

**webapp** (React, port 3000) → **server** (FastAPI, port 8000) → **cube** (Cube.js, port 4000) → **destination DBs** (Postgres)

Flow:
1. Webapp fetches tenant list from server
2. User selects a tenant; webapp requests a JWT from server (`/tenants/{id}/token`)
3. Server encodes tenant's destination config + data models into a JWT signed with `CUBEJS_API_SECRET`
4. Webapp creates a Cube.js client using that JWT and queries Cube
5. Cube reads the JWT security context to dynamically connect to the correct Postgres destination via `driver_factory` and load the right data models via `repository_factory`

**Key files:**
- `cube/cube.py` — Cube.js Python config: `driver_factory`, `repository_factory`, `context_to_app_id`, `scheduled_refresh_contexts`
- `server/main.py` — FastAPI app with SQLModel (SQLite). Defines `Tenant`, `Destination` models and JWT generation endpoint
- `webapp/src/App.js` — React frontend using `@cubejs-client/core` and `@cubejs-client/react`

## Server (FastAPI)

- Python 3.9, dependencies in `server/requirements.txt`
- Uses SQLModel (SQLAlchemy + Pydantic) with a local SQLite database (`api.db`)
- Seeds test data (2 destinations, 2 tenants) on startup via `setup()` in the lifespan handler
- API secret shared with Cube: `CUBEJS_API_SECRET = "apisecret"`

**Endpoints:**
- `GET /tenants/` — list tenants
- `GET /tenants/{id}` — get tenant
- `GET /tenants/{id}/token` — generate JWT for Cube
- `GET /destinations/` — list destinations
- `GET /destinations/{id}` — get destination

## Cube Configuration

- `cube/cube.py` uses the Cube Python SDK (`from cube import config, file_repository`)
- Data models live in `cube/model/cubes/` (subdirs: `ecommerce_attribution`, `paid_performance`) and `cube/model/views/`
- Multi-tenancy is implemented via security context in JWT — each tenant gets isolated app ID, orchestrator ID, and pre-aggregation schema
- `driver_factory` maps the destination config from the JWT to a Postgres connection; only `postgres` type is implemented

## Webapp (React)

- Create React App with `@cubejs-client/core` + `@cubejs-client/react`
- No build tooling beyond CRA defaults; no test suite configured beyond CRA placeholder
- Uses Ant Design (`antd`) for table rendering

## Verifying Changes

Use the local dev workflow for fast iteration:
- **Server**: Run `make dev-server` for hot-reloading. For quick syntax checks without starting the server: `python -m py_compile server/agent/<file>.py`.
- **Webapp**: Run `make dev-webapp` for hot-reloading. For build checks: `cd webapp && npx react-scripts build`.
- **Docker**: Only use `docker compose build && docker compose up` for end-to-end integration testing. Use `--no-cache` on a specific service if you suspect layer caching issues (e.g., `docker compose build --no-cache webapp`).

## Planning & Verification Discipline

When implementing a plan:
1. **ALWAYS create a todo list** that includes verification/testing steps as explicit tasks — not just the implementation steps.
2. **ALWAYS run verification steps** after implementing changes. Never skip them, even if the code "looks right."
3. Iterate until verification passes. Do not mark work as done until tests/checks confirm it works.

## Dummy Data

`dummy_data/` contains SQL init scripts (`fill_destination1.sql`, `fill_destination2.sql`) that populate the two Postgres containers on startup.
