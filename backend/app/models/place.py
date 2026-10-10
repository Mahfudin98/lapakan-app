from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    google_place_key: Mapped[str] = mapped_column(String(255), unique=True)
    nama: Mapped[str] = mapped_column(String(500))
    kategori_google: Mapped[str | None] = mapped_column(String(255))
    rating: Mapped[float | None] = mapped_column(Float, index=True)
    review_count: Mapped[int | None] = mapped_column(Integer, index=True)
    alamat: Mapped[str | None] = mapped_column(Text)
    telepon: Mapped[str | None] = mapped_column(String(64))
    website: Mapped[str | None] = mapped_column(Text)
    maps_url: Mapped[str | None] = mapped_column(Text)
    # GIST index dibuat eksplisit di migrasi
    geom = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=True
    )
    # none_as_null: None disimpan sebagai SQL NULL, bukan JSON 'null' (operator || menjadikan 'null'||{} array)
    jam_buka: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    status_bisnis: Mapped[str | None] = mapped_column(String(32))
    region_kode: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("regions.kode"), index=True
    )
    in_region: Mapped[bool | None] = mapped_column(Boolean)  # NULL = unknown
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
