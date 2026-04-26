from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class URLMapping(Base):
    # `id` doubles as our counter: base62(id) IS the short code. We also store
    # short_code as its own column so it shows up plainly in sqlite-web.
    __tablename__ = "url_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    short_code: Mapped[str | None] = mapped_column(String(16), unique=True, index=True)
    long_url: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Click(Base):
    # One row per redirect. Lives in its own table so analytics writes don't
    # contend with the read-heavy url_mappings table — the whole point of
    # Phase 2's split.
    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mapping_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("url_mappings.id"), index=True
    )
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    # IPv6 max length is 45 chars. Nullable because request.client may be None.
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    referer: Mapped[str | None] = mapped_column(String(2048))
