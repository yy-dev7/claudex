"""add sandbox_provider to user_settings and chats

Revision ID: a1b2c3d4e5f6
Revises: 2306b1fb0742
Create Date: 2025-12-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '2306b1fb0742'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_settings',
        sa.Column('sandbox_provider', sa.String(length=20), nullable=False, server_default='e2b')
    )
    op.add_column(
        'chats',
        sa.Column('sandbox_provider', sa.String(length=20), nullable=True)
    )
    op.execute("UPDATE chats SET sandbox_provider = 'e2b' WHERE sandbox_id IS NOT NULL")


def downgrade() -> None:
    op.drop_column('chats', 'sandbox_provider')
    op.drop_column('user_settings', 'sandbox_provider')
