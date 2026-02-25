# Prototype: Self-hosted Cube (BigQuery)

This repo provides a **local self-hosted Cube** setup that can replace the Embeddable (cloud) path. Cube connects to a **test GCP project** via a single **service account** and loads the **Cube models** pulled from the `eyk-analytics` repo.

## Layout

- **cube/** – Cube config and data models
  - `cube.js` – BigQuery driver config, security context (dataset from JWT or env).
  - `model/` – Cube YAML models (from eyk-analytics), use `COMPILE_CONTEXT.securityContext.dataset`.
- **server/** – Backend that issues Cube JWTs (`/cube-token`) and chat API.
- **webapp/** – React app that calls the Cube API (and server for token).

## Running the prototype

### 1. GCP credentials

- Download the Service Account JSON key and save it as **`cube/gcp-credentials.json`** (this file is gitignored).
- Ensure the BigQuery dataset and tables (e.g. from `eyk-transforms` / dbt) exist in that project.

### 2. Environment

```bash
cp cube/.env.example cube/.env
```

### 3. Start stack

```bash
docker compose up
```

- **Cube API**: http://localhost:4000
- **Server**: http://localhost:8000 (JWT endpoint, chat API)
- **Webapp**: http://localhost:3001

The webapp is configured with `REACT_APP_USE_SELF_HOSTED_CUBE=true` and fetches a Cube JWT from `GET /cube-token`, then queries Cube for **paid_performance** and **ecommerce_attribution**.

## References

- [Cube – Deploying with Docker](https://cube.dev/docs/product/deployment/core)
- [Cube – Google BigQuery](https://cube.dev/docs/product/configuration/data-sources/google-bigquery)
- [Cube – Security context](https://cube.dev/docs/product/auth/context)
