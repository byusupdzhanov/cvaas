"""add ordering to projects and recommendations and levels to skills

Revision ID: b8ef21f15f42
Revises: c5fa4f0bf0c1
Create Date: 2026-07-20 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8ef21f15f42"
down_revision: Union[str, None] = "c5fa4f0bf0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("skills", sa.Column("level", sa.Integer(), nullable=True, server_default="3"))
    op.add_column("projects", sa.Column("position", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("recommendations", sa.Column("position", sa.Integer(), nullable=True, server_default="0"))


def downgrade() -> None:
    op.drop_column("recommendations", "position")
    op.drop_column("projects", "position")
    op.drop_column("skills", "level")
