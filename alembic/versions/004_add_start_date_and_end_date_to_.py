"""add start_date and end_date to experience

Revision ID: 903548454509
Revises: baaaaf0d3ef6
Create Date: 2025-06-04 22:42:48.962612

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '903548454509'
down_revision: Union[str, None] = 'baaaaf0d3ef6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("experience", sa.Column("start_date", sa.String(), nullable=True))
    op.add_column("experience", sa.Column("end_date", sa.String(), nullable=True))
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("experience", "start_date")
    op.drop_column("experience", "end_date")
    pass
