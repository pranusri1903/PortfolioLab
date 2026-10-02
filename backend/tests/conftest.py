import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.api.market import get_provider
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


class OfflineProvider:
    """Stands in for the live providers so tests never touch the network."""

    stocks = funds = None

    def search(self, q, currency=None):
        return []


@pytest.fixture(autouse=True)
def offline(request):
    if "client" in request.fixturenames:
        app.dependency_overrides[get_provider] = lambda: OfflineProvider()
    yield


@pytest.fixture
def portfolio(client):
    """An empty portfolio owned by alice."""
    r = client.post("/api/v1/portfolios", json={"name": "Mine"}, headers=auth())
    assert r.status_code == 201, r.text
    return r.json()["id"]
