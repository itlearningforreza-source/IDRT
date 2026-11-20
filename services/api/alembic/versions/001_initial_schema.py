"""initial_schema

Revision ID: 001
Revises: 
Create Date: 2026-11-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    account_type_enum = postgresql.ENUM('ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE', name='accounttype')
    account_type_enum.create(op.get_bind(), checkfirst=True)
    
    entry_status_enum = postgresql.ENUM('DRAFT', 'POSTED', 'REVERSED', name='entrystatus')
    entry_status_enum.create(op.get_bind(), checkfirst=True)

    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('address', sa.String(length=42), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('username', sa.String(length=100), nullable=True),
        sa.Column('hashed_password', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, default=False),
        sa.Column('roles', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('address'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username'),
    )
    op.create_index('ix_users_address', 'users', ['address'], unique=True)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_username', 'users', ['username'], unique=True)

    # API Keys table
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key_hash', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('scopes', sa.Text(), nullable=True),
        sa.Column('rate_limit', sa.Integer(), nullable=False, default=1000),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash'),
    )
    op.create_index('ix_api_keys_user_id', 'api_keys', ['user_id'])
    op.create_index('ix_api_keys_key_hash', 'api_keys', ['key_hash'], unique=True)

    # Audit Logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('resource_id', sa.String(length=100), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, default=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_resource_type', 'audit_logs', ['resource_type'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])

    # Accounts table (Chart of Accounts)
    op.create_table(
        'accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('type', sa.Enum('ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE', name='accounttype'), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, default='IDR'),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['parent_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index('ix_accounts_type_active', 'accounts', ['type', 'is_active'])
    op.create_index('ix_accounts_parent_id', 'accounts', ['parent_id'])

    # Journal Entries table
    op.create_table(
        'journal_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entry_number', sa.BigInteger(), nullable=False),
        sa.Column('entry_date', sa.Date(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('reference_type', sa.String(length=50), nullable=True),
        sa.Column('reference_id', sa.String(length=100), nullable=True),
        sa.Column('status', sa.Enum('DRAFT', 'POSTED', 'REVERSED', name='entrystatus'), nullable=False, default='DRAFT'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('posted_at', sa.DateTime(), nullable=True),
        sa.Column('posted_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reversed_at', sa.DateTime(), nullable=True),
        sa.Column('reversed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reversal_reason', sa.Text(), nullable=True),
        sa.Column('prev_hash', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['posted_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reversed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entry_number'),
    )
    op.create_index('ix_journal_entry_date_status', 'journal_entries', ['entry_date', 'status'])
    op.create_index('ix_journal_entry_ref', 'journal_entries', ['reference_type', 'reference_id'])
    op.create_index('ix_journal_entry_number', 'journal_entries', ['entry_number'], unique=True)

    # Journal Lines table
    op.create_table(
        'journal_lines',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('journal_entry_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('debit', sa.Numeric(precision=78, scale=0), nullable=False, default=0),
        sa.Column('credit', sa.Numeric(precision=78, scale=0), nullable=False, default=0),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('debit = 0 OR credit = 0', name='ck_journal_line_one_sided'),
        sa.CheckConstraint('debit >= 0 AND credit >= 0', name='ck_journal_line_non_negative'),
        sa.UniqueConstraint('journal_entry_id', 'line_number', name='uq_journal_line_number'),
    )
    op.create_index('ix_journal_lines_entry_id', 'journal_lines', ['journal_entry_id'])
    op.create_index('ix_journal_lines_account_id', 'journal_lines', ['account_id'])

    # Reconciliations table
    op.create_table(
        'reconciliations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reconciliation_date', sa.Date(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('expected_value', sa.Numeric(precision=78, scale=0), nullable=False),
        sa.Column('actual_value', sa.Numeric(precision=78, scale=0), nullable=False),
        sa.Column('difference', sa.Numeric(precision=78, scale=0), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, default='OPEN'),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reconciliation_date', 'type', name='uq_reconciliation_date_type'),
    )
    op.create_index('ix_reconciliations_date_type', 'reconciliations', ['reconciliation_date', 'type'])
    op.create_index('ix_reconciliations_status', 'reconciliations', ['status'])

    # Financial Snapshots table
    op.create_table(
        'financial_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('snapshot_type', sa.String(length=20), nullable=False),
        sa.Column('total_fiat_reserve', sa.Numeric(precision=78, scale=0), nullable=False, default=0),
        sa.Column('customer_liability_reserve', sa.Numeric(precision=78, scale=0), nullable=False, default=0),
        sa.Column('operational_cash', sa.Numeric(precision=78, scale=0), nullable=False, default=0),
        sa.Column('fee_revenue_reserve', sa.Numeric(precision=78, scale=0), nullable=False, default=0),
        sa.Column('pending_deposits', sa.Numeric(precision=78, scale=0), nullable=False, default=0),
        sa.Column('encumbered_reserve', sa.Numeric(precision=78, scale=0), nullable=False, default=0),
        sa.Column('total_token_liability', sa.Numeric(precision=78, scale=0), nullable=False, default=0),
        sa.Column('pending_withdrawals', sa.Numeric(precision=78, scale=0), nullable=False, default=0),
        sa.Column('onchain_total_supply', sa.Numeric(precision=78, scale=0), nullable=False, default=0),
        sa.Column('onchain_reserve_balance', sa.Numeric(precision=78, scale=0), nullable=False, default=0),
        sa.Column('collateralization_ratio_bps', sa.Integer(), nullable=True),
        sa.Column('prev_snapshot_hash', sa.String(length=64), nullable=True),
        sa.Column('snapshot_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('snapshot_date', 'snapshot_type', name='uq_snapshot_date_type'),
    )
    op.create_index('ix_financial_snapshots_date_type', 'financial_snapshots', ['snapshot_date', 'snapshot_type'])

    # Token Events table
    op.create_table(
        'token_events',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('tx_hash', sa.String(length=66), nullable=False),
        sa.Column('block_number', sa.BigInteger(), nullable=False),
        sa.Column('log_index', sa.Integer(), nullable=False),
        sa.Column('chain_id', sa.Integer(), nullable=False),
        sa.Column('from_address', sa.String(length=42), nullable=True),
        sa.Column('to_address', sa.String(length=42), nullable=True),
        sa.Column('amount', sa.Numeric(precision=78, scale=0), nullable=True),
        sa.Column('caller', sa.String(length=42), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tx_hash', 'log_index', 'chain_id', name='uq_token_events_tx_log_chain'),
    )
    op.create_index('ix_token_events_tx_hash', 'token_events', ['tx_hash'])
    op.create_index('ix_token_events_block_number', 'token_events', ['block_number'])
    op.create_index('ix_token_events_chain_id', 'token_events', ['chain_id'])
    op.create_index('ix_token_events_timestamp', 'token_events', ['timestamp'])

    # Reserve Events table
    op.create_table(
        'reserve_events',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('tx_hash', sa.String(length=66), nullable=False),
        sa.Column('block_number', sa.BigInteger(), nullable=False),
        sa.Column('chain_id', sa.Integer(), nullable=False),
        sa.Column('fiat_balance', sa.Numeric(precision=78, scale=0), nullable=True),
        sa.Column('proof_hash', sa.String(length=66), nullable=True),
        sa.Column('submitted_by', sa.String(length=42), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tx_hash', 'block_number', 'chain_id', name='uq_reserve_events_tx_block_chain'),
    )
    op.create_index('ix_reserve_events_tx_hash', 'reserve_events', ['tx_hash'])
    op.create_index('ix_reserve_events_timestamp', 'reserve_events', ['timestamp'])

    # Bridge Events table
    op.create_table(
        'bridge_events',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('tx_hash', sa.String(length=66), nullable=False),
        sa.Column('block_number', sa.BigInteger(), nullable=False),
        sa.Column('chain_id', sa.Integer(), nullable=False),
        sa.Column('bridge_nonce', sa.BigInteger(), nullable=False),
        sa.Column('src_chain', sa.Integer(), nullable=True),
        sa.Column('dst_chain', sa.Integer(), nullable=True),
        sa.Column('sender', sa.String(length=42), nullable=True),
        sa.Column('recipient', sa.String(length=42), nullable=True),
        sa.Column('amount', sa.Numeric(precision=78, scale=0), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tx_hash', 'block_number', 'chain_id', name='uq_bridge_events_tx_block_chain'),
    )
    op.create_index('ix_bridge_events_tx_hash', 'bridge_events', ['tx_hash'])
    op.create_index('ix_bridge_events_nonce', 'bridge_events', ['bridge_nonce'])
    op.create_index('ix_bridge_events_timestamp', 'bridge_events', ['timestamp'])

    # KYC Profiles table
    op.create_table(
        'kyc_profiles',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tier', sa.Enum('TIER_0', 'TIER_1', 'TIER_2', 'TIER_3', name='kyctier'), nullable=False, default='TIER_0'),
        sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', name='kycstatus'), nullable=False, default='PENDING'),
        sa.Column('risk_level', sa.Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='risklevel'), nullable=False, default='LOW'),
        sa.Column('kyc_expiry', sa.DateTime(), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('verified_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=False, default={}),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['verified_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('user_id'),
    )

    # Sanctions Screening table
    op.create_table(
        'sanctions_screening',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('screening_type', sa.String(length=50), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('result', sa.Enum('CLEAR', 'HIT', 'REVIEW', name='screeningresult'), nullable=False),
        sa.Column('match_details', postgresql.JSONB(), nullable=True),
        sa.Column('screened_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sanctions_user_id', 'sanctions_screening', ['user_id'])
    op.create_index('ix_sanctions_screened_at', 'sanctions_screening', ['screened_at'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('sanctions_screening')
    op.drop_table('kyc_profiles')
    op.drop_table('bridge_events')
    op.drop_table('reserve_events')
    op.drop_table('token_events')
    op.drop_table('financial_snapshots')
    op.drop_table('reconciliations')
    op.drop_table('journal_lines')
    op.drop_table('journal_entries')
    op.drop_table('accounts')
    op.drop_table('audit_logs')
    op.drop_table('api_keys')
    op.drop_table('users')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS screeningresult')
    op.execute('DROP TYPE IF EXISTS risklevel')
    op.execute('DROP TYPE IF EXISTS kycstatus')
    op.execute('DROP TYPE IF EXISTS kyctier')
    op.execute('DROP TYPE IF EXISTS entrystatus')
    op.execute('DROP TYPE IF EXISTS accounttype')
