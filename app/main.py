from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .db import Base, engine, get_session
from .encoding import encode
from .models import URLMapping
from .schemas import ShortenRequest, ShortenResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="URL Shortener — Phase 1",
    description=(
        "Single FastAPI process + SQLite, counter-based base62 short codes. "
        "Drive traffic from /docs and watch rows appear in sqlite-web."
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


@app.get("/{short_code}")
def redirect(short_code: str, db: Session = Depends(get_session)) -> RedirectResponse:
    row = db.query(URLMapping).filter(URLMapping.short_code == short_code).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="short code not found")
    # 302 (not 301): browsers don't cache it, so every click hits the server.
    # That matters for Phase 2 when we add click analytics.
    return RedirectResponse(url=row.long_url, status_code=302)
