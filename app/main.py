from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlmodel import Field, Session, SQLModel, create_engine, select


class Destination(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hostname: str
    port: int
    database: str
    username: str
    password: str


sqlite_file_name = "app/database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, echo=True, connect_args=connect_args)


def setup():
    SQLModel.metadata.create_all(engine)
    destination1 = Destination(
        hostname="destination1",
        port=5433,
        database="database1",
        username="username1",
        password="password1",
    )
    destination2 = Destination(
        hostname="destination2",
        port=5434,
        database="database2",
        username="username2",
        password="password2",
    )
    with Session(engine) as session:
        session.add(destination1)
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
