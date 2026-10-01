import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.db import Base, get_session, make_engine
from app.main import app
from app.services.demo import seed_market_data


@pytest.fixture
def engine():
    e = make_engine("sqlite://")
    Base.metadata.create_all(e)
    yield e


@pytest.fixture
def db(engine):
    with Session(engine) as s:
        seed_market_data(s)
        yield s


@pytest.fixture
def client(engine, db):
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _session():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth(user="alice"):
    return {"Authorization": f"Bearer dev:{user}"}


@pytest.fixture
def portfolio(client):
    """An empty portfolio owned by alice."""
    r = client.post("/api/v1/portfolios", json={"name": "Mine"}, headers=auth())
    assert r.status_code == 201, r.text
    return r.json()["id"]
