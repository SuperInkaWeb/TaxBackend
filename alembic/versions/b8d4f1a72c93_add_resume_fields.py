"""add_resume_fields

Revision ID: b8d4f1a72c93
Revises: a1f3e8c92b47
Create Date: 2026-07-08 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8d4f1a72c93'
down_revision: Union[str, None] = 'a1f3e8c92b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reconciliation_jobs', sa.Column('empresa_file_path', sa.String(length=500), nullable=True))
    op.add_column('reconciliation_jobs', sa.Column('num_ticket', sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column('reconciliation_jobs', 'num_ticket')
    op.drop_column('reconciliation_jobs', 'empresa_file_path')
