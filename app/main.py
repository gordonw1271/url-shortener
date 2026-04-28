import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import cache
from .db import Base, SessionLocal, engine, get_session
from .encoding import ALPHABET, encode
from .models import Click, URLMapping
from .schemas import ClickRecord, ShortenRequest, ShortenResponse, StatsResponse

# Uvicorn only configures its own loggers (`uvicorn`, `uvicorn.access`). Our
# `app.*` loggers default to WARNING, so cache HIT/MISS lines never show up.
# Attach an INFO-level stdout handler to the whole `app` namespace.
_app_logger = logging.getLogger("app")
if not _app_logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(levelname)-7s %(name)s: %(message)s"))
    _app_logger.addHandler(_h)
_app_logger.setLevel(logging.INFO)
_app_logger.propagate = False

log = logging.getLogger(__name__)

# Phase 4: every instance has a unique single-character ID. Short codes are
# `MACHINE_ID + base62(per-machine-counter)`, so two instances mint codes in
# disjoint keyspaces — no coordination required to avoid collisions.
MACHINE_ID = os.getenv("MACHINE_ID", "a")
if len(MACHINE_ID) != 1 or MACHINE_ID not in ALPHABET:
    raise RuntimeError(
        f"MACHINE_ID must be a single base62 character (got {MACHINE_ID!r})"
    )

SEQ_NAME = f"seq_{MACHINE_ID}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        # Per-machine Postgres SEQUENCE. Each instance pulls from its own;
        # nextval() is atomic, so two writers on the same instance still
        # serialize correctly, and instances never see each other's counter.
        conn.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {SEQ_NAME}"))
    log.info("instance MACHINE_ID=%s ready (sequence=%s)", MACHINE_ID, SEQ_NAME)
    yield


app = FastAPI(
    title=f"URL Shortener — Phase 4 (instance {MACHINE_ID})",
    description=(
        f"This instance prefixes every short code with `{MACHINE_ID}`. nginx "
        "(port 8000) round-robins POSTs across two instances; either instance "
        "can serve any GET because they share Postgres + Redis."
    ),
    lifespan=lifespan,
)


@app.post("/shorten", response_model=ShortenResponse, status_code=201)
def shorten(
    payload: ShortenRequest,
    request: Request,
    db: Session = Depends(get_session),
) -> ShortenResponse:
    # Pull the next per-machine sequence value, then prefix with MACHINE_ID
    # to produce a globally unique short code without coordinating with the
    # other instance.
    seq = db.execute(text(f"SELECT nextval('{SEQ_NAME}')")).scalar()
    short_code = MACHINE_ID + encode(seq)
    row = URLMapping(short_code=short_code, long_url=str(payload.url))
    db.add(row)
    db.commit()
    db.refresh(row)

    base = str(request.base_url).rstrip("/")
    return ShortenResponse(
        short_code=row.short_code,
        short_url=f"{base}/{row.short_code}",
        long_url=row.long_url,
    )


def _record_click(
    short_code: str,
    ip: str | None,
    user_agent: str | None,
    referer: str | None,
) -> None:
    db = SessionLocal()
    try:
        row = (
            db.query(URLMapping)
            .filter(URLMapping.short_code == short_code)
            .one_or_none()
        )
        if row is None:
            return
        db.add(
            Click(
                mapping_id=row.id,
                ip=ip,
                user_agent=user_agent,
                referer=referer,
            )
        )
        db.commit()
    finally:
        db.close()


@app.get("/stats/{short_code}", response_model=StatsResponse)
def stats(short_code: str, db: Session = Depends(get_session)) -> StatsResponse:
    row = db.query(URLMapping).filter(URLMapping.short_code == short_code).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="short code not found")

    total = db.query(Click).filter(Click.mapping_id == row.id).count()
    recent = (
        db.query(Click)
        .filter(Click.mapping_id == row.id)
        .order_by(Click.clicked_at.desc())
        .limit(10)
        .all()
    )
    return StatsResponse(
        short_code=row.short_code,
        long_url=row.long_url,
        total_clicks=total,
        recent=[ClickRecord.model_validate(c) for c in recent],
    )


@app.get("/{short_code}")
def redirect(
    short_code: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
) -> RedirectResponse:
    long_url = cache.get(short_code)
    if long_url is not None:
        log.info("cache HIT  %s (served by %s)", short_code, MACHINE_ID)
    else:
        row = (
            db.query(URLMapping)
            .filter(URLMapping.short_code == short_code)
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="short code not found")
        long_url = row.long_url
        cache.put(short_code, long_url)
        log.info("cache MISS %s (populated, served by %s)", short_code, MACHINE_ID)

    background_tasks.add_task(
        _record_click,
        short_code=short_code,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        referer=request.headers.get("referer"),
    )

    return RedirectResponse(url=long_url, status_code=302)
