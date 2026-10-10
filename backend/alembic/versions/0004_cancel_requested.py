"""scrape_jobs.cancel_requested (pembatalan lewat database, menggantikan Redis)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scrape_jobs",
        sa.Column("cancel_requested", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("scrape_jobs", "cancel_requested")
