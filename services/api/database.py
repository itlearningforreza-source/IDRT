"""
IDRC API Database
Async SQLAlchemy models and session management
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text, BigInteger, Numeric,
    ForeignKey, Index, UniqueConstraint, select, func, Date, CheckConstraint
)
import enum
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine, AsyncEngine
)
from sqlalchemy.orm import DeclarativeBase, relationship, declared_attr
from sqlalchemy.dialects.postgresql import UUID
import uuid


# ============================================================
# Base Model
# ============================================================

class Base(DeclarativeBase):
    pass


# ============================================================
# Models
# ============================================================

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    address = Column(String(42), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    username = Column(String(100), unique=True, nullable=True, index=True)
    hashed_password = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    roles = Column(Text, nullable=True)  # JSON array of roles
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    # Relationships
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    key_hash = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    scopes = Column(Text, nullable=True)  # JSON array of scopes
    rate_limit = Column(Integer, default=1000)  # requests per minute
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="api_keys")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=False, index=True)
    resource_id = Column(String(100), nullable=True, index=True)
    details = Column(Text, nullable=True)  # JSON
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="audit_logs")


class TokenEvent(Base):
    __tablename__ = "token_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(50), nullable=False, index=True)  # Mint, Burn, Transfer, Approve, etc.
    tx_hash = Column(String(66), unique=True, nullable=False, index=True)
    block_number = Column(BigInteger, nullable=False, index=True)
    log_index = Column(Integer, nullable=False)
    chain_id = Column(Integer, nullable=False, index=True)
    from_address = Column(String(42), nullable=True, index=True)
    to_address = Column(String(42), nullable=True, index=True)
    amount = Column(Numeric(precision=78, scale=0), nullable=True)  # wei
    caller = Column(String(42), nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_token_event_tx_log"),
        Index("ix_token_event_chain_block", "chain_id", "block_number"),
    )


class MultisigTransaction(Base):
    __tablename__ = "multisig_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(BigInteger, nullable=False, index=True)
    chain_id = Column(Integer, nullable=False, index=True)
    multisig_address = Column(String(42), nullable=False, index=True)
    to_address = Column(String(42), nullable=False)
    value = Column(Numeric(precision=78, scale=0), nullable=False)
    data = Column(Text, nullable=True)
    executed = Column(Boolean, default=False, index=True)
    confirmations = Column(Integer, default=0)
    threshold = Column(Integer, nullable=False)
    proposed_by = Column(String(42), nullable=False)
    submit_tx_hash = Column(String(66), nullable=True, index=True)
    execute_tx_hash = Column(String(66), nullable=True, index=True)
    submission_time = Column(DateTime, nullable=False)
    execution_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MultisigConfirmation(Base):
    __tablename__ = "multisig_confirmations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(BigInteger, nullable=False, index=True)
    chain_id = Column(Integer, nullable=False, index=True)
    multisig_address = Column(String(42), nullable=False, index=True)
    confirmer = Column(String(42), nullable=False, index=True)
    tx_hash = Column(String(66), nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("transaction_id", "chain_id", "multisig_address", "confirmer", name="uq_multisig_confirmation"),
    )


class ReserveUpdate(Base):
    __tablename__ = "reserve_updates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_id = Column(Integer, nullable=False, index=True)
    reserve_address = Column(String(42), nullable=False, index=True)
    update_type = Column(String(50), nullable=False)  # oracle_update, audit_proof
    fiat_balance_idr = Column(Numeric(precision=78, scale=0), nullable=True)
    proof_hash = Column(String(66), nullable=True)
    submitted_by = Column(String(42), nullable=False, index=True)
    tx_hash = Column(String(66), nullable=False, index=True)
    block_number = Column(BigInteger, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BridgeEvent(Base):
    __tablename__ = "bridge_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(50), nullable=False, index=True)  # Locked, Released, Relayed
    bridge_nonce = Column(BigInteger, nullable=False, index=True)
    src_chain_id = Column(Integer, nullable=False, index=True)
    dst_chain_id = Column(Integer, nullable=False, index=True)
    sender = Column(String(42), nullable=True, index=True)
    recipient = Column(String(42), nullable=True, index=True)
    amount = Column(Numeric(precision=78, scale=0), nullable=False)
    tx_hash = Column(String(66), nullable=False, index=True)
    block_number = Column(BigInteger, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    processed = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("bridge_nonce", "src_chain_id", "event_type", name="uq_bridge_event"),
        Index("ix_bridge_event_chains", "src_chain_id", "dst_chain_id"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level = Column(String(20), nullable=False, index=True)  # INFO, WARNING, CRITICAL
    code = Column(String(50), nullable=False, index=True)
    message = Column(Text, nullable=False)
    chain_id = Column(Integer, nullable=True, index=True)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(100), nullable=True)
    acknowledged = Column(Boolean, default=False, index=True)
    acknowledged_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)



# ============================================================
# Financial Ledger Models (Double-Entry Accounting)
# ============================================================

class AccountType(enum.Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class EntryStatus(enum.Enum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class Account(Base):
    """Chart of Accounts - Double-entry accounting accounts"""
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(20), unique=True, nullable=False, index=True)  # e.g., '1010', '2010', '3010'
    name = Column(String(100), nullable=False)
    type = Column(SQLEnum(AccountType), nullable=False, index=True)
    currency = Column(String(3), nullable=False, default="IDR")
    parent_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True, index=True)
    is_active = Column(Boolean, default=True, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Self-referential relationship for hierarchical accounts
    parent = relationship("Account", remote_side=[id], backref="children")

    __table_args__ = (
        Index("ix_account_type_active", "type", "is_active"),
    )


class JournalEntry(Base):
    """Journal Entry - Immutable once posted, hash-chained for audit integrity"""
    __tablename__ = "journal_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_number = Column(BigInteger, unique=True, nullable=False, index=True)
    entry_date = Column(Date, nullable=False, index=True)
    description = Column(Text, nullable=False)
    reference_type = Column(String(50), nullable=True, index=True)  # MINT, BURN, BRIDGE_LOCK, BRIDGE_RELEASE, FEE, PAYOUT, DEPOSIT
    reference_id = Column(String(100), nullable=True, index=True)  # tx_hash, bridge_nonce, deposit_id, etc.
    status = Column(SQLEnum(EntryStatus), nullable=False, default=EntryStatus.DRAFT, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    posted_at = Column(DateTime, nullable=True, index=True)
    posted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reversed_at = Column(DateTime, nullable=True)
    reversed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reversal_reason = Column(Text, nullable=True)
    prev_hash = Column(String(64), nullable=True)  # Hash of previous posted entry for chain integrity

    # Relationships
    lines = relationship("JournalLine", back_populates="journal_entry", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])
    poster = relationship("User", foreign_keys=[posted_by])
    reverser = relationship("User", foreign_keys=[reversed_by])

    __table_args__ = (
        Index("ix_journal_entry_date_status", "entry_date", "status"),
        Index("ix_journal_entry_ref", "reference_type", "reference_id"),
    )


class JournalLine(Base):
    """Journal Line - Individual debit/credit entries within a journal entry"""
    __tablename__ = "journal_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journal_entry_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    debit = Column(Numeric(precision=78, scale=0), nullable=False, default=0)  # 18 decimals for IDR wei
    credit = Column(Numeric(precision=78, scale=0), nullable=False, default=0)
    description = Column(Text, nullable=True)
    line_number = Column(Integer, nullable=False)

    # Relationships
    journal_entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account")

    __table_args__ = (
        CheckConstraint("debit = 0 OR credit = 0", name="ck_journal_line_one_sided"),
        CheckConstraint("debit >= 0 AND credit >= 0", name="ck_journal_line_non_negative"),
        UniqueConstraint("journal_entry_id", "line_number", name="uq_journal_line_number"),
    )


class Reconciliation(Base):
    """Reconciliation - Daily reconciliation between on-chain, off-chain, and bank state"""
    __tablename__ = "reconciliations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reconciliation_date = Column(Date, nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)  # DAILY_SUPPLY, DAILY_RESERVE, DEPOSIT_MINT, REDEMPTION_PAYOUT, BRIDGE_BALANCE
    expected_value = Column(Numeric(precision=78, scale=0), nullable=False)
    actual_value = Column(Numeric(precision=78, scale=0), nullable=False)
    difference = Column(Numeric(precision=78, scale=0), nullable=False)  # actual - expected
    status = Column(String(20), nullable=False, default="OPEN", index=True)  # OPEN, INVESTIGATING, RESOLVED, FALSE_POSITIVE
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    resolver = relationship("User", foreign_keys=[resolved_by])

    __table_args__ = (
        UniqueConstraint("reconciliation_date", "type", name="uq_reconciliation_date_type"),
    )


class FinancialSnapshot(Base):
    """Financial Snapshot - Point-in-time balance sheet for audit/regulatory reporting"""
    __tablename__ = "financial_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_date = Column(Date, nullable=False, index=True)
    snapshot_type = Column(String(20), nullable=False, index=True)  # DAILY, MONTHLY, QUARTERLY, YEARLY
    
    # Assets
    total_fiat_reserve = Column(Numeric(precision=78, scale=0), nullable=False, default=0)
    customer_liability_reserve = Column(Numeric(precision=78, scale=0), nullable=False, default=0)
    operational_cash = Column(Numeric(precision=78, scale=0), nullable=False, default=0)
    fee_revenue_reserve = Column(Numeric(precision=78, scale=0), nullable=False, default=0)
    pending_deposits = Column(Numeric(precision=78, scale=0), nullable=False, default=0)
    encumbered_reserve = Column(Numeric(precision=78, scale=0), nullable=False, default=0)
    
    # Liabilities
    total_token_liability = Column(Numeric(precision=78, scale=0), nullable=False, default=0)
    pending_withdrawals = Column(Numeric(precision=78, scale=0), nullable=False, default=0)
    
    # On-chain state
    onchain_total_supply = Column(Numeric(precision=78, scale=0), nullable=False, default=0)
    onchain_reserve_balance = Column(Numeric(precision=78, scale=0), nullable=False, default=0)
    
    # Collateralization
    collateralization_ratio_bps = Column(Integer, nullable=True)  # basis points (10000 = 100%)
    
    # Hash chain for integrity
    prev_snapshot_hash = Column(String(64), nullable=True)
    snapshot_hash = Column(String(64), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("snapshot_date", "snapshot_type", name="uq_snapshot_date_type"),
    )

# ============================================================
# Database Setup
# ============================================================

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_database_url() -> str:
    """Get database URL from environment"""
    return os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/idrc"
    )


async def init_db() -> None:
    """Initialize database engine and create tables"""
    global _engine, _session_factory

    database_url = get_database_url()
    _engine = create_async_engine(
        database_url,
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
        pool_pre_ping=True,
        pool_recycle=3600,
    )

    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    # Create tables
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections"""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
    _engine = None
    _session_factory = None


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session"""
    if not _session_factory:
        await init_db()

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database session"""
    async with get_session() as session:
        yield session
