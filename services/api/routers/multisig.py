"""
Multisig router - Multisig wallet operations
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session_dependency
from ..auth import get_current_user
from ..models import (
    MultisigProposeRequest, MultisigConfirmRequest, MultisigExecuteRequest,
    MultisigListResponse, MultisigTransactionResponse,
    AddressStr, WeiAmount
)
from ..blockchain import get_multisig_contract
from ..services.multisig_service import MultisigService

router = APIRouter()


@router.post("/propose", response_model=MultisigTransactionResponse)
async def propose_transaction(
    request: MultisigProposeRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Propose a new multisig transaction"""
    # Verify caller is an owner
    multisig = await get_multisig_contract(chain_id)
    service = MultisigService(multisig, chain_id)

    if not await service.is_owner(request.caller):
        raise HTTPException(status_code=403, detail="Caller is not a multisig owner")

    tx_id = await service.propose(
        request.to, WeiAmount(request.value), request.data, request.caller
    )

    tx = await service.get_transaction(tx_id)
    return _format_multisig_tx(tx, tx_id)


@router.post("/confirm", response_model=MultisigTransactionResponse)
async def confirm_transaction(
    request: MultisigConfirmRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Confirm a pending multisig transaction"""
    multisig = await get_multisig_contract(chain_id)
    service = MultisigService(multisig, chain_id)

    if not await service.is_owner(request.caller):
        raise HTTPException(status_code=403, detail="Caller is not a multisig owner")

    await service.confirm(request.transaction_id, request.caller)
    tx = await service.get_transaction(request.transaction_id)
    return _format_multisig_tx(tx, request.transaction_id)


@router.post("/execute", response_model=MultisigTransactionResponse)
async def execute_transaction(
    request: MultisigExecuteRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Execute a confirmed multisig transaction"""
    multisig = await get_multisig_contract(chain_id)
    service = MultisigService(multisig, chain_id)

    if not await service.is_owner(request.caller):
        raise HTTPException(status_code=403, detail="Caller is not a multisig owner")

    await service.execute(request.transaction_id, request.caller)
    tx = await service.get_transaction(request.transaction_id)
    return _format_multisig_tx(tx, request.transaction_id)


@router.post("/revoke", response_model=MultisigTransactionResponse)
async def revoke_confirmation(
    request: MultisigConfirmRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Revoke confirmation for a multisig transaction"""
    multisig = await get_multisig_contract(chain_id)
    service = MultisigService(multisig, chain_id)

    if not await service.is_owner(request.caller):
        raise HTTPException(status_code=403, detail="Caller is not a multisig owner")

    await service.revoke(request.transaction_id, request.caller)
    tx = await service.get_transaction(request.transaction_id)
    return _format_multisig_tx(tx, request.transaction_id)


@router.get("/pending", response_model=MultisigListResponse)
async def get_pending_transactions(
    chain_id: int = Query(1, description="Chain ID"),
    from_id: int = Query(0, ge=0),
    to_id: int = Query(100, ge=0),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get pending, confirmed, and executed transactions"""
    multisig = await get_multisig_contract(chain_id)
    service = MultisigService(multisig, chain_id)

    pending, confirmed, executed = await service.get_transaction_lists(from_id, to_id)
    return MultisigListResponse(
        pending=[_format_multisig_tx(tx, i) for i, tx in enumerate(pending)],
        confirmed=[_format_multisig_tx(tx, i) for i, tx in enumerate(confirmed)],
        executed=[_format_multisig_tx(tx, i) for i, tx in enumerate(executed)],
    )


@router.get("/transaction/{tx_id}", response_model=MultisigTransactionResponse)
async def get_transaction(
    tx_id: int,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get a specific multisig transaction"""
    multisig = await get_multisig_contract(chain_id)
    service = MultisigService(multisig, chain_id)

    tx = await service.get_transaction(tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return _format_multisig_tx(tx, tx_id)


@router.get("/owners")
async def get_owners(
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get multisig owners"""
    multisig = await get_multisig_contract(chain_id)
    service = MultisigService(multisig, chain_id)
    owners = await service.get_owners()
    return {"owners": owners, "count": len(owners)}


@router.get("/threshold")
async def get_threshold(
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get multisig threshold"""
    multisig = await get_multisig_contract(chain_id)
    service = MultisigService(multisig, chain_id)
    threshold = await service.get_threshold()
    return {"threshold": threshold}


@router.get("/is-owner/{address}")
async def check_owner(
    address: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Check if address is a multisig owner"""
    multisig = await get_multisig_contract(chain_id)
    service = MultisigService(multisig, chain_id)
    is_owner = await service.is_owner(address)
    return {"address": address, "is_owner": is_owner}


@router.post("/add-owner")
async def add_owner(
    new_owner: AddressStr,
    new_threshold: int,
    caller: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Add a new owner (requires multisig transaction)"""
    multisig = await get_multisig_contract(chain_id)
    service = MultisigService(multisig, chain_id)

    if not await service.is_owner(caller):
        raise HTTPException(status_code=403, detail="Caller is not a multisig owner")

    # This would be done via a multisig transaction in practice
    # For now, direct call (requires owner)
    await service.add_owner(new_owner, new_threshold, caller)
    return {"message": f"Owner {new_owner} added with threshold {new_threshold}"}


@router.post("/remove-owner")
async def remove_owner(
    owner: AddressStr,
    new_threshold: int,
    caller: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Remove an owner (requires multisig transaction)"""
    multisig = await get_multisig_contract(chain_id)
    service = MultisigService(multisig, chain_id)

    if not await service.is_owner(caller):
        raise HTTPException(status_code=403, detail="Caller is not a multisig owner")

    await service.remove_owner(owner, new_threshold, caller)
    return {"message": f"Owner {owner} removed with threshold {new_threshold}"}


@router.post("/change-threshold")
async def change_threshold(
    new_threshold: int,
    caller: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Change multisig threshold"""
    multisig = await get_multisig_contract(chain_id)
    service = MultisigService(multisig, chain_id)

    if not await service.is_owner(caller):
        raise HTTPException(status_code=403, detail="Caller is not a multisig owner")

    await service.change_threshold(new_threshold, caller)
    return {"message": f"Threshold changed to {new_threshold}"}


def _format_multisig_tx(tx, tx_id):
    """Format multisig transaction for response"""
    return MultisigTransactionResponse(
        transaction_id=tx_id,
        to=tx["to"],
        value=WeiAmount(tx["value"]),
        data=tx["data"],
        executed=tx["executed"],
        confirmations=tx["confirmations"],
        threshold=tx["threshold"],
        confirmers=tx["confirmers"],
        proposed_by=tx["proposed_by"],
        submission_time=tx["submission_time"]
    )
