"""query cache

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "query_cache",
        sa.Column("query_key", sa.String(500), primary_key=True),
        sa.Column("detail", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("max_results", sa.Integer, nullable=False),
        sa.Column("complete", sa.Boolean, nullable=False),
        sa.Column("place_ids", postgresql.JSONB, nullable=False),
        sa.Column("scraped_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("query_cache")
