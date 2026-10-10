"""Seed kategori preset. Idempotent: python -m app.scripts.seed_categories"""
from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal
from app.logging import get_logger, setup_logging
from app.models import Category

PRESETS = [
    ("Toko Kecantikan", "toko kecantikan"),
    ("Toko Kosmetik", "toko kosmetik"),
    ("Toko Skincare", "toko skincare"),
    ("Salon", "salon"),
    ("Barbershop", "barbershop"),
    ("Klinik Kecantikan", "klinik kecantikan"),
    ("Spa", "spa"),
    ("Minimarket", "minimarket"),
    ("Supermarket", "supermarket"),
    ("Apotek", "apotek"),
    ("Toko Obat", "toko obat"),
    ("Bengkel", "bengkel"),
    ("Laundry", "laundry"),
    ("Kafe", "kafe"),
    ("Rumah Makan", "rumah makan"),
    ("Toko Roti", "toko roti"),
    ("Toko Kelontong", "toko kelontong"),
    ("Toko Pakaian", "toko pakaian"),
    ("Toko Elektronik", "toko elektronik"),
    ("Toko Bangunan", "toko bangunan"),
    ("Toko Ponsel", "toko handphone"),
    ("Toko Buku", "toko buku"),
    ("Toko Perlengkapan Bayi", "toko perlengkapan bayi"),
    ("Toko Hewan Peliharaan", "pet shop"),
    ("Optik", "optik"),
]


def main() -> None:
    setup_logging()
    log = get_logger("seed_categories")
    with SessionLocal() as db:
        stmt = insert(Category).values([{"nama": n, "keyword": k} for n, k in PRESETS])
        stmt = stmt.on_conflict_do_update(
            index_elements=["nama"], set_={"keyword": stmt.excluded.keyword}
        )
        db.execute(stmt)
        db.commit()
    log.info("categories_seeded", count=len(PRESETS))


if __name__ == "__main__":
    main()
