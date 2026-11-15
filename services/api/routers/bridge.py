"""
Bridge router - Cross-chain bridge operations
"""
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session_dependency
from ..auth import get_current_user, require_relayer, require_relayer_admin
from ..models import (
    BridgeTransferRequest, BridgeCompleteRequest,
    BridgeStatusResponse, BridgeTransferResponse,
    AddressStr, IDRCAmount, ChainId
)
from ..blockchain import get_bridge_contracts
from ..services.bridge_service import BridgeService

router = APIRouter()


@router.get("/status", response_model=list[BridgeStatusResponse])
async def get_bridge_status(
    chain_id: int = Query(None, description="Specific chain ID (optional)"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get bridge status for all chains or specific chain"""
    contracts = await get_bridge_contracts(chain_id)
    service = BridgeService(contracts)

    if chain_id:
        status = await service.get_chain_status(chain_id)
        return [status]
    return await service.get_all_chains_status()


@router.get("/chains")
async def get_supported_chains(
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get list of supported chains"""
    contracts = await get_bridge_contracts()
    service = BridgeService(contracts)
    return {"chains": await service.get_supported_chains()}


@router.post("/transfer", response_model=BridgeTransferResponse)
async def initiate_transfer(
    request: BridgeTransferRequest,
    session: AsyncSession = Depends(get_session_dependency),
    current_user = Depends(require_relayer),
):
    """Initiate cross-chain transfer (requires RELAYER_ROLE)"""
    contracts = await get_bridge_contracts(request.src_chain)
    service = BridgeService(contracts)

    result = await service.transfer(
        request.src_chain,
        request.dst_chain,
        request.sender,
        request.recipient,
        request.amount.to_wei(),
        request.caller
    )
    return BridgeTransferResponse(**result)


@router.post("/complete", response_model=dict)
async def complete_transfer(
    request: BridgeCompleteRequest,
    session: AsyncSession = Depends(get_session_dependency),
    current_user = Depends(require_relayer_admin),
):
    """Complete cross-chain transfer on destination chain (requires RELAYER_ADMIN_ROLE)"""
    contracts = await get_bridge_contracts(request.dst_chain)
    service = BridgeService(contracts)

    tx_hash = await service.complete_transfer(
        request.bridge_nonce,
        request.src_chain,
        request.dst_chain,
        request.recipient,
        request.amount.to_wei(),
        request.caller
    )
    return {"tx_hash": tx_hash, "status": "PENDING"}


@router.get("/nonce/{bridge_nonce}")
async def check_nonce_processed(
    bridge_nonce: int,
    src_chain: ChainId,
    chain_id: int = Query(1, description="Destination chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Check if bridge nonce has been processed"""
    contracts = await get_bridge_contracts(chain_id)
    service = BridgeService(contracts)
    processed = await service.is_nonce_processed(bridge_nonce, src_chain)
    return {"bridge_nonce": bridge_nonce, "src_chain": src_chain, "processed": processed}


@router.get("/locked/{address}")
async def get_locked_balance(
    address: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get locked balance for an address"""
    contracts = await get_bridge_contracts(chain_id)
    service = BridgeService(contracts)
    locked = await service.get_locked_balance(address)
    return {"address": address, "locked": IDRCAmount(locked / 10**18)}


@router.post("/relayer/set")
async def set_relayer(
    new_relayer: AddressStr,
    caller: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Set new relayer address (requires RELAYER_ADMIN_ROLE)"""
    contracts = await get_bridge_contracts(chain_id)
    service = BridgeService(contracts)

    if not await service.has_relayer_admin_role(caller):
        raise HTTPException(status_code=403, detail="Requires RELAYER_ADMIN_ROLE")

    tx_hash = await service.set_relayer(new_relayer, caller)
    return {"tx_hash": tx_hash, "status": "PENDING"}


@router.post("/pause")
async def pause_bridge(
    caller: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Pause bridge operations"""
    contracts = await get_bridge_contracts(chain_id)
    service = BridgeService(contracts)

    if not await service.has_relayer_admin_role(caller):
        raise HTTPException(status_code=403, detail="Requires RELAYER_ADMIN_ROLE")

    tx_hash = await service.pause(caller)
    return {"tx_hash": tx_hash, "status": "PENDING"}


@router.post("/unpause")
async def unpause_bridge(
    caller: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Unpause bridge operations"""
    contracts = await get_bridge_contracts(chain_id)
    service = BridgeService(contracts)

    if not await service.has_relayer_admin_role(caller):
        raise HTTPException(status_code=403, detail="Requires RELAYER_ADMIN_ROLE")

    tx_hash = await service.unpause(caller)
    return {"tx_hash": tx_hash, "status": "PENDING"}