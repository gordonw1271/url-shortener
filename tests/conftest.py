"""Shared test fixtures.

Two important details:

1. We set MACHINE_ID and DATABASE_URL via env vars BEFORE importing
   `app.main`, because main.py reads them at module load time.

2. We point at a separate `shortener_test` database so tests never touch
   dev data. The first run creates it on demand via the admin connection.
"""
import os

# Must be set before any `from app...` import below.
os.environ.setdefault("MACHINE_ID", "a")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://shortener:shortener@localhost:5432/shortener_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")


def _ensure_test_db() -> None:
    """Create `shortener_test` if it doesn't exist."""
    import psycopg

    admin_url = "postgresql://shortener:shortener@localhost:5432/postgres"
    with psycopg.connect(admin_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = 'shortener_test'")
            if cur.fetchone() is None:
                cur.execute("CREATE DATABASE shortener_test")


_ensure_test_db()

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import cache  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Swap the real Redis client with fakeredis for every test."""
    fake = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(cache, "_client", fake)
    return fake


@pytest.fixture(autouse=True)
def reset_db():
    """Truncate tables and reset the per-machine sequence before each test."""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE SEQUENCE IF NOT EXISTS seq_a"))
        conn.execute(text("TRUNCATE clicks, url_mappings RESTART IDENTITY CASCADE"))
        conn.execute(text("ALTER SEQUENCE seq_a RESTART WITH 1"))
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
