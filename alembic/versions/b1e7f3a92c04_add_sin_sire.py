"""add sin_sire a reconciliation_jobs

Revision ID: b1e7f3a92c04
Revises: a9c4e7d21f85
Create Date: 2026-07-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1e7f3a92c04'
down_revision: Union[str, None] = 'a9c4e7d21f85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'reconciliation_jobs',
        sa.Column('sin_sire', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('reconciliation_jobs', 'sin_sire')
