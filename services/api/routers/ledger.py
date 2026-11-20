"""
Ledger Router - Financial ledger API endpoints
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import (
    Account, AccountType, JournalEntry, JournalLine, EntryStatus,
    Reconciliation, FinancialSnapshot, get_session_dependency
)
from ..services.ledger_service import LedgerService, wei_to_decimal
from ..models import (
    AccountCreate, AccountResponse,
    JournalEntryCreate, JournalEntryPost, JournalEntryReverse, JournalEntryResponse,
    ReconciliationResponse, FinancialSnapshotResponse,
    DailyReconciliationRequest, FinancialHealthResponse,
    IDRCAmount, WeiAmount
)

router = APIRouter()


# ============================================================
# Chart of Accounts
# ============================================================

@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    account: AccountCreate,
    session: AsyncSession = Depends(get_session_dependency),
):
    """Create a new account in the chart of accounts"""
    ledger = LedgerService(session)
    
    # Validate parent exists if provided
    if account.parent_code:
        parent_stmt = select(Account).where(Account.code == account.parent_code)
        parent_result = await session.execute(parent_stmt)
        if not parent_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Parent account not found")
    
    db_account = await ledger.get_or_create_account(
        code=account.code,
        name=account.name,
        type=AccountType(account.type.value),
        parent_code=account.parent_code
    )
    
    return AccountResponse(
        id=str(db_account.id),
        code=db_account.code,
        name=db_account.name,
        type=AccountType(db_account.type.value),
        currency=db_account.currency,
        parent_code=account.parent_code,
        is_active=db_account.is_active,
        description=db_account.description,
        created_at=db_account.created_at,
        updated_at=db_account.updated_at
    )


@router.get("/accounts", response_model=List[AccountResponse])
async def list_accounts(
    type: Optional[AccountType] = Query(None),
    is_active: Optional[bool] = Query(None),
    session: AsyncSession = Depends(get_session_dependency),
):
    """List all accounts with optional filters"""
    stmt = select(Account)
    if type:
        stmt = stmt.where(Account.type == type)
    if is_active is not None:
        stmt = stmt.where(Account.is_active == is_active)
    stmt = stmt.order_by(Account.code)
    
    result = await session.execute(stmt)
    accounts = result.scalars().all()
    
    return [
        AccountResponse(
            id=str(acc.id),
            code=acc.code,
            name=acc.name,
            type=AccountType(acc.type.value),
            currency=acc.currency,
            parent_code=acc.parent.code if acc.parent else None,
            is_active=acc.is_active,
            description=acc.description,
            created_at=acc.created_at,
            updated_at=acc.updated_at
        )
        for acc in accounts
    ]


@router.get("/accounts/{code}", response_model=AccountResponse)
async def get_account(
    code: str,
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get account by code"""
    stmt = select(Account).where(Account.code == code)
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    return AccountResponse(
        id=str(account.id),
        code=account.code,
        name=account.name,
        type=AccountType(account.type.value),
        currency=account.currency,
        parent_code=account.parent.code if account.parent else None,
        is_active=account.is_active,
        description=account.description,
        created_at=account.created_at,
        updated_at=account.updated_at
    )


@router.get("/accounts/{code}/balance")
async def get_account_balance(
    code: str,
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get account balance (net debit - credit)"""
    ledger = LedgerService(session)
    net_balance = await ledger.get_account_net_balance(code)
    debit, credit = await ledger.get_account_balance(code)
    
    return {
        "account_code": code,
        "debit": WeiAmount(debit),
        "credit": WeiAmount(credit),
        "net_balance": WeiAmount(net_balance),
        "net_balance_idr": IDRCAmount(wei_to_decimal(net_balance))
    }


# ============================================================
# Journal Entries
# ============================================================

@router.post("/journal-entries", response_model=JournalEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_journal_entry(
    entry: JournalEntryCreate,
    session: AsyncSession = Depends(get_session_dependency),
):
    """Create a new journal entry (draft)"""
    ledger = LedgerService(session)
    
    lines = [
        {
            "account_code": line.account_code,
            "debit": line.debit,
            "credit": line.credit,
            "description": line.description
        }
        for line in entry.lines
    ]
    
    db_entry = await ledger.create_journal_entry(
        entry_date=entry.entry_date,
        description=entry.description,
        reference_type=entry.reference_type,
        reference_id=entry.reference_id or "",
        lines=lines
    )
    
    await session.commit()
    await session.refresh(db_entry, attribute_names=["lines"])
    
    return await _format_journal_entry(db_entry, session)


@router.post("/journal-entries/{entry_id}/post", response_model=JournalEntryResponse)
async def post_journal_entry(
    entry_id: UUID,
    post: JournalEntryPost,
    session: AsyncSession = Depends(get_session_dependency),
):
    """Post a draft journal entry"""
    ledger = LedgerService(session)
    
    try:
        posted_by = UUID(post.posted_by) if post.posted_by else None
    except ValueError:
        posted_by = None
    
    try:
        db_entry = await ledger.post_journal_entry(entry_id, posted_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return await _format_journal_entry(db_entry, session)


@router.post("/journal-entries/{entry_id}/reverse", response_model=JournalEntryResponse)
async def reverse_journal_entry(
    entry_id: UUID,
    reverse: JournalEntryReverse,
    session: AsyncSession = Depends(get_session_dependency),
):
    """Reverse a posted journal entry"""
    ledger = LedgerService(session)
    
    try:
        reversed_by = UUID(reverse.reversed_by) if reverse.reversed_by else None
    except ValueError:
        reversed_by = None
    
    try:
        reversed_entry = await ledger.reverse_journal_entry(entry_id, reversed_by, reverse.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return await _format_journal_entry(reversed_entry, session)


@router.get("/journal-entries", response_model=List[JournalEntryResponse])
async def list_journal_entries(
    status: Optional[EntryStatus] = Query(None),
    reference_type: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session_dependency),
):
    """List journal entries with filters"""
    stmt = select(JournalEntry).options(selectinload(JournalEntry.lines))
    
    if status:
        stmt = stmt.where(JournalEntry.status == status)
    if reference_type:
        stmt = stmt.where(JournalEntry.reference_type == reference_type)
    if from_date:
        stmt = stmt.where(JournalEntry.entry_date >= from_date)
    if to_date:
        stmt = stmt.where(JournalEntry.entry_date <= to_date)
    
    stmt = stmt.order_by(desc(JournalEntry.entry_number)).limit(limit).offset(offset)
    result = await session.execute(stmt)
    entries = result.scalars().all()
    
    return [await _format_journal_entry(entry, session) for entry in entries]


@router.get("/journal-entries/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: UUID,
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get journal entry by ID"""
    stmt = select(JournalEntry).options(selectinload(JournalEntry.lines)).where(
        JournalEntry.id == entry_id
    )
    result = await session.execute(stmt)
    entry = result.scalar_one_or_none()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    
    return await _format_journal_entry(entry, session)


# ============================================================
# Reconciliation
# ============================================================

@router.post("/reconciliation/daily", response_model=List[ReconciliationResponse])
async def run_daily_reconciliation(
    request: DailyReconciliationRequest,
    session: AsyncSession = Depends(get_session_dependency),
):
    """Run daily reconciliation"""
    ledger = LedgerService(session)
    reconciliations = await ledger.run_daily_reconciliation(request.reconciliation_date)
    return [
        ReconciliationResponse(
            id=str(r.id),
            reconciliation_date=r.reconciliation_date,
            type=r.type,
            expected_value=r.expected_value,
            actual_value=r.actual_value,
            difference=r.difference,
            status=r.status,
            resolved_at=r.resolved_at,
            resolved_by=str(r.resolved_by) if r.resolved_by else None,
            notes=r.notes,
            created_at=r.created_at
        )
        for r in reconciliations
    ]


@router.get("/reconciliation", response_model=List[ReconciliationResponse])
async def list_reconciliations(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session_dependency),
):
    """List reconciliations with filters"""
    stmt = select(Reconciliation)
    
    if date_from:
        stmt = stmt.where(Reconciliation.reconciliation_date >= date_from)
    if date_to:
        stmt = stmt.where(Reconciliation.reconciliation_date <= date_to)
    if type:
        stmt = stmt.where(Reconciliation.type == type)
    if status:
        stmt = stmt.where(Reconciliation.status == status)
    
    stmt = stmt.order_by(desc(Reconciliation.reconciliation_date))
    result = await session.execute(stmt)
    reconciliations = result.scalars().all()
    
    return [
        ReconciliationResponse(
            id=str(r.id),
            reconciliation_date=r.reconciliation_date,
            type=r.type,
            expected_value=r.expected_value,
            actual_value=r.actual_value,
            difference=r.difference,
            status=r.status,
            resolved_at=r.resolved_at,
            resolved_by=str(r.resolved_by) if r.resolved_by else None,
            notes=r.notes,
            created_at=r.created_at
        )
        for r in reconciliations
    ]


# ============================================================
# Financial Snapshots
# ============================================================

@router.post("/snapshots/daily", response_model=FinancialSnapshotResponse)
async def create_daily_snapshot(
    snapshot_date: date = date.today(),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Create daily financial snapshot"""
    ledger = LedgerService(session)
    snapshot = await ledger.create_daily_snapshot(snapshot_date)
    
    return FinancialSnapshotResponse(
        id=str(snapshot.id),
        snapshot_date=snapshot.snapshot_date,
        snapshot_type=snapshot.snapshot_type,
        total_fiat_reserve=snapshot.total_fiat_reserve,
        customer_liability_reserve=snapshot.customer_liability_reserve,
        operational_cash=snapshot.operational_cash,
        fee_revenue_reserve=snapshot.fee_revenue_reserve,
        pending_deposits=snapshot.pending_deposits,
        encumbered_reserve=snapshot.encumbered_reserve,
        total_token_liability=snapshot.total_token_liability,
        pending_withdrawals=snapshot.pending_withdrawals,
        onchain_total_supply=snapshot.onchain_total_supply,
        onchain_reserve_balance=snapshot.onchain_reserve_balance,
        collateralization_ratio_bps=snapshot.collateralization_ratio_bps,
        prev_snapshot_hash=snapshot.prev_snapshot_hash,
        snapshot_hash=snapshot.snapshot_hash,
        created_at=snapshot.created_at
    )


@router.get("/snapshots", response_model=List[FinancialSnapshotResponse])
async def list_snapshots(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    snapshot_type: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session_dependency),
):
    """List financial snapshots"""
    stmt = select(FinancialSnapshot)
    
    if date_from:
        stmt = stmt.where(FinancialSnapshot.snapshot_date >= date_from)
    if date_to:
        stmt = stmt.where(FinancialSnapshot.snapshot_date <= date_to)
    if snapshot_type:
        stmt = stmt.where(FinancialSnapshot.snapshot_type == snapshot_type)
    
    stmt = stmt.order_by(desc(FinancialSnapshot.snapshot_date))
    result = await session.execute(stmt)
    snapshots = result.scalars().all()
    
    return [
        FinancialSnapshotResponse(
            id=str(s.id),
            snapshot_date=s.snapshot_date,
            snapshot_type=s.snapshot_type,
            total_fiat_reserve=s.total_fiat_reserve,
            customer_liability_reserve=s.customer_liability_reserve,
            operational_cash=s.operational_cash,
            fee_revenue_reserve=s.fee_revenue_reserve,
            pending_deposits=s.pending_deposits,
            encumbered_reserve=s.encumbered_reserve,
            total_token_liability=s.total_token_liability,
            pending_withdrawals=s.pending_withdrawals,
            onchain_total_supply=s.onchain_total_supply,
            onchain_reserve_balance=s.onchain_reserve_balance,
            collateralization_ratio_bps=s.collateralization_ratio_bps,
            prev_snapshot_hash=s.prev_snapshot_hash,
            snapshot_hash=s.snapshot_hash,
            created_at=s.created_at
        )
        for s in snapshots
    ]


# ============================================================
# Financial Health
# ============================================================

@router.get("/health", response_model=FinancialHealthResponse)
async def get_financial_health(
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get overall financial health summary"""
    ledger = LedgerService(session)
    
    total_token_liability = await ledger.get_token_liability()
    total_fiat_reserve = await ledger.get_bank_reserve()
    pending_deposits = await ledger.get_pending_deposits()
    pending_withdrawals = await ledger.get_pending_withdrawals()
    encumbered_reserve = await ledger.get_encumbered_reserve()
    fee_revenue = await ledger.get_fee_revenue()
    
    collateralization_ratio_bps = None
    is_fully_collateralized = False
    if total_token_liability > 0:
        collateralization_ratio_bps = int((total_fiat_reserve * 10000) // total_token_liability)
        is_fully_collateralized = collateralization_ratio_bps >= 10000
    
    # Get last reconciliation status
    stmt = select(Reconciliation).order_by(desc(Reconciliation.reconciliation_date)).limit(1)
    result = await session.execute(stmt)
    last_recon = result.scalar_one_or_none()
    
    reconciliation_status = {}
    if last_recon:
        stmt = select(Reconciliation).where(Reconciliation.reconciliation_date == last_recon.reconciliation_date)
        result = await session.execute(stmt)
        recons = result.scalars().all()
        reconciliation_status = {r.type: r.status for r in recons}
    
    return FinancialHealthResponse(
        total_token_liability=IDRCAmount(wei_to_decimal(total_token_liability)),
        total_fiat_reserve=IDRCAmount(wei_to_decimal(total_fiat_reserve)),
        collateralization_ratio_bps=collateralization_ratio_bps,
        is_fully_collateralized=is_fully_collateralized,
        supply_cap_utilization_bps=None,  # Would need supply cap
        pending_deposits=IDRCAmount(wei_to_decimal(pending_deposits)),
        pending_withdrawals=IDRCAmount(wei_to_decimal(pending_withdrawals)),
        encumbered_reserve=IDRCAmount(wei_to_decimal(encumbered_reserve)),
        fee_revenue=IDRCAmount(wei_to_decimal(fee_revenue)),
        last_reconciliation_date=last_recon.reconciliation_date if last_recon else None,
        reconciliation_status=reconciliation_status
    )


# ============================================================
# Helper Functions
# ============================================================

async def _format_journal_entry(entry: JournalEntry, session: AsyncSession) -> JournalEntryResponse:
    """Format journal entry with lines"""
    # Load lines if not already loaded
    if not entry.lines:
        stmt = select(JournalLine).options(selectinload(JournalLine.account)).where(
            JournalLine.journal_entry_id == entry.id
        ).order_by(JournalLine.line_number)
        result = await session.execute(stmt)
        lines = result.scalars().all()
    else:
        # Ensure accounts are loaded
        for line in entry.lines:
            if not line.account:
                stmt = select(Account).where(Account.id == line.account_id)
                result = await session.execute(stmt)
                line.account = result.scalar_one_or_none()
        lines = entry.lines
    
    return JournalEntryResponse(
        id=str(entry.id),
        entry_number=entry.entry_number,
        entry_date=entry.entry_date,
        description=entry.description,
        reference_type=entry.reference_type,
        reference_id=entry.reference_id,
        status=EntryStatus(entry.status.value),
        created_by=str(entry.created_by) if entry.created_by else None,
        created_at=entry.created_at,
        posted_at=entry.posted_at,
        posted_by=str(entry.posted_by) if entry.posted_by else None,
        reversed_at=entry.reversed_at,
        reversed_by=str(entry.reversed_by) if entry.reversed_by else None,
        reversal_reason=entry.reversal_reason,
        prev_hash=entry.prev_hash,
        lines=[
            JournalLineResponse(
                id=str(line.id),
                journal_entry_id=str(line.journal_entry_id),
                account_code=line.account.code if line.account else "",
                account_name=line.account.name if line.account else None,
                debit=line.debit,
                credit=line.credit,
                description=line.description,
                line_number=line.line_number
            )
            for line in lines
        ]
    )


# Add selectinload import
from sqlalchemy.orm import selectinload
