import jwt
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from sqlmodel import Field, Session, SQLModel, create_engine, select, delete


CUBE_API_SECRET = "apisecret"

sqlite_file_name = "/code/app/api.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, echo=True, connect_args=connect_args)


class Destination(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    type: str
    hostname: str
    port: int
    database: str
    username: str
    password: str


def generate_token(destination: Destination) -> str:
    token_payload = {
        "tenant_id": destination.id,
        "destination_config": destination.model_dump(),
    }

    # Generate the JWT token
    token = jwt.encode(token_payload, CUBE_API_SECRET, algorithm="HS256")
    return token


def setup():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # Delete old destinations
        statement = delete(Destination)
        session.exec(statement)
        session.commit()

        # Create new destinations
        destination1 = Destination(
            type="postgres",
            hostname="destination1",
            port=5432,
            database="database1",
            username="username1",
            password="password1",
        )
        session.add(destination1)
        destination2 = Destination(
            type="postgres",
            hostname="destination2",
            port=5432,
            database="database2",
            username="username2",
            password="password2",
        )
        session.add(destination2)
        session.commit()


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


@app.get("/destinations/")
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


@app.get("/destinations/{destination_id}/token")
def generate_jwt_token(destination_id: int) -> str:
    with Session(engine) as session:
        destination = session.get(Destination, destination_id)
        if not destination:
            raise HTTPException(status_code=404, detail="Destination not found")
        print(destination)
        return generate_token(destination)
