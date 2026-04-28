import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Phase 4 swaps SQLite for Postgres. Everything else stays the same — the
# whole point of using SQLAlchemy from Phase 1 was to make this change a
# one-line connection-string swap.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://shortener:shortener@localhost:5432/shortener",
)

# pool_pre_ping: SQLAlchemy tests the connection before handing it out.
# Cheap insurance against stale connections (e.g. after `docker compose
# restart postgres`).
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
