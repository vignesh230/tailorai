"""add screening column to analyses

Revision ID: 0002_add_screening
Revises: 0001_initial
Create Date: 2026-08-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_add_screening"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column(
            "screening",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("analyses", "screening", server_default=None)


def downgrade() -> None:
    op.drop_column("analyses", "screening")
