"""
Token router - ERC-20 token operations
"""
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session_dependency
from ..auth import get_current_user, require_minter, require_burner, require_pauser, require_blacklister
from ..models import (
    TokenMintRequest, TokenBurnRequest, TokenTransferRequest,
    TokenApproveRequest, TokenPermitRequest, TokenInfoResponse,
    BalanceResponse, AllowanceResponse, TransactionResponse,
    AddressStr, IDRCAmount, WeiAmount
)
from ..blockchain import get_token_contract, get_multisig_contract
from ..services.token_service import TokenService

router = APIRouter()


@router.get("/info", response_model=TokenInfoResponse)
async def get_token_info(
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get token information"""
    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    return await service.get_token_info()


@router.get("/balance/{address}", response_model=BalanceResponse)
async def get_balance(
    address: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get token balance for an address"""
    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    balance = await service.balance_of(address)
    return BalanceResponse(
        address=address,
        balance=IDRCAmount(balance / 10**18),
        balance_wei=WeiAmount(balance)
    )


@router.get("/allowance", response_model=AllowanceResponse)
async def get_allowance(
    owner: AddressStr,
    spender: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get allowance between owner and spender"""
    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    allowance = await service.allowance(owner, spender)
    return AllowanceResponse(
        owner=owner,
        spender=spender,
        allowance=IDRCAmount(allowance / 10**18),
        allowance_wei=WeiAmount(allowance)
    )


@router.post("/mint", response_model=TransactionResponse)
async def mint_tokens(
    request: TokenMintRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_minter),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Mint new IDRC tokens (requires MINTER_ROLE)"""
    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    tx_hash = await service.mint(request.to, request.amount.to_wei(), request.caller)
    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.post("/burn", response_model=TransactionResponse)
async def burn_tokens(
    request: TokenBurnRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_burner),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Burn IDRC tokens from an address (requires BURNER_ROLE)"""
    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    tx_hash = await service.issuer_burn(request.from_address, request.amount.to_wei(), request.caller)
    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.post("/user-burn", response_model=TransactionResponse)
async def user_burn(
    request: TokenBurnRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Burn own IDRC tokens (any holder can call)"""
    # Verify caller is burning their own tokens
    if request.caller != request.from_address:
        raise HTTPException(status_code=400, detail="Can only burn own tokens")

    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    tx_hash = await service.burn(request.amount.to_wei(), request.caller)
    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.post("/transfer", response_model=TransactionResponse)
async def transfer_tokens(
    request: TokenTransferRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Transfer IDRC tokens"""
    # Verify caller is the sender
    if request.caller != request.from_address:
        raise HTTPException(status_code=400, detail="Caller must be sender")

    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    tx_hash = await service.transfer(request.to, request.amount.to_wei(), request.caller)
    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.post("/approve", response_model=TransactionResponse)
async def approve_spender(
    request: TokenApproveRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Approve spender allowance"""
    if request.caller != request.owner:
        raise HTTPException(status_code=400, detail="Caller must be owner")

    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    tx_hash = await service.approve(request.spender, request.amount.to_wei(), request.caller)
    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.post("/permit", response_model=TransactionResponse)
async def permit(
    request: TokenPermitRequest,
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """EIP-2612 permit (gasless approval)"""
    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    tx_hash = await service.permit(
        request.owner, request.spender, request.value.to_wei(),
        request.deadline, request.v, request.r, request.s
    )
    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.post("/pause", response_model=TransactionResponse)
async def pause_token(
    caller: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_pauser),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Pause all token transfers (requires PAUSER_ROLE)"""
    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    tx_hash = await service.pause(caller)
    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.post("/unpause", response_model=TransactionResponse)
async def unpause_token(
    caller: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_pauser),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Unpause token transfers (requires PAUSER_ROLE)"""
    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    tx_hash = await service.unpause(caller)
    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.post("/blacklist", response_model=TransactionResponse)
async def blacklist_address(
    request: BlacklistRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_blacklister),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Blacklist an address (requires BLACKLISTER_ROLE)"""
    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    tx_hash = await service.blacklist(request.account, request.caller)
    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.post("/unblacklist", response_model=TransactionResponse)
async def unblacklist_address(
    request: BlacklistRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_blacklister),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Remove address from blacklist (requires BLACKLISTER_ROLE)"""
    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    tx_hash = await service.unblacklist(request.account, request.caller)
    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.get("/is-blacklisted/{address}")
async def check_blacklisted(
    address: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Check if address is blacklisted"""
    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    is_blacklisted = await service.is_blacklisted(address)
    return {"address": address, "is_blacklisted": is_blacklisted}


@router.get("/holders")
async def get_top_holders(
    limit: int = Query(10, ge=1, le=100),
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get top token holders"""
    token = await get_token_contract(chain_id)
    service = TokenService(token, chain_id)
    holders = await service.get_top_holders(limit)
    return {"holders": holders}