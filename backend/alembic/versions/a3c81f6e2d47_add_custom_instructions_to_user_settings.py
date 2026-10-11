"""add custom instructions to user settings

Revision ID: a3c81f6e2d47
Revises: f00fae5c4eaf
Create Date: 2026-10-11 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c81f6e2d47'
down_revision: Union[str, Sequence[str], None] = 'f00fae5c4eaf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user_settings', sa.Column('custom_instructions', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('user_settings', 'custom_instructions')
