"""add location to experience and education

Revision ID: c5fa4f0bf0c1
Revises: 903548454509
Create Date: 2026-07-19 22:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5fa4f0bf0c1"
down_revision: Union[str, None] = "903548454509"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("experience", sa.Column("location", sa.String(), nullable=True))
    op.add_column("education", sa.Column("location", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("education", "location")
    op.drop_column("experience", "location")
