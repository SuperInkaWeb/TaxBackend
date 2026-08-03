"""password_hash nullable (auth 100% Auth0)

Revision ID: f7a3d21c8e40
Revises: e5b1c9d34a20
Create Date: 2026-08-01 03:00:00.000000

Fase 1 del paso a Auth0-only (expand/contract): la columna deja de ser
obligatoria porque ya no se guardan contraseñas locales. El drop de la columna
va en una migración posterior, una vez estable.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a3d21c8e40'
down_revision: Union[str, None] = 'e5b1c9d34a20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('users', 'password_hash', existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    op.alter_column('users', 'password_hash', existing_type=sa.String(length=255), nullable=False)
