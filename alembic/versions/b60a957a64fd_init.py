"""init

Revision ID: b60a957a64fd
Revises:
Create Date: 2026-06-27 19:45:18.530342

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b60a957a64fd'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('companies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre_razon_social', sa.String(length=200), nullable=False),
    sa.Column('ruc', sa.String(length=11), nullable=False),
    sa.Column('status', sa.Enum('activo', 'inactivo', name='companystatus'), nullable=False),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], name='fk_companies_approved_by', use_alter=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_companies_id'), 'companies', ['id'], unique=False)
    op.create_index(op.f('ix_companies_ruc'), 'companies', ['ruc'], unique=True)
    op.create_table('company_file_mappings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('delimiter', sa.String(length=5), nullable=False),
    sa.Column('encoding', sa.String(length=20), nullable=False),
    sa.Column('has_header', sa.Boolean(), nullable=False),
    sa.Column('skip_rows', sa.Integer(), nullable=False),
    sa.Column('col_tipo_cdp', sa.Integer(), nullable=True),
    sa.Column('col_serie', sa.Integer(), nullable=True),
    sa.Column('col_numero', sa.Integer(), nullable=True),
    sa.Column('col_importe_total', sa.Integer(), nullable=True),
    sa.Column('detection_confidence', sa.Integer(), nullable=True),
    sa.Column('sample_rows', sa.JSON(), nullable=True),
    sa.Column('confirmed_by_user', sa.Boolean(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('company_id')
    )
    op.create_index(op.f('ix_company_file_mappings_id'), 'company_file_mappings', ['id'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('nombre', sa.String(length=150), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.Enum('superadmin', 'admin', 'empresa', 'usuario', name='userrole'), nullable=False),
    sa.Column('status', sa.Enum('activo', 'inactivo', 'pendiente', name='userstatus'), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_table('access_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('nombre', sa.String(length=150), nullable=False),
    sa.Column('empresa_nombre', sa.String(length=200), nullable=False),
    sa.Column('ruc', sa.String(length=11), nullable=False),
    sa.Column('telefono', sa.String(length=20), nullable=True),
    sa.Column('mensaje', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('pendiente', 'aprobado', 'rechazado', name='accessrequeststatus'), nullable=False),
    sa.Column('reviewed_by_id', sa.Integer(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_access_requests_email'), 'access_requests', ['email'], unique=False)
    op.create_index(op.f('ix_access_requests_id'), 'access_requests', ['id'], unique=False)
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('entity_type', sa.String(length=50), nullable=True),
    sa.Column('entity_id', sa.Integer(), nullable=True),
    sa.Column('details', sa.JSON(), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)
    op.create_table('company_credentials',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('usuario_sol', sa.String(length=50), nullable=False),
    sa.Column('clave_sol_enc', sa.Text(), nullable=False),
    sa.Column('client_id', sa.String(length=100), nullable=False),
    sa.Column('client_secret_enc', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('company_id')
    )
    op.create_index(op.f('ix_company_credentials_id'), 'company_credentials', ['id'], unique=False)
    op.create_table('reconciliation_jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=False),
    sa.Column('periodo', sa.String(length=6), nullable=False),
    sa.Column('tipo_libro', sa.Enum('compras', 'ventas', name='tipolibro'), nullable=False),
    sa.Column('status', sa.Enum('en_cola', 'procesando', 'completado', 'error', name='jobstatus'), nullable=False),
    sa.Column('empresa_filename', sa.String(length=255), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reconciliation_jobs_company_id'), 'reconciliation_jobs', ['company_id'], unique=False)
    op.create_index(op.f('ix_reconciliation_jobs_id'), 'reconciliation_jobs', ['id'], unique=False)
    op.create_table('reconciliation_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('escenario_a_count', sa.Integer(), nullable=False),
    sa.Column('escenario_b_count', sa.Integer(), nullable=False),
    sa.Column('escenario_c_count', sa.Integer(), nullable=False),
    sa.Column('igv_diferencia_total', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('tiene_alertas_rojas', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['reconciliation_jobs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_id')
    )
    op.create_index(op.f('ix_reconciliation_results_id'), 'reconciliation_results', ['id'], unique=False)
    op.create_table('report_files',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('storage_path', sa.String(length=500), nullable=False),
    sa.Column('file_size_bytes', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['reconciliation_jobs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_id')
    )
    op.create_index(op.f('ix_report_files_id'), 'report_files', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_report_files_id'), table_name='report_files')
    op.drop_table('report_files')
    op.drop_index(op.f('ix_reconciliation_results_id'), table_name='reconciliation_results')
    op.drop_table('reconciliation_results')
    op.drop_index(op.f('ix_reconciliation_jobs_id'), table_name='reconciliation_jobs')
    op.drop_index(op.f('ix_reconciliation_jobs_company_id'), table_name='reconciliation_jobs')
    op.drop_table('reconciliation_jobs')
    op.drop_index(op.f('ix_company_credentials_id'), table_name='company_credentials')
    op.drop_table('company_credentials')
    op.drop_index(op.f('ix_audit_logs_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_access_requests_id'), table_name='access_requests')
    op.drop_index(op.f('ix_access_requests_email'), table_name='access_requests')
    op.drop_table('access_requests')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_company_file_mappings_id'), table_name='company_file_mappings')
    op.drop_table('company_file_mappings')
    op.drop_index(op.f('ix_companies_ruc'), table_name='companies')
    op.drop_index(op.f('ix_companies_id'), table_name='companies')
    op.drop_table('companies')
