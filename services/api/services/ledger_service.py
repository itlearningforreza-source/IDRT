"""
Ledger Service - Double-entry accounting for IDRC financial operations
Handles journal entries, reconciliation, and financial snapshots
"""
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .database import (
    Account, AccountType, JournalEntry, JournalLine, EntryStatus,
    Reconciliation, FinancialSnapshot, User, TokenEvent
)


class LedgerService:
    """Double-entry ledger service for IDRC financial operations"""
    
    # Chart of Accounts Codes
    # Assets (1xxx)
    ACCOUNT_BANK_RESERVE = "1010"           # Fiat reserve at bank custodian
    ACCOUNT_CUSTOMER_LIABILITY_RESERVE = "1020"  # Reserve backing customer tokens
    ACCOUNT_OPERATIONAL_CASH = "1030"       # Company operational funds
    ACCOUNT_FEE_REVENUE_RESERVE = "1040"    # Accumulated fee revenue
    ACCOUNT_PENDING_DEPOSITS = "1050"       # Deposits received, not yet minted
    ACCOUNT_ENCUMBERED_RESERVE = "1060"     # Legally encumbered (sanctions, holds)
    
    # Liabilities (2xxx)
    ACCOUNT_TOKEN_LIABILITY = "2010"        # Total IDRC tokens outstanding (customer liability)
    ACCOUNT_PENDING_WITHDRAWALS = "2020"    # Burned tokens awaiting fiat payout
    
    # Equity (3xxx)
    ACCOUNT_RETAINED_EARNINGS = "3010"
    
    # Revenue (4xxx)
    ACCOUNT_MINT_FEE_REVENUE = "4010"
    ACCOUNT_BURN_FEE_REVENUE = "4020"
    ACCOUNT_BRIDGE_FEE_REVENUE = "4030"
    
    # Expense (5xxx)
    ACCOUNT_OPERATIONAL_EXPENSE = "5010"

    def __init__(self, session: AsyncSession):
        self.session = session

    # ============================================================
    # Account Management
    # ============================================================

    async def get_or_create_account(self, code: str, name: str, type: AccountType, 
                                     parent_code: Optional[str] = None) -> Account:
        """Get existing account or create new one"""
        stmt = select(Account).where(Account.code == code)
        result = await self.session.execute(stmt)
        account = result.scalar_one_or_none()
        
        if account:
            return account
        
        parent_id = None
        if parent_code:
            parent_stmt = select(Account).where(Account.code == parent_code)
            parent_result = await self.session.execute(parent_stmt)
            parent = parent_result.scalar_one_or_none()
            if parent:
                parent_id = parent.id
        
        account = Account(
            code=code,
            name=name,
            type=type,
            parent_id=parent_id
        )
        self.session.add(account)
        await self.session.flush()
        return account

    async def initialize_chart_of_accounts(self) -> List[Account]:
        """Initialize the standard chart of accounts for IDRC"""
        accounts = []
        
        # Asset accounts
        accounts.append(await self.get_or_create_account(
            self.ACCOUNT_BANK_RESERVE, "Bank Reserve (Custodian)", AccountType.ASSET
        ))
        accounts.append(await self.get_or_create_account(
            self.ACCOUNT_CUSTOMER_LIABILITY_RESERVE, "Customer Liability Reserve", AccountType.ASSET,
            parent_code=self.ACCOUNT_BANK_RESERVE
        ))
        accounts.append(await self.get_or_create_account(
            self.ACCOUNT_OPERATIONAL_CASH, "Operational Cash", AccountType.ASSET,
            parent_code=self.ACCOUNT_BANK_RESERVE
        ))
        accounts.append(await self.get_or_create_account(
            self.ACCOUNT_FEE_REVENUE_RESERVE, "Fee Revenue Reserve", AccountType.ASSET,
            parent_code=self.ACCOUNT_BANK_RESERVE
        ))
        accounts.append(await self.get_or_create_account(
            self.ACCOUNT_PENDING_DEPOSITS, "Pending Deposits", AccountType.ASSET
        ))
        accounts.append(await self.get_or_create_account(
            self.ACCOUNT_ENCUMBERED_RESERVE, "Encumbered Reserve", AccountType.ASSET
        ))
        
        # Liability accounts
        accounts.append(await self.get_or_create_account(
            self.ACCOUNT_TOKEN_LIABILITY, "Token Liability (Customer)", AccountType.LIABILITY
        ))
        accounts.append(await self.get_or_create_account(
            self.ACCOUNT_PENDING_WITHDRAWALS, "Pending Withdrawals", AccountType.LIABILITY
        ))
        
        # Equity accounts
        accounts.append(await self.get_or_create_account(
            self.ACCOUNT_RETAINED_EARNINGS, "Retained Earnings", AccountType.EQUITY
        ))
        
        # Revenue accounts
        accounts.append(await self.get_or_create_account(
            self.ACCOUNT_MINT_FEE_REVENUE, "Mint Fee Revenue", AccountType.REVENUE
        ))
        accounts.append(await self.get_or_create_account(
            self.ACCOUNT_BURN_FEE_REVENUE, "Burn Fee Revenue", AccountType.REVENUE
        ))
        accounts.append(await self.get_or_create_account(
            self.ACCOUNT_BRIDGE_FEE_REVENUE, "Bridge Fee Revenue", AccountType.REVENUE
        ))
        
        # Expense accounts
        accounts.append(await self.get_or_create_account(
            self.ACCOUNT_OPERATIONAL_EXPENSE, "Operational Expenses", AccountType.EXPENSE
        ))
        
        await self.session.commit()
        return accounts

    # ============================================================
    # Journal Entry Operations
    # ============================================================

    async def create_journal_entry(
        self,
        entry_date: date,
        description: str,
        reference_type: str,
        reference_id: str,
        lines: List[dict],  # [{"account_code": str, "debit": int, "credit": int, "description": str}]
        created_by: Optional[UUID] = None
    ) -> JournalEntry:
        """Create a journal entry with lines (must balance: sum debit = sum credit)"""
        
        # Validate lines balance
        total_debit = sum(line.get("debit", 0) for line in lines)
        total_credit = sum(line.get("credit", 0) for line in lines)
        
        if total_debit != total_credit:
            raise ValueError(f"Journal entry unbalanced: debits={total_debit}, credits={total_credit}")
        
        # Get previous entry hash for chain integrity
        prev_stmt = select(JournalEntry).where(
            JournalEntry.status == EntryStatus.POSTED
        ).order_by(desc(JournalEntry.entry_number)).limit(1)
        prev_result = await self.session.execute(prev_stmt)
        prev_entry = prev_result.scalar_one_or_none()
        prev_hash = prev_entry.get_hash() if prev_entry else "0" * 64
        
        # Get next entry number
        next_num_stmt = select(func.coalesce(func.max(JournalEntry.entry_number), 0) + 1)
        next_num_result = await self.session.execute(next_num_stmt)
        entry_number = next_num_result.scalar_one()
        
        # Create journal entry
        entry = JournalEntry(
            entry_number=entry_number,
            entry_date=entry_date,
            description=description,
            reference_type=reference_type,
            reference_id=reference_id,
            status=EntryStatus.DRAFT,
            created_by=created_by,
            prev_hash=prev_hash
        )
        self.session.add(entry)
        await self.session.flush()
        
        # Create journal lines
        for i, line_data in enumerate(lines, 1):
            account_stmt = select(Account).where(Account.code == line_data["account_code"])
            account_result = await self.session.execute(account_stmt)
            account = account_result.scalar_one_or_none()
            
            if not account:
                raise ValueError(f"Account not found: {line_data['account_code']}")
            
            line = JournalLine(
                journal_entry_id=entry.id,
                account_id=account.id,
                debit=line_data.get("debit", 0),
                credit=line_data.get("credit", 0),
                description=line_data.get("description", ""),
                line_number=i
            )
            self.session.add(line)
        
        await self.session.flush()
        return entry

    async def post_journal_entry(self, entry_id: UUID, posted_by: UUID) -> JournalEntry:
        """Post a draft journal entry (validates balance, computes hash chain)"""
        stmt = select(JournalEntry).options(selectinload(JournalEntry.lines)).where(
            JournalEntry.id == entry_id
        )
        result = await self.session.execute(stmt)
        entry = result.scalar_one_or_none()
        
        if not entry:
            raise ValueError(f"Journal entry not found: {entry_id}")
        
        if entry.status != EntryStatus.DRAFT:
            raise ValueError(f"Entry already {entry.status.value}")
        
        # Validate balance
        total_debit = sum(line.debit for line in entry.lines)
        total_credit = sum(line.credit for line in entry.lines)
        
        if total_debit != total_credit:
            raise ValueError(f"Entry {entry_id} unbalanced: debits={total_debit}, credits={total_credit}")
        
        # Update status and compute hash
        entry.status = EntryStatus.POSTED
        entry.posted_at = datetime.utcnow()
        entry.posted_by = posted_by
        
        # Compute hash chain: hash(prev_hash || entry_data)
        entry_data = f"{entry.entry_number}|{entry.entry_date}|{entry.description}|{entry.reference_type}|{entry.reference_id}|{total_debit}|{total_credit}|{prev_hash}"
        entry.prev_hash = hashlib.sha256(entry_data.encode()).hexdigest()
        
        await self.session.commit()
        return entry

    async def reverse_journal_entry(
        self, entry_id: UUID, reversed_by: UUID, reason: str
    ) -> JournalEntry:
        """Reverse a posted journal entry by creating reversing entry"""
        stmt = select(JournalEntry).options(selectinload(JournalEntry.lines)).where(
            JournalEntry.id == entry_id
        )
        result = await self.session.execute(stmt)
        original = result.scalar_one_or_none()
        
        if not original:
            raise ValueError(f"Journal entry not found: {entry_id}")
        
        if original.status != EntryStatus.POSTED:
            raise ValueError(f"Can only reverse posted entries (status: {original.status.value})")
        
        # Create reversing lines (swap debit/credit)
        reversing_lines = []
        for line in original.lines:
            reversing_lines.append({
                "account_code": line.account.code,
                "debit": line.credit,
                "credit": line.debit,
                "description": f"Reversal: {line.description or original.description}"
            })
        
        # Create reversing entry
        reversing_entry = await self.create_journal_entry(
            entry_date=date.today(),
            description=f"Reversal of entry {original.entry_number}: {reason}",
            reference_type="REVERSAL",
            reference_id=str(original.id),
            lines=reversing_lines,
            created_by=reversed_by
        )
        
        # Post the reversing entry
        await self.post_journal_entry(reversing_entry.id, reversed_by)
        
        # Update original entry
        original.status = EntryStatus.REVERSED
        original.reversed_at = datetime.utcnow()
        original.reversed_by = reversed_by
        original.reversal_reason = reason
        
        await self.session.commit()
        return reversing_entry

    def _compute_entry_hash(self, entry: JournalEntry) -> str:
        """Compute hash for journal entry"""
        total_debit = sum(line.debit for line in entry.lines)
        total_credit = sum(line.credit for line in entry.lines)
        data = f"{entry.entry_number}|{entry.entry_date}|{entry.description}|{entry.reference_type}|{entry.reference_id}|{total_debit}|{total_credit}|{entry.prev_hash}"
        return hashlib.sha256(data.encode()).hexdigest()

    # ============================================================
    # Convenience Methods for IDRC Operations
    # ============================================================

    async def record_mint(
        self,
        amount_wei: int,
        tx_hash: str,
        deposit_reference: str,
        fee_wei: int = 0,
        created_by: Optional[UUID] = None
    ) -> JournalEntry:
        """Record token minting: Dr Bank Reserve / Cr Token Liability (+ Fee Revenue)"""
        lines = [
            {
                "account_code": self.ACCOUNT_BANK_RESERVE,
                "debit": amount_wei,
                "credit": 0,
                "description": f"Mint deposit received (ref: {deposit_reference})"
            },
            {
                "account_code": self.ACCOUNT_TOKEN_LIABILITY,
                "debit": 0,
                "credit": amount_wei,
                "description": f"Token liability increase (mint {amount_wei} wei)"
            }
        ]
        
        if fee_wei > 0:
            lines.append({
                "account_code": self.ACCOUNT_MINT_FEE_REVENUE,
                "debit": 0,
                "credit": fee_wei,
                "description": f"Mint fee revenue ({fee_wei} wei)"
            })
            # Fee comes from operational cash
            lines.append({
                "account_code": self.ACCOUNT_OPERATIONAL_CASH,
                "debit": fee_wei,
                "credit": 0,
                "description": f"Fee collected from operational cash"
            })
        
        entry = await self.create_journal_entry(
            entry_date=date.today(),
            description=f"Token mint: {amount_wei} wei (tx: {tx_hash})",
            reference_type="MINT",
            reference_id=tx_hash,
            lines=lines,
            created_by=created_by
        )
        
        return await self.post_journal_entry(entry.id, created_by) if created_by else entry

    async def record_burn(
        self,
        amount_wei: int,
        tx_hash: str,
        payout_reference: Optional[str] = None,
        fee_wei: int = 0,
        created_by: Optional[UUID] = None
    ) -> JournalEntry:
        """Record token burning: Dr Token Liability / Cr Bank Reserve (+ Fee Revenue)"""
        lines = [
            {
                "account_code": self.ACCOUNT_TOKEN_LIABILITY,
                "debit": amount_wei,
                "credit": 0,
                "description": f"Token liability decrease (burn {amount_wei} wei)"
            },
            {
                "account_code": self.ACCOUNT_BANK_RESERVE,
                "debit": 0,
                "credit": amount_wei,
                "description": f"Bank reserve for redemption payout"
            }
        ]
        
        if fee_wei > 0:
            lines.append({
                "account_code": self.ACCOUNT_BURN_FEE_REVENUE,
                "debit": 0,
                "credit": fee_wei,
                "description": f"Burn fee revenue ({fee_wei} wei)"
            })
            lines.append({
                "account_code": self.ACCOUNT_OPERATIONAL_CASH,
                "debit": fee_wei,
                "credit": 0,
                "description": f"Fee collected from operational cash"
            })
        
        entry = await self.create_journal_entry(
            entry_date=date.today(),
            description=f"Token burn: {amount_wei} wei (tx: {tx_hash})",
            reference_type="BURN",
            reference_id=tx_hash,
            lines=lines,
            created_by=created_by
        )
        
        return await self.post_journal_entry(entry.id, created_by) if created_by else entry

    async def record_bridge_lock(
        self,
        amount_wei: int,
        bridge_nonce: int,
        tx_hash: str,
        src_chain: int,
        dst_chain: int,
        created_by: Optional[UUID] = None
    ) -> JournalEntry:
        """Record bridge lock (burn on source): Dr Token Liability / Cr Bridge Locked Reserve"""
        lines = [
            {
                "account_code": self.ACCOUNT_TOKEN_LIABILITY,
                "debit": amount_wei,
                "credit": 0,
                "description": f"Bridge lock: token liability decrease (nonce {bridge_nonce})"
            },
            {
                "account_code": self.ACCOUNT_CUSTOMER_LIABILITY_RESERVE,
                "debit": 0,
                "credit": amount_wei,
                "description": f"Bridge locked reserve (src: {src_chain}, dst: {dst_chain})"
            }
        ]
        
        entry = await self.create_journal_entry(
            entry_date=date.today(),
            description=f"Bridge lock: {amount_wei} wei (nonce: {bridge_nonce}, src: {src_chain})",
            reference_type="BRIDGE_LOCK",
            reference_id=f"{bridge_nonce}:{tx_hash}",
            lines=lines,
            created_by=created_by
        )
        
        return await self.post_journal_entry(entry.id, created_by) if created_by else entry

    async def record_bridge_release(
        self,
        amount_wei: int,
        bridge_nonce: int,
        tx_hash: str,
        src_chain: int,
        dst_chain: int,
        created_by: Optional[UUID] = None
    ) -> JournalEntry:
        """Record bridge release (mint on destination): Dr Bridge Locked Reserve / Cr Token Liability"""
        lines = [
            {
                "account_code": self.ACCOUNT_CUSTOMER_LIABILITY_RESERVE,
                "debit": amount_wei,
                "credit": 0,
                "description": f"Bridge release: locked reserve decrease (nonce {bridge_nonce})"
            },
            {
                "account_code": self.ACCOUNT_TOKEN_LIABILITY,
                "debit": 0,
                "credit": amount_wei,
                "description": f"Bridge release: token liability increase (dst: {dst_chain})"
            }
        ]
        
        entry = await self.create_journal_entry(
            entry_date=date.today(),
            description=f"Bridge release: {amount_wei} wei (nonce: {bridge_nonce}, dst: {dst_chain})",
            reference_type="BRIDGE_RELEASE",
            reference_id=f"{bridge_nonce}:{tx_hash}",
            lines=lines,
            created_by=created_by
        )
        
        return await self.post_journal_entry(entry.id, created_by) if created_by else entry

    async def record_deposit_received(
        self,
        amount_wei: int,
        deposit_id: str,
        user_id: UUID,
        created_by: Optional[UUID] = None
    ) -> JournalEntry:
        """Record fiat deposit received: Dr Pending Deposits / Cr Bank Reserve"""
        lines = [
            {
                "account_code": self.ACCOUNT_PENDING_DEPOSITS,
                "debit": amount_wei,
                "credit": 0,
                "description": f"Deposit received from user {user_id}"
            },
            {
                "account_code": self.ACCOUNT_BANK_RESERVE,
                "debit": 0,
                "credit": amount_wei,
                "description": f"Bank reserve increase from deposit {deposit_id}"
            }
        ]
        
        entry = await self.create_journal_entry(
            entry_date=date.today(),
            description=f"Deposit received: {amount_wei} wei (deposit: {deposit_id})",
            reference_type="DEPOSIT",
            reference_id=deposit_id,
            lines=lines,
            created_by=created_by
        )
        
        return await self.post_journal_entry(entry.id, created_by) if created_by else entry

    async def record_payout_initiated(
        self,
        amount_wei: int,
        redemption_id: str,
        created_by: Optional[UUID] = None
    ) -> JournalEntry:
        """Record payout initiation: Dr Bank Reserve / Cr Pending Withdrawals"""
        lines = [
            {
                "account_code": self.ACCOUNT_BANK_RESERVE,
                "debit": amount_wei,
                "credit": 0,
                "description": f"Bank reserve for payout {redemption_id}"
            },
            {
                "account_code": self.ACCOUNT_PENDING_WITHDRAWALS,
                "debit": 0,
                "credit": amount_wei,
                "description": f"Payout pending for redemption {redemption_id}"
            }
        ]
        
        entry = await self.create_journal_entry(
            entry_date=date.today(),
            description=f"Payout initiated: {amount_wei} wei (redemption: {redemption_id})",
            reference_type="PAYOUT_INIT",
            reference_id=redemption_id,
            lines=lines,
            created_by=created_by
        )
        
        return await self.post_journal_entry(entry.id, created_by) if created_by else entry

    async def record_payout_completed(
        self,
        amount_wei: int,
        redemption_id: str,
        bank_reference: str,
        created_by: Optional[UUID] = None
    ) -> JournalEntry:
        """Record payout completion: Dr Pending Withdrawals / Cr Bank Reserve"""
        lines = [
            {
                "account_code": self.ACCOUNT_PENDING_WITHDRAWALS,
                "debit": amount_wei,
                "credit": 0,
                "description": f"Payout completed for redemption {redemption_id}"
            },
            {
                "account_code": self.ACCOUNT_BANK_RESERVE,
                "debit": 0,
                "credit": amount_wei,
                "description": f"Bank reserve decrease for payout {bank_reference}"
            }
        ]
        
        entry = await self.create_journal_entry(
            entry_date=date.today(),
            description=f"Payout completed: {amount_wei} wei (redemption: {redemption_id}, bank: {bank_reference})",
            reference_type="PAYOUT_COMPLETE",
            reference_id=redemption_id,
            lines=lines,
            created_by=created_by
        )
        
        return await self.post_journal_entry(entry.id, created_by) if created_by else entry

    async def record_blacklist(
        self,
        amount_wei: int,
        address: str,
        created_by: Optional[UUID] = None
    ) -> JournalEntry:
        """Record blacklist: Dr Token Liability / Cr Encumbered Reserve"""
        lines = [
            {
                "account_code": self.ACCOUNT_TOKEN_LIABILITY,
                "debit": amount_wei,
                "credit": 0,
                "description": f"Blacklist: token liability decrease for {address}"
            },
            {
                "account_code": self.ACCOUNT_ENCUMBERED_RESERVE,
                "debit": 0,
                "credit": amount_wei,
                "description": f"Encumbered reserve for blacklisted address {address}"
            }
        ]
        
        entry = await self.create_journal_entry(
            entry_date=date.today(),
            description=f"Address blacklisted: {address} ({amount_wei} wei encumbered)",
            reference_type="BLACKLIST",
            reference_id=address,
            lines=lines,
            created_by=created_by
        )
        
        return await self.post_journal_entry(entry.id, created_by) if created_by else entry

    async def record_unblacklist(
        self,
        amount_wei: int,
        address: str,
        created_by: Optional[UUID] = None
    ) -> JournalEntry:
        """Record unblacklist: Dr Encumbered Reserve / Cr Token Liability"""
        lines = [
            {
                "account_code": self.ACCOUNT_ENCUMBERED_RESERVE,
                "debit": amount_wei,
                "credit": 0,
                "description": f"Unblacklist: encumbered reserve release for {address}"
            },
            {
                "account_code": self.ACCOUNT_TOKEN_LIABILITY,
                "debit": 0,
                "credit": amount_wei,
                "description": f"Unblacklist: token liability restored for {address}"
            }
        ]
        
        entry = await self.create_journal_entry(
            entry_date=date.today(),
            description=f"Address unblacklisted: {address} ({amount_wei} wei restored)",
            reference_type="UNBLACKLIST",
            reference_id=address,
            lines=lines,
            created_by=created_by
        )
        
        return await self.post_journal_entry(entry.id, created_by) if created_by else entry

    # ============================================================
    # Balance Queries
    # ============================================================

    async def get_account_balance(self, account_code: str) -> Tuple[int, int]:
        """Get total debit and credit for an account from posted entries"""
        stmt = select(
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0)
        ).select_from(JournalLine).join(JournalEntry).join(Account).where(
            and_(
                Account.code == account_code,
                JournalEntry.status == EntryStatus.POSTED
            )
        )
        result = await self.session.execute(stmt)
        debit, credit = result.one()
        return int(debit), int(credit)

    async def get_account_net_balance(self, account_code: str) -> int:
        """Get net balance (debit - credit) for an account"""
        debit, credit = await self.get_account_balance(account_code)
        return debit - credit

    async def get_token_liability(self) -> int:
        """Get total token liability (should match on-chain totalSupply)"""
        return await self.get_account_net_balance(self.ACCOUNT_TOKEN_LIABILITY)

    async def get_bank_reserve(self) -> int:
        """Get total bank reserve"""
        return await self.get_account_net_balance(self.ACCOUNT_BANK_RESERVE)

    async def get_customer_liability_reserve(self) -> int:
        """Get customer liability reserve (bridge locked)"""
        return await self.get_account_net_balance(self.ACCOUNT_CUSTOMER_LIABILITY_RESERVE)

    async def get_operational_cash(self) -> int:
        """Get operational cash"""
        return await self.get_account_net_balance(self.ACCOUNT_OPERATIONAL_CASH)

    async def get_fee_revenue(self) -> int:
        """Get total fee revenue"""
        mint_fee = await self.get_account_net_balance(self.ACCOUNT_MINT_FEE_REVENUE)
        burn_fee = await self.get_account_net_balance(self.ACCOUNT_BURN_FEE_REVENUE)
        bridge_fee = await self.get_account_net_balance(self.ACCOUNT_BRIDGE_FEE_REVENUE)
        return mint_fee + burn_fee + bridge_fee

    async def get_pending_deposits(self) -> int:
        """Get pending deposits"""
        return await self.get_account_net_balance(self.ACCOUNT_PENDING_DEPOSITS)

    async def get_pending_withdrawals(self) -> int:
        """Get pending withdrawals"""
        return await self.get_account_net_balance(self.ACCOUNT_PENDING_WITHDRAWALS)

    async def get_encumbered_reserve(self) -> int:
        """Get encumbered reserve (blacklisted, sanctions)"""
        return await self.get_account_net_balance(self.ACCOUNT_ENCUMBERED_RESERVE)

    # ============================================================
    # Reconciliation
    # ============================================================

    async def run_daily_reconciliation(self, recon_date: date) -> List[Reconciliation]:
        """Run daily reconciliation between on-chain, ledger, and bank"""
        reconciliations = []
        
        # 1. Supply vs Token Liability
        # This would fetch from blockchain - placeholder for now
        onchain_supply = 0  # TODO: fetch from blockchain
        ledger_liability = await self.get_token_liability()
        
        recon = Reconciliation(
            reconciliation_date=recon_date,
            type="DAILY_SUPPLY",
            expected_value=ledger_liability,
            actual_value=onchain_supply,
            difference=onchain_supply - ledger_liability,
            status="OPEN" if onchain_supply != ledger_liability else "RESOLVED",
            resolved_at=datetime.utcnow() if onchain_supply == ledger_liability else None
        )
        self.session.add(recon)
        reconciliations.append(recon)
        
        # 2. Reserve vs Bank (would fetch from bank API)
        bank_reserve = 0  # TODO: fetch from bank
        ledger_reserve = await self.get_bank_reserve()
        
        recon = Reconciliation(
            reconciliation_date=recon_date,
            type="DAILY_RESERVE",
            expected_value=ledger_reserve,
            actual_value=bank_reserve,
            difference=bank_reserve - ledger_reserve,
            status="OPEN" if abs(bank_reserve - ledger_reserve) > 0 else "RESOLVED",
            resolved_at=datetime.utcnow() if bank_reserve == ledger_reserve else None
        )
        self.session.add(recon)
        reconciliations.append(recon)
        
        # 3. Deposit-Mint Parity
        # 4. Redemption-Burn-Payout Parity
        # 5. Bridge Lock-Release Parity
        
        await self.session.commit()
        return reconciliations

    # ============================================================
    # Financial Snapshots
    # ============================================================

    async def create_daily_snapshot(self, snapshot_date: date) -> FinancialSnapshot:
        """Create daily financial snapshot for audit trail"""
        # Get all balances
        total_fiat_reserve = await self.get_bank_reserve()
        customer_liability_reserve = await self.get_customer_liability_reserve()
        operational_cash = await self.get_operational_cash()
        fee_revenue_reserve = await self.get_fee_revenue()
        pending_deposits = await self.get_pending_deposits()
        encumbered_reserve = await self.get_encumbered_reserve()
        total_token_liability = await self.get_token_liability()
        pending_withdrawals = await self.get_pending_withdrawals()
        
        # On-chain state (placeholder)
        onchain_total_supply = 0
        onchain_reserve_balance = 0
        
        # Collateralization ratio in basis points
        collateralization_ratio_bps = None
        if total_token_liability > 0:
            collateralization_ratio_bps = int((total_fiat_reserve * 10000) // total_token_liability)
        
        # Previous snapshot hash
        prev_stmt = select(FinancialSnapshot).order_by(
            desc(FinancialSnapshot.snapshot_date)
        ).limit(1)
        prev_result = await self.session.execute(prev_stmt)
        prev_snapshot = prev_result.scalar_one_or_none()
        prev_hash = prev_snapshot.snapshot_hash if prev_snapshot else "0" * 64
        
        # Compute snapshot hash
        snapshot_data = f"{snapshot_date}|{total_fiat_reserve}|{total_token_liability}|{prev_hash}"
        snapshot_hash = hashlib.sha256(snapshot_data.encode()).hexdigest()
        
        snapshot = FinancialSnapshot(
            snapshot_date=snapshot_date,
            snapshot_type="DAILY",
            total_fiat_reserve=total_fiat_reserve,
            customer_liability_reserve=customer_liability_reserve,
            operational_cash=operational_cash,
            fee_revenue_reserve=fee_revenue_reserve,
            pending_deposits=pending_deposits,
            encumbered_reserve=encumbered_reserve,
            total_token_liability=total_token_liability,
            pending_withdrawals=pending_withdrawals,
            onchain_total_supply=onchain_total_supply,
            onchain_reserve_balance=onchain_reserve_balance,
            collateralization_ratio_bps=collateralization_ratio_bps,
            prev_snapshot_hash=prev_hash,
            snapshot_hash=snapshot_hash
        )
        
        self.session.add(snapshot)
        await self.session.commit()
        return snapshot


def wei_to_decimal(wei: int) -> Decimal:
    """Convert wei (18 decimals) to Decimal for display"""
    return Decimal(wei) / Decimal(10**18)


def decimal_to_wei(amount: Decimal) -> int:
    """Convert Decimal to wei (18 decimals)"""
    return int((amount * Decimal(10**18)).quantize(Decimal('1')))


# Export for use in other modules
__all__ = [
    "LedgerService",
    "wei_to_decimal",
    "decimal_to_wei",
]
