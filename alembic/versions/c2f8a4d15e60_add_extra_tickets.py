"""add extra_tickets a reconciliation_jobs

Revision ID: c2f8a4d15e60
Revises: b1e7f3a92c04
Create Date: 2026-07-24 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2f8a4d15e60'
down_revision: Union[str, None] = 'b1e7f3a92c04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'reconciliation_jobs',
        sa.Column('extra_tickets', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('reconciliation_jobs', 'extra_tickets')
