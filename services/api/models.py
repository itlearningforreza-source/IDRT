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