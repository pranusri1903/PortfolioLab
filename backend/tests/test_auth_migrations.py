import time

import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine, inspect

from app.auth import verify_clerk_token
from app.config import Settings
from app.errors import ApiError

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SETTINGS = Settings(auth_mode="clerk", clerk_jwks_url="https://x/jwks", clerk_issuer="https://clerk.test")
resolver = lambda token, settings: KEY.public_key()  # noqa: E731


def token(**claims):
    base = {"sub": "user_1", "iss": "https://clerk.test", "exp": int(time.time()) + 60}
    return jwt.encode({**base, **claims}, KEY, algorithm="RS256")


def test_valid_clerk_token_returns_subject():
    assert verify_clerk_token(token(), SETTINGS, resolver) == "user_1"


@pytest.mark.parametrize("claims", [{"exp": 1}, {"iss": "https://evil"}])
def test_expired_or_wrong_issuer_rejected(claims):
    with pytest.raises(ApiError) as e:
        verify_clerk_token(token(**claims), SETTINGS, resolver)
    assert e.value.status == 401


def test_token_signed_with_other_key_rejected():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bad = jwt.encode(
        {"sub": "u", "iss": "https://clerk.test", "exp": int(time.time()) + 60}, other, algorithm="RS256"
    )
    with pytest.raises(ApiError):
        verify_clerk_token(bad, SETTINGS, resolver)


def test_migrations_create_all_tables(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    from app.config import get_settings

    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    get_settings.cache_clear()
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"portfolios", "assets", "transactions", "daily_prices", "daily_snapshots"} <= tables
