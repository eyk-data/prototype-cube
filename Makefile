-include .env.local
-include cube/.env
export

.PHONY: dev-setup dev-infra dev-server dev-webapp dev-stop

## One-time setup: create venv, install Python + Node deps
dev-setup:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r server/requirements.txt
	cd webapp && npm install

## Start infrastructure (PostgreSQL + Cube) in Docker
dev-infra:
	docker compose -f docker-compose.dev.yml up -d

## Run FastAPI server locally with hot-reload on port 8000
dev-server:
	.venv/bin/uvicorn server.main:app --reload --host 0.0.0.0 --port 8000

## Run React dev server on port 3001
dev-webapp:
	cd webapp && PORT=3001 REACT_APP_SERVER_URL=http://localhost:8000 npm start

## Stop Docker infrastructure
dev-stop:
	docker compose -f docker-compose.dev.yml down
