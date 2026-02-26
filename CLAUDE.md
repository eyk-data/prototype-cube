# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An AI-powered analytics chat application. Users ask questions in natural language; a pydantic-ai agent pipeline plans analytics queries, executes them against Cube (BigQuery), and assembles a report with text, charts, and tables.

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

**webapp** (React chat UI, port 3000) → **server** (FastAPI + pydantic-ai agents, port 8000) → **cube** (Cube.js, port 4000) → **BigQuery**

Flow:
1. User asks a question in the chat UI
2. Webapp sends the message to `POST /api/chat` (Vercel AI SDK data stream protocol)
3. Server runs a pydantic-ai/pydantic-graph analytics workflow: Planner → Block Executor (loop) → Reviewer → Assembler
4. Block Executor queries Cube (BigQuery) via REST API, Cube handles caching and pre-aggregations
5. Assembled report (text, charts, tables) streams back to the webapp

**Key files:**
- `server/main.py` — FastAPI app: chat endpoints, chat history persistence (PostgreSQL via SQLModel)
- `server/agent/` — pydantic-ai agents and pydantic-graph workflow (nodes, orchestrator, streaming, prompts, models)
- `cube/cube.js` — Cube.js config: BigQuery driver, security context (dataset from JWT)
- `cube/model/` — Cube YAML data models
- `webapp/src/` — React frontend using assistant-ui + Tailwind CSS

## Server (FastAPI)

- Python 3.9+, dependencies in `server/requirements.txt`
- Uses SQLModel (SQLAlchemy + Pydantic) with PostgreSQL for chat history persistence
- pydantic-ai agents for analytics workflow orchestration
- API secret shared with Cube: `CUBEJS_API_SECRET`

**Endpoints:**
- `GET /cube-token` — generate JWT for Cube (BigQuery dataset)
- `POST /api/chat` — streaming chat endpoint (Vercel AI SDK UI Message Stream Protocol v1)
- `GET /api/chats/` — list chat sessions
- `GET /api/chats/{thread_id}/messages` — get messages for a chat
- `DELETE /api/chats/{thread_id}` — delete a chat session

## Cube Configuration

- `cube/cube.js` configures the BigQuery driver via environment variables and GCP service account credentials
- Data models live in `cube/model/cubes/` and `cube/model/views/` (YAML)
- Security context in JWT carries the BigQuery dataset name

## Webapp (React)

- Built with assistant-ui for the chat interface and Tailwind CSS for styling
- Uses recharts for chart rendering in analytics reports
- Communicates with the server via Vercel AI SDK data stream protocol

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
