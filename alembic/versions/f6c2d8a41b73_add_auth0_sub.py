"""add_auth0_sub

Revision ID: f6c2d8a41b73
Revises: e4b1a7c62d90
Create Date: 2026-07-13 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6c2d8a41b73'
down_revision: Union[str, None] = 'e4b1a7c62d90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('auth0_sub', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_users_auth0_sub'), 'users', ['auth0_sub'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_auth0_sub'), table_name='users')
    op.drop_column('users', 'auth0_sub')
