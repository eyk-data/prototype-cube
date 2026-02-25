import os
import uuid
import jwt
from datetime import datetime
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

from server.agent.streaming import pydanticai_to_datastream, report_to_content_parts


CUBE_API_SECRET = os.environ.get("CUBE_API_SECRET") or os.environ.get("CUBEJS_API_SECRET", "apisecret")
CUBEJS_BQ_DATASET = os.environ.get("CUBEJS_BQ_DATASET", "")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/server")
engine = create_engine(DATABASE_URL, echo=True)


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


class Chat(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    thread_id: str = Field(index=True, unique=True)
    title: str = Field(default="New Chat")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    thread_id: str = Field(index=True)
    role: str  # "user" or "assistant"
    content: str = ""
    report_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


def setup():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # Delete old data (tenants first due to FK constraint)
        statement = delete(Tenant)
        session.exec(statement)
        statement = delete(Destination)
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
# Chat history endpoints
# ---------------------------------------------------------------------------


@app.get("/api/chats/")
def list_chats():
    with Session(engine) as session:
        chats = session.exec(
            select(Chat).order_by(Chat.updated_at.desc())
        ).all()
        return chats


@app.get("/api/chats/{thread_id}/messages")
def get_chat_messages(thread_id: str):
    with Session(engine) as session:
        msgs = session.exec(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.created_at)
        ).all()

    if not msgs:
        raise HTTPException(status_code=404, detail="Thread not found")

    result = []
    for msg in msgs:
        if msg.role == "user":
            result.append({"id": str(msg.id), "role": "user", "content": msg.content})
        elif msg.role == "assistant":
            if msg.report_data:
                content_parts = report_to_content_parts(msg.report_data)
                result.append({"id": str(msg.id), "role": "assistant", "content": content_parts})
            else:
                result.append({"id": str(msg.id), "role": "assistant", "content": msg.content})
    return result


@app.delete("/api/chats/{thread_id}")
def delete_chat(thread_id: str):
    with Session(engine) as session:
        chat = session.exec(
            select(Chat).where(Chat.thread_id == thread_id)
        ).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        session.exec(delete(ChatMessage).where(ChatMessage.thread_id == thread_id))
        session.delete(chat)
        session.commit()
        return {"ok": True}


# ---------------------------------------------------------------------------
# Streaming chat endpoint (Vercel AI SDK UI Message Stream Protocol v1)
# ---------------------------------------------------------------------------


def _extract_content_text(content) -> str:
    """Extract text from AI SDK content (string or content parts array)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [
            p.get("text", "") for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return " ".join(text_parts)
    return ""


def _build_conversation_history(
    thread_id: str, max_messages: int = 10, exclude_last: bool = False,
) -> str:
    """Load recent ChatMessage rows for a thread and format as history string."""
    limit = max_messages + 1 if exclude_last else max_messages
    with Session(engine) as session:
        msgs = session.exec(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        ).all()

    if not msgs:
        return ""

    # Reverse to chronological order
    msgs = list(reversed(msgs))
    if exclude_last:
        msgs = msgs[:-1]  # drop the most recently stored message

    parts = []
    for msg in msgs:
        if msg.role == "user":
            parts.append(f"User: {msg.content}")
        elif msg.role == "assistant":
            content = msg.content
            if len(content) > 1500:
                content = content[:1500] + "... [truncated]"
            parts.append(f"Assistant: {content}")
    return "\n\n".join(parts)


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    thread_id = body.get("thread_id") or str(uuid.uuid4())

    # Extract user message text
    user_messages = [msg for msg in messages if msg.get("role") == "user"]
    last_user = user_messages[-1] if user_messages else {"content": ""}
    user_text = _extract_content_text(last_user.get("content", ""))

    # Create or update Chat record + store user message
    with Session(engine) as session:
        existing = session.exec(
            select(Chat).where(Chat.thread_id == thread_id)
        ).first()
        if existing:
            existing.updated_at = datetime.utcnow()
            session.add(existing)
        else:
            title = user_text[:100] if user_text else "New Chat"
            chat_record = Chat(thread_id=thread_id, title=title)
            session.add(chat_record)

        # Store user message
        session.add(ChatMessage(
            thread_id=thread_id,
            role="user",
            content=user_text,
        ))
        session.commit()

    # Build conversation history from stored messages excluding the message
    # we just stored (the current user question is passed separately).
    conversation_history = _build_conversation_history(thread_id, exclude_last=True)

    return StreamingResponse(
        pydanticai_to_datastream(messages, thread_id, conversation_history),
        media_type="text/plain; charset=utf-8",
        headers={
            "x-vercel-ai-data-stream": "v1",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
