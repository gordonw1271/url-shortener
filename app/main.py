import logging
import sys
from contextlib import asynccontextmanager

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

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from . import cache
from .db import Base, SessionLocal, engine, get_session
from .encoding import encode
from .models import Click, URLMapping
from .schemas import ClickRecord, ShortenRequest, ShortenResponse, StatsResponse

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="URL Shortener — Phase 3",
    description=(
        "FastAPI + SQLite + Redis read-through cache. The redirect path tries "
        "Redis first; on miss it falls back to the DB and populates the cache. "
        "Cache failures degrade gracefully — Redis is an optimization, not a "
        "dependency."
    ),
    lifespan=lifespan,
)


@app.post("/shorten", response_model=ShortenResponse, status_code=201)
def shorten(
    payload: ShortenRequest,
    request: Request,
    db: Session = Depends(get_session),
) -> ShortenResponse:
    row = URLMapping(long_url=str(payload.url))
    db.add(row)
    # flush() sends the INSERT and populates row.id without committing — we
    # need the id to compute the short_code, then commit both in one txn.
    db.flush()
    row.short_code = encode(row.id)
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
    # Runs AFTER the 302 has been sent. Opens its own session because the
    # request-scoped session is already closed by then. Looks up mapping_id
    # by short_code so the redirect handler doesn't need to do a DB SELECT
    # on cache HIT just to satisfy the click write.
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
        log.info("cache HIT  %s", short_code)
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
        log.info("cache MISS %s (populated)", short_code)

    background_tasks.add_task(
        _record_click,
        short_code=short_code,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        referer=request.headers.get("referer"),
    )

    # 302 (not 301): browsers don't cache it, so every click reaches us and
    # gets recorded in `clicks`.
    return RedirectResponse(url=long_url, status_code=302)
