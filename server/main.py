import os
import jwt
import json
import uuid
import random
import asyncio
from typing import Optional, List
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from starlette.responses import StreamingResponse

from sqlmodel import (
    Field,
    Session,
    SQLModel,
    create_engine,
    select,
    delete,
    Column,
    JSON,
)


CUBE_API_SECRET = os.environ.get("CUBE_API_SECRET") or os.environ.get("CUBEJS_API_SECRET", "apisecret")
CUBEJS_BQ_DATASET = os.environ.get("CUBEJS_BQ_DATASET", "")

sqlite_file_name = "api.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, echo=True, connect_args=connect_args)


class Destination(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    type: str
    hostname: str
    port: int
    database: str
    schema: str
    username: str
    password: str


class DataModel(Enum):
    ecommerce_attribution = "ecommerce_attribution"
    paid_performance = "paid_performance"


class Tenant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    data_models: List[str] = Field(default=None, sa_column=Column(JSON))
    destination_id: Optional[int] = Field(default=None, foreign_key="destination.id")

    class Config:
        arbitrary_types_allowed = True


def setup():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # Delete old destinations
        statement = delete(Destination)
        session.exec(statement)
        statement = delete(Tenant)
        session.exec(statement)
        session.commit()

        # Create new destinations
        destination1 = Destination(
            type="postgres",
            hostname="destination1",
            port=5432,
            database="database1",
            schema="public",
            username="username1",
            password="password1",
        )

        destination2 = Destination(
            type="postgres",
            hostname="destination2",
            port=5432,
            database="database2",
            schema="public",
            username="username2",
            password="password2",
        )

        session.add(destination1)
        session.add(destination2)
        session.commit()

        # Create new tenants
        tenant1 = Tenant(
            name="tenant1",
            data_models=[DataModel.paid_performance.value],
            destination_id=destination1.id,
        )
        session.add(tenant1)

        tenant2 = Tenant(
            name="tenant2",
            data_models=[
                DataModel.paid_performance.value,
                DataModel.ecommerce_attribution.value,
            ],
            destination_id=destination2.id,
        )
        session.add(tenant2)
        session.commit()

        session.refresh(tenant1)
        session.refresh(tenant2)

        print("Tenant 1:", tenant1)
        print("Tenant 2:", tenant2)


def teardown():
    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup()
    yield
    teardown()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-vercel-ai-ui-message-stream"],
)


@app.get("/destinations/", response_model=List[Destination])
def list_destinations():
    with Session(engine) as session:
        destinations = session.exec(select(Destination)).all()
        return destinations


@app.get("/destinations/{destination_id}", response_model=Destination)
def retrieve_destination(destination_id: int):
    with Session(engine) as session:
        destination = session.get(Destination, destination_id)
        if not destination:
            raise HTTPException(status_code=404, detail="Destination not found")
        return destination


@app.get("/tenants/", response_model=List[Tenant])
def list_tenants():
    with Session(engine) as session:
        tenants = session.exec(select(Tenant)).all()
        return tenants


@app.get("/tenants/{tenant_id}", response_model=Tenant)
def retrieve_tenant(tenant_id: int):
    with Session(engine) as session:
        tenant = session.get(Tenant, tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant


@app.get("/tenants/{tenant_id}/token")
def generate_jwt_token(tenant_id: int) -> str:
    with Session(engine) as session:
        tenant = session.get(Tenant, tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        destination = session.get(Destination, tenant.destination_id)
        if not destination:
            raise HTTPException(status_code=404, detail="Destination not found")
        token_payload = {
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "data_models": tenant.data_models,
            "destination": destination.model_dump(),
        }
        token = jwt.encode(token_payload, CUBE_API_SECRET, algorithm="HS256")
        return token


@app.get("/cube-token", response_class=PlainTextResponse)
def get_cube_token(dataset: Optional[str] = None) -> str:
    """Return a JWT for self-hosted Cube (BigQuery). Payload includes dataset for COMPILE_CONTEXT.
    Plain text response so the client gets the raw token, not JSON-wrapped."""
    ds = (dataset or CUBEJS_BQ_DATASET or "").strip()
    if not ds:
        raise HTTPException(
            status_code=400,
            detail="Missing dataset. Set CUBEJS_BQ_DATASET in cube/.env or pass ?dataset=...",
        )
    payload = {"dataset": ds}
    token = jwt.encode(payload, CUBE_API_SECRET, algorithm="HS256")
    return token


# ---------------------------------------------------------------------------
# Streaming chat endpoint (Vercel AI SDK UI Message Stream Protocol v1)
# ---------------------------------------------------------------------------

MOCK_THINKING = [
    "Let me analyze what you're asking about. I need to consider the data sources available and determine the best approach to answer your question.",
    "Thinking through this step by step. First, I'll look at the relevant metrics, then consider how they relate to your question.",
    "Processing your request. I'm reviewing the available data models to find the most relevant information for you.",
    "Let me reason about this carefully. I want to make sure I provide accurate and useful information based on the data we have.",
]

MOCK_RESPONSES = [
    "Based on the available data, here's what I found:\n\n**Key Metrics Summary**\n- Total impressions: 125,430\n- Click-through rate: 3.2%\n- Conversion rate: 1.8%\n\nThe paid performance campaigns are showing steady growth over the last quarter. The top-performing campaign is *Summer Sale 2024* with a ROAS of 4.2x.\n\nWould you like me to drill deeper into any specific campaign or metric?",
    "Here's an overview of the ecommerce attribution data:\n\n**Attribution by Channel**\n| Channel | Revenue | Spend | ROAS |\n|---------|---------|-------|------|\n| Google Ads | $45,200 | $12,000 | 3.8x |\n| Meta Ads | $32,100 | $9,500 | 3.4x |\n| Email | $28,700 | $2,100 | 13.7x |\n\nEmail continues to deliver the highest return on ad spend, though paid channels drive significantly more total revenue.\n\nLet me know if you'd like to explore a specific channel in more detail.",
    "Great question! Let me break down the performance trends:\n\n1. **Traffic Sources**: Organic search accounts for 42% of total sessions, followed by paid search at 28%\n2. **Top Campaigns**: The brand awareness campaign saw a 15% increase in impressions this month\n3. **Conversion Funnel**: Cart abandonment rate decreased from 72% to 68% after the checkout optimization\n\nThe overall trend is positive. Shall I generate a more detailed report on any of these areas?",
    "I've looked into the subscription performance data:\n\n**Monthly Recurring Revenue (MRR)**\n- Current MRR: $89,400\n- MRR Growth: +6.2% month-over-month\n- Churn Rate: 2.1%\n- Net Revenue Retention: 112%\n\nThe cohort analysis shows that customers acquired through referral programs have a 35% higher lifetime value compared to those from paid channels.\n\nWould you like me to analyze a specific cohort or time period?",
]


async def _chat_stream(messages: list):
    """Generator that yields Vercel AI SDK data stream protocol lines.

    Format: each line is ``<type_prefix>:<json_value>\\n``
    Type prefixes:
      0  = text delta
      e  = finish (with reason + usage)
      d  = done
    """
    thinking = random.choice(MOCK_THINKING)
    response = random.choice(MOCK_RESPONSES)

    # Stream the text response word by word
    for word in response.split(" "):
        yield f'0:{json.dumps(word + " ")}\n'
        await asyncio.sleep(random.uniform(0.03, 0.08))

    # finish event
    yield f'e:{json.dumps({"finishReason": "stop", "usage": {"promptTokens": 42, "completionTokens": 128}})}\n'
    # done
    yield f'd:{json.dumps({"finishReason": "stop", "usage": {"promptTokens": 42, "completionTokens": 128}})}\n'


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    return StreamingResponse(
        _chat_stream(messages),
        media_type="text/plain; charset=utf-8",
        headers={
            "x-vercel-ai-data-stream": "v1",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
