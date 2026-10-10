"""Menyusun daftar query scraping dari (kategori x wilayah).

- Wilayah level 4 (desa) / 3 (kecamatan): satu query per kata kunci.
- Wilayah level 2 (kab/kota) / 1 (provinsi): dipecah otomatis menjadi satu query per kecamatan di
  bawahnya supaya hasil tidak terpotong.
Teks query: "{kategori} di {desa}, {kecamatan}, {kab/kota}, {provinsi}".
"""
import re
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Category, Region
from app.services.region_match import RegionMatcher, norm


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class PlannedQuery:
    keyword: str
    region_kode: str
    query: str


@dataclass
class Target:
    kode: str
    names: list[str]  # nama yang sudah rapi, dari provinsi (atas) ke bawah


def pretty(nama: str) -> str:
    s = re.sub(r"\b(?:adm\.?|administrasi)(?=\s|$)", "", nama, flags=re.I)
    return " ".join(s.split()).title()


def build_plan(keywords: list[str], targets: list[Target]) -> list[PlannedQuery]:
    return [
        PlannedQuery(kw, t.kode, f"{kw} di {', '.join(reversed(t.names))}")
        for t in targets
        for kw in keywords
    ]


def dedupe_keywords(keywords: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for k in keywords:
        k = " ".join(k.split())
        if k and k.lower() not in seen:
            seen.add(k.lower())
            out.append(k)
    return out


# --- akses DB ----------------------------------------------------------------------------
def load_chain(db: Session, kode: str) -> list[Region]:
    """Wilayah terpilih beserta induknya, urut provinsi -> terpilih."""
    chain: list[Region] = []
    cur: str | None = kode
    while cur:
        r = db.get(Region, cur)
        if r is None:
            raise PlanError(f"wilayah dengan kode '{kode}' tidak ditemukan")
        chain.append(r)
        cur = r.parent_kode
    return chain[::-1]


_DISTRICTS_SQL = text(
    """
    SELECT r3.kode, r3.nama, r2.nama AS kab, r1.nama AS prov
    FROM regions r3
    JOIN regions r2 ON r3.parent_kode = r2.kode
    JOIN regions r1 ON r2.parent_kode = r1.kode
    WHERE r3.level = 3 AND (r2.kode = :k OR r1.kode = :k)
    ORDER BY r3.kode
    """
)


def load_targets(db: Session, chain: list[Region]) -> list[Target]:
    selected = chain[-1]
    if selected.level >= 3:
        return [Target(selected.kode, [pretty(r.nama) for r in chain])]
    rows = db.execute(_DISTRICTS_SQL, {"k": selected.kode}).all()
    if not rows:
        raise PlanError(
            f"tidak ada kecamatan di bawah '{selected.nama}'. Jalankan seed wilayah dengan --max-level 3 atau 4."
        )
    return [Target(r.kode, [pretty(r.prov), pretty(r.kab), pretty(r.nama)]) for r in rows]


def resolve_keywords(db: Session, category_ids: list[int], free_keywords: list[str]) -> list[str]:
    kws: list[str] = []
    if category_ids:
        rows = db.scalars(select(Category).where(Category.id.in_(category_ids)).order_by(Category.id)).all()
        missing = set(category_ids) - {c.id for c in rows}
        if missing:
            raise PlanError(f"kategori tidak ditemukan: {sorted(missing)}")
        kws += [c.keyword for c in rows]
    kws += free_keywords
    kws = dedupe_keywords(kws)
    if not kws:
        raise PlanError("pilih minimal satu kategori atau isi kata kunci")
    return kws


def plan_for_params(db: Session, params: dict, max_queries: int) -> tuple[list[PlannedQuery], list[str]]:
    chain = load_chain(db, params["region_kode"])
    keywords = resolve_keywords(db, params.get("category_ids", []), params.get("keywords", []))
    targets = load_targets(db, chain)
    plan = build_plan(keywords, targets)
    if len(plan) > max_queries:
        raise PlanError(
            f"rencana menghasilkan {len(plan)} query (> batas {max_queries}). "
            "Pilih wilayah yang lebih sempit atau kurangi kategori."
        )
    return plan, keywords


def build_matcher(db: Session, chain: list[Region]) -> RegionMatcher:
    selected = chain[-1]
    districts: dict[str, str] = {}
    if selected.level <= 2:
        rows = db.execute(_DISTRICTS_SQL, {"k": selected.kode}).all()
        districts = {norm(r.nama): r.kode for r in rows}
    return RegionMatcher(level=selected.level, names=[r.nama for r in chain], districts=districts)
