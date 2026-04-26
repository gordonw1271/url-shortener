from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class ShortenRequest(BaseModel):
    url: HttpUrl


class ShortenResponse(BaseModel):
    short_code: str
    short_url: str
    long_url: str


class ClickRecord(BaseModel):
    # from_attributes lets FastAPI serialize SQLAlchemy ORM objects directly
    # against this schema (reads attributes instead of dict keys).
    model_config = ConfigDict(from_attributes=True)

    clicked_at: datetime
    ip: str | None = None
    user_agent: str | None = None
    referer: str | None = None


class StatsResponse(BaseModel):
    short_code: str
    long_url: str
    total_clicks: int
    recent: list[ClickRecord]
