from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .db import Base, SessionLocal, engine, get_session
from .encoding import encode
from .models import Click, URLMapping
from .schemas import ClickRecord, ShortenRequest, ShortenResponse, StatsResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="URL Shortener — Phase 2",
    description=(
        "FastAPI + SQLite, base62 counter codes, with split analytics: every "
        "redirect fires a fire-and-forget click write so the 302 is never "
        "blocked by an analytics INSERT."
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
    mapping_id: int,
    ip: str | None,
    user_agent: str | None,
    referer: str | None,
) -> None:
    # Runs AFTER the 302 has been sent. Opens its own session because the
    # request-scoped session is already closed by then. If this insert fails,
    # the user has already been redirected — analytics drift, no user impact.
    db = SessionLocal()
    try:
        db.add(
            Click(
                mapping_id=mapping_id,
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
    row = db.query(URLMapping).filter(URLMapping.short_code == short_code).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="short code not found")

    background_tasks.add_task(
        _record_click,
        mapping_id=row.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        referer=request.headers.get("referer"),
    )

    # 302 (not 301): browsers don't cache it, so every click hits the server.
    # Phase 2 leverages this — every hit becomes one row in `clicks`.
    return RedirectResponse(url=row.long_url, status_code=302)
