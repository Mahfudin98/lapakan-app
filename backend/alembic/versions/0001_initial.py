"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-10
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "regions",
        sa.Column("kode", sa.String(10), primary_key=True),
        sa.Column("nama", sa.String(255), nullable=False),
        sa.Column("level", sa.SmallInteger, nullable=False),
        sa.Column("parent_kode", sa.String(10), sa.ForeignKey("regions.kode")),
    )
    op.create_index("ix_regions_level_parent", "regions", ["level", "parent_kode"])

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("nama", sa.String(100), nullable=False, unique=True),
        sa.Column("keyword", sa.String(100), nullable=False),
    )

    op.create_table(
        "places",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("google_place_key", sa.String(255), nullable=False, unique=True),
        sa.Column("nama", sa.String(500), nullable=False),
        sa.Column("kategori_google", sa.String(255)),
        sa.Column("rating", sa.Float),
        sa.Column("review_count", sa.Integer),
        sa.Column("alamat", sa.Text),
        sa.Column("telepon", sa.String(64)),
        sa.Column("website", sa.Text),
        sa.Column("maps_url", sa.Text),
        sa.Column(
            "geom",
            geoalchemy2.Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        ),
        sa.Column("jam_buka", postgresql.JSONB),
        sa.Column("status_bisnis", sa.String(32)),
        sa.Column("region_kode", sa.String(10), sa.ForeignKey("regions.kode")),
        sa.Column("in_region", sa.Boolean),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_scraped_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_places_geom", "places", ["geom"], postgresql_using="gist")
    op.create_index("ix_places_rating", "places", ["rating"])
    op.create_index("ix_places_review_count", "places", ["review_count"])
    op.create_index("ix_places_region_kode", "places", ["region_kode"])

    op.create_table(
        "scrape_jobs",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("params", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("progress", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_scrape_jobs_status", "scrape_jobs", ["status"])

    op.create_table(
        "job_places",
        sa.Column(
            "job_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scrape_jobs.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "place_id", sa.BigInteger,
            sa.ForeignKey("places.id", ondelete="CASCADE"), primary_key=True,
        ),
    )
    op.create_index("ix_job_places_place_id", "job_places", ["place_id"])


def downgrade() -> None:
    op.drop_table("job_places")
    op.drop_table("scrape_jobs")
    op.drop_table("places")
    op.drop_table("categories")
    op.drop_table("regions")
