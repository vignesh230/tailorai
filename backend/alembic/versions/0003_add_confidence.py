"""add confidence column to analyses

Revision ID: 0003_add_confidence
Revises: 0002_add_screening
Create Date: 2026-08-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_add_confidence"
down_revision = "0002_add_screening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column(
            "confidence",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("analyses", "confidence", server_default=None)


def downgrade() -> None:
    op.drop_column("analyses", "confidence")
