from datetime import datetime

from sqlalchemy import DateTime, Integer, String
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
