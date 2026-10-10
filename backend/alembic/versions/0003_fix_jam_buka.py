"""jam_buka: ganti JSON null / array rusak menjadi SQL NULL

Upsert lama menyimpan JSON 'null' dan operator || mengubahnya menjadi array [null, ...].

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-10
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE places
        SET jam_buka = COALESCE(
            jsonb_path_query_first(jam_buka, '$[*] ? (@.type() == "object")'), NULL
        )
        WHERE jam_buka IS NOT NULL AND jsonb_typeof(jam_buka) <> 'object'
        """
    )


def downgrade() -> None:
    pass  # perbaikan data; tidak ada yang perlu dikembalikan
