from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QueryCache(Base):
    """Cache hasil pencarian: query yang sama dalam N hari tidak di-scrape ulang."""

    __tablename__ = "query_cache"

    query_key: Mapped[str] = mapped_column(String(500), primary_key=True)  # query ternormalisasi
    detail: Mapped[bool] = mapped_column(Boolean, default=False)
    max_results: Mapped[int] = mapped_column(Integer)  # batas yang dipakai saat scraping
    complete: Mapped[bool] = mapped_column(Boolean)  # True = daftar sudah habis (bukan terpotong batas)
    place_ids: Mapped[list] = mapped_column(JSONB)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
