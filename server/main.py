import jwt
from typing import Optional, List
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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


CUBE_API_SECRET = "apisecret"

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
