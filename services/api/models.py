"""
IDRC API Models
Pydantic models for request/response validation
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address


# ============================================================
# Enums
# ============================================================

class Role(str, Enum):
    DEFAULT_ADMIN = "DEFAULT_ADMIN_ROLE"
    MINTER = "MINTER_ROLE"
    BURNER = "BURNER_ROLE"
    PAUSER = "PAUSER_ROLE"
    UPGRADER = "UPGRADER_ROLE"
    BLACKLISTER = "BLACKLISTER_ROLE"
    ORACLE = "ORACLE_ROLE"
    AUDITOR = "AUDITOR_ROLE"
    RELAYER = "RELAYER_ROLE"
    RELAYER_ADMIN = "RELAYER_ADMIN_ROLE"


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ChainId(int, Enum):
    ETHEREUM = 1
    POLYGON = 137
    BSC = 56
    ARBITRUM = 42161
    OPTIMISM = 10
    BASE = 8453
    SEPOLIA = 11155111
    AMOY = 80002


# ============================================================
# Base Models
# ============================================================

class AddressStr(str):
    """Ethereum address with checksum validation"""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, str):
            try:
                return to_checksum_address(v)
            except Exception:
                raise ValueError("Invalid Ethereum address")
        raise ValueError("Address must be a string")


class WeiAmount(int):
    """Token amount in wei (18 decimals)"""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, (int, str)):
            return int(v)
        if isinstance(v, (float, Decimal)):
            return int(Decimal(str(v)) * 10**18)
        raise ValueError("Amount must be a number")


class IDRCAmount(Decimal):
    """Token amount in IDRC (human readable, 18 decimals)"""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, (int, float, str, Decimal)):
            return Decimal(str(v))
        raise ValueError("Amount must be a number")

    def to_wei(self) -> int:
        return int(self * 10**18)


# ============================================================
# Request Models
# ============================================================

class TokenMintRequest(BaseModel):
    to: AddressStr = Field(..., description="Recipient address")
    amount: IDRCAmount = Field(..., gt=0, description="Amount in IDRC")
    caller: AddressStr = Field(..., description="Caller address (must have MINTER_ROLE)")


class TokenBurnRequest(BaseModel):
    from_address: AddressStr = Field(..., alias="from", description="Address to burn from")
    amount: IDRCAmount = Field(..., gt=0, description="Amount in IDRC")
    caller: AddressStr = Field(..., description="Caller address (must have BURNER_ROLE)")


class TokenTransferRequest(BaseModel):
    from_address: AddressStr = Field(..., alias="from", description="Sender address")
    to: AddressStr = Field(..., description="Recipient address")
    amount: IDRCAmount = Field(..., gt=0, description="Amount in IDRC")


class TokenApproveRequest(BaseModel):
    spender: AddressStr = Field(..., description="Spender address")
    amount: IDRCAmount = Field(..., ge=0, description="Amount in IDRC")
    caller: AddressStr = Field(..., description="Owner address")


class TokenPermitRequest(BaseModel):
    owner: AddressStr
    spender: AddressStr
    value: IDRCAmount
    deadline: int = Field(..., description="Unix timestamp deadline")
    v: int = Field(..., ge=0, le=255)
    r: str = Field(..., pattern=r"^0x[0-9a-fA-F]{64}$")
    s: str = Field(..., pattern=r"^0x[0-9a-fA-F]{64}$")


class MultisigProposeRequest(BaseModel):
    to: AddressStr
    value: str = Field(default="0", description="ETH value in wei")
    data: str = Field(default="0x", description="Calldata")
    caller: AddressStr = Field(..., description="Proposer address (must be owner)")
    description: Optional[str] = None


class MultisigConfirmRequest(BaseModel):
    transaction_id: int = Field(..., ge=0)
    caller: AddressStr = Field(..., description="Confirmer address (must be owner)")


class MultisigExecuteRequest(BaseModel):
    transaction_id: int = Field(..., ge=0)
    caller: AddressStr = Field(..., description="Executor address (must be owner)")


class RoleGrantRequest(BaseModel):
    role: Role
    account: AddressStr
    caller: AddressStr = Field(..., description="Caller address (must have DEFAULT_ADMIN_ROLE)")


class RoleRevokeRequest(BaseModel):
    role: Role
    account: AddressStr
    caller: AddressStr = Field(..., description="Caller address (must have DEFAULT_ADMIN_ROLE)")


class PauseRequest(BaseModel):
    caller: AddressStr = Field(..., description="Caller address (must have PAUSER_ROLE)")


class BlacklistRequest(BaseModel):
    account: AddressStr
    caller: AddressStr = Field(..., description="Caller address (must have BLACKLISTER_ROLE)")


class ReserveProofRequest(BaseModel):
    proof_hash: str = Field(..., pattern=r"^0x[0-9a-fA-F]{64}$", description="SHA-256 hash of audit report")
    reported_fiat_idr: IDRCAmount = Field(..., gt=0, description="Reported fiat balance in IDR")
    caller: AddressStr = Field(..., description="Caller address (must have AUDITOR_ROLE)")


class ReserveOracleUpdateRequest(BaseModel):
    new_balance_idr: IDRCAmount = Field(..., ge=0, description="New fiat balance in IDR")
    caller: AddressStr = Field(..., description="Caller address (must have ORACLE_ROLE)")


class BridgeTransferRequest(BaseModel):
    src_chain: ChainId
    dst_chain: ChainId
    sender: AddressStr
    recipient: AddressStr
    amount: IDRCAmount = Field(..., gt=0)
    caller: AddressStr = Field(..., description="Caller address (must have RELAYER_ROLE)")


class BridgeCompleteRequest(BaseModel):
    bridge_nonce: int = Field(..., ge=0)
    src_chain: ChainId
    dst_chain: ChainId
    recipient: AddressStr
    amount: IDRCAmount = Field(..., gt=0)
    caller: AddressStr = Field(..., description="Caller address (must have RELAYER_ADMIN_ROLE)")


class UpgradeRequest(BaseModel):
    new_implementation: AddressStr
    caller: AddressStr = Field(..., description="Caller address (must have UPGRADER_ROLE)")
    init_data: Optional[str] = None


# ============================================================
# Response Models
# ============================================================

class BaseResponse(BaseModel):
    success: bool = True
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TokenInfoResponse(BaseResponse):
    name: str
    symbol: str
    decimals: int
    total_supply: IDRCAmount
    supply_cap: IDRCAmount
    paused: bool
    reserve_proof_hash: str


class BalanceResponse(BaseResponse):
    address: AddressStr
    balance: IDRCAmount
    balance_wei: WeiAmount


class AllowanceResponse(BaseResponse):
    owner: AddressStr
    spender: AddressStr
    allowance: IDRCAmount
    allowance_wei: WeiAmount


class TransactionResponse(BaseResponse):
    tx_hash: str
    status: TransactionStatus
    block_number: Optional[int] = None
    gas_used: Optional[int] = None


class MultisigTransactionResponse(BaseResponse):
    transaction_id: int
    to: AddressStr
    value: WeiAmount
    data: str
    executed: bool
    confirmations: int
    threshold: int
    confirmers: List[AddressStr]
    proposed_by: AddressStr
    submission_time: datetime


class MultisigListResponse(BaseResponse):
    pending: List[MultisigTransactionResponse]
    confirmed: List[MultisigTransactionResponse]
    executed: List[MultisigTransactionResponse]


class RoleResponse(BaseResponse):
    role: Role
    members: List[AddressStr]


class ReserveStatusResponse(BaseResponse):
    fiat_balance_idr: IDRCAmount
    latest_proof_hash: str
    last_oracle_update: Optional[datetime]
    reserve_ratio: Decimal
    is_fully_collateralised: bool
    audit_report_count: int


class AuditReportResponse(BaseResponse):
    seq: int
    proof_hash: str
    reported_fiat_idr: IDRCAmount
    submitted_by: AddressStr
    timestamp: datetime


class BridgeStatusResponse(BaseResponse):
    chain_id: ChainId
    total_locked: IDRCAmount
    relayer: AddressStr
    vault_address: AddressStr
    token_address: AddressStr


class BridgeTransferResponse(BaseResponse):
    bridge_nonce: int
    src_chain: ChainId
    dst_chain: ChainId
    sender: AddressStr
    recipient: AddressStr
    amount: IDRCAmount
    lock_tx_hash: str


class AlertResponse(BaseResponse):
    level: AlertLevel
    code: str
    message: str
    timestamp: datetime


class DashboardResponse(BaseResponse):
    token: TokenInfoResponse
    reserve: ReserveStatusResponse
    multisig: Dict[str, Any]
    alerts: List[AlertResponse]
    top_holders: List[Dict[str, Any]]
    recent_events: List[str]


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# WebSocket Models
# ============================================================

class WSMessage(BaseModel):
    type: str
    payload: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WSSubscription(BaseModel):
    channels: List[str]  # e.g., ["token.transfers", "multisig.tx", "reserve.updates", "bridge.events"]

# ============================================================
# Financial Ledger Models
# ============================================================

class AccountType(str, Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"

class EntryStatus(str, Enum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"

class ReconciliationStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"

class AccountBase(BaseModel):
    code: str = Field(..., max_length=20, description="Account code (e.g., 1010)")
    name: str = Field(..., max_length=100)
    type: AccountType
    currency: str = Field(default="IDR", max_length=3)
    parent_code: Optional[str] = Field(None, max_length=20)
    is_active: bool = True
    description: Optional[str] = None

class AccountCreate(AccountBase):
    pass

class AccountResponse(AccountBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class JournalLineBase(BaseModel):
    account_code: str = Field(..., max_length=20)
    debit: int = Field(default=0, ge=0, description="Debit amount in wei")
    credit: int = Field(default=0, ge=0, description="Credit amount in wei")
    description: Optional[str] = None

class JournalLineCreate(JournalLineBase):
    pass

class JournalLineResponse(JournalLineBase):
    id: str
    journal_entry_id: str
    line_number: int
    account_name: Optional[str] = None

    class Config:
        from_attributes = True

class JournalEntryBase(BaseModel):
    entry_date: date
    description: str
    reference_type: str = Field(..., max_length=50)
    reference_id: Optional[str] = Field(None, max_length=100)

class JournalEntryCreate(JournalEntryBase):
    lines: List[JournalLineCreate] = Field(..., min_length=2)

class JournalEntryPost(BaseModel):
    posted_by: Optional[str] = None

class JournalEntryReverse(BaseModel):
    reversed_by: Optional[str] = None
    reason: str = Field(..., min_length=1)

class JournalEntryResponse(JournalEntryBase):
    id: str
    entry_number: int
    status: EntryStatus
    created_by: Optional[str] = None
    created_at: datetime
    posted_at: Optional[datetime] = None
    posted_by: Optional[str] = None
    reversed_at: Optional[datetime] = None
    reversed_by: Optional[str] = None
    reversal_reason: Optional[str] = None
    prev_hash: Optional[str] = None
    lines: List[JournalLineResponse] = []

    class Config:
        from_attributes = True

class ReconciliationBase(BaseModel):
    reconciliation_date: date
    type: str = Field(..., max_length=50)
    expected_value: int = Field(..., ge=0)
    actual_value: int = Field(..., ge=0)
    difference: int
    status: ReconciliationStatus = ReconciliationStatus.OPEN
    notes: Optional[str] = None

class ReconciliationResponse(ReconciliationBase):
    id: str
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class FinancialSnapshotBase(BaseModel):
    snapshot_date: date
    snapshot_type: str = Field(..., max_length=20)
    total_fiat_reserve: int = Field(default=0, ge=0)
    customer_liability_reserve: int = Field(default=0, ge=0)
    operational_cash: int = Field(default=0, ge=0)
    fee_revenue_reserve: int = Field(default=0, ge=0)
    pending_deposits: int = Field(default=0, ge=0)
    encumbered_reserve: int = Field(default=0, ge=0)
    total_token_liability: int = Field(default=0, ge=0)
    pending_withdrawals: int = Field(default=0, ge=0)
    onchain_total_supply: int = Field(default=0, ge=0)
    onchain_reserve_balance: int = Field(default=0, ge=0)
    collateralization_ratio_bps: Optional[int] = None

class FinancialSnapshotResponse(FinancialSnapshotBase):
    id: str
    prev_snapshot_hash: Optional[str] = None
    snapshot_hash: str
    created_at: datetime

    class Config:
        from_attributes = True

class DailyReconciliationRequest(BaseModel):
    reconciliation_date: date = Field(default_factory=date.today)

class FinancialHealthResponse(BaseModel):
    total_token_liability: IDRCAmount
    total_fiat_reserve: IDRCAmount
    collateralization_ratio_bps: Optional[int]
    is_fully_collateralized: bool
    supply_cap_utilization_bps: Optional[int]
    pending_deposits: IDRCAmount
    pending_withdrawals: IDRCAmount
    encumbered_reserve: IDRCAmount
    fee_revenue: IDRCAmount
    last_reconciliation_date: Optional[date]
    reconciliation_status: Dict[str, ReconciliationStatus]
