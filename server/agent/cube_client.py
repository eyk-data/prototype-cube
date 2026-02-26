from __future__ import annotations

import os

import httpx
import jwt

from .models import CubeQuery

CUBE_API_SECRET = os.environ.get("CUBE_API_SECRET") or os.environ.get(
    "CUBEJS_API_SECRET", "apisecret"
)
CUBEJS_BQ_DATASET = os.environ.get("CUBEJS_BQ_DATASET", "")
CUBE_BASE_URL = os.environ.get("CUBE_BASE_URL", "http://cube:4000")


def _make_token() -> str:
    payload = {"dataset": CUBEJS_BQ_DATASET}
    return jwt.encode(payload, CUBE_API_SECRET, algorithm="HS256")


async def fetch_cube_meta() -> dict:
    """Fetch model metadata from the CubeJS /meta endpoint."""
    token = _make_token()
    url = f"{CUBE_BASE_URL}/cubejs-api/v1/meta"
    headers = {"Authorization": token}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def execute_cube_query(query: CubeQuery) -> dict:
    """Execute a CubeQuery against the CubeJS REST API and return the JSON response."""
    token = _make_token()
    url = f"{CUBE_BASE_URL}/cubejs-api/v1/load"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
    }
    body = {"query": query.to_cube_api_payload()}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()
