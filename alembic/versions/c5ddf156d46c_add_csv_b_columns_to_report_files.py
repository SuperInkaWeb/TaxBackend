"""add_csv_b_columns_to_report_files

Revision ID: c5ddf156d46c
Revises: b60a957a64fd
Create Date: 2026-06-28 16:40:33.692907

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5ddf156d46c'
down_revision: Union[str, None] = 'b60a957a64fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_foreign_key('fk_companies_approved_by', 'companies', 'users', ['approved_by_id'], ['id'], use_alter=True)
    op.alter_column('company_file_mappings', 'detection_confidence',
               existing_type=sa.INTEGER(),
               type_=sa.Float(),
               existing_nullable=True)
    op.add_column('report_files', sa.Column('csv_b_storage_path', sa.String(length=500), nullable=True))
    op.add_column('report_files', sa.Column('csv_b_file_size_bytes', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('report_files', 'csv_b_file_size_bytes')
    op.drop_column('report_files', 'csv_b_storage_path')
    op.alter_column('company_file_mappings', 'detection_confidence',
               existing_type=sa.Float(),
               type_=sa.INTEGER(),
               existing_nullable=True)
    op.drop_constraint('fk_companies_approved_by', 'companies', type_='foreignkey')
