from sqlalchemy import ForeignKey, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 1 = provinsi, 2 = kabupaten/kota, 3 = kecamatan, 4 = desa/kelurahan
LEVELS = {1: "provinsi", 2: "kabupaten", 3: "kecamatan", 4: "desa"}


class Region(Base):
    __tablename__ = "regions"

    kode: Mapped[str] = mapped_column(String(10), primary_key=True)
    nama: Mapped[str] = mapped_column(String(255))
    level: Mapped[int] = mapped_column(SmallInteger)
    parent_kode: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("regions.kode"), nullable=True
    )

    __table_args__ = (Index("ix_regions_level_parent", "level", "parent_kode"),)
