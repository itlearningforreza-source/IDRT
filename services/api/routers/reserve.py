"""
Reserve router - Proof of Reserve operations
"""
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session_dependency
from ..auth import get_current_user, require_auditor, require_oracle
from ..models import (
    ReserveProofRequest, ReserveOracleUpdateRequest,
    ReserveStatusResponse, AuditReportResponse,
    AddressStr, IDRCAmount
)
from ..blockchain import get_reserve_contract
from ..services.reserve_service import ReserveService

router = APIRouter()


@router.get("/status", response_model=ReserveStatusResponse)
async def get_reserve_status(
    chain_id: int = Query(1, description="Chain ID"),
    token_supply: str = Query(..., description="Current token total supply in wei"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get reserve status including collateralization ratio"""
    reserve = await get_reserve_contract(chain_id)
    service = ReserveService(reserve, chain_id)

    status = await service.get_status(int(token_supply))
    return ReserveStatusResponse(**status)


@router.get("/audit-reports", response_model=list[AuditReportResponse])
async def get_audit_reports(
    chain_id: int = Query(1, description="Chain ID"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get audit reports"""
    reserve = await get_reserve_contract(chain_id)
    service = ReserveService(reserve, chain_id)
    reports = await service.get_audit_reports(limit, offset)
    return [AuditReportResponse(**r) for r in reports]


@router.get("/audit-reports/{seq}", response_model=AuditReportResponse)
async def get_audit_report(
    seq: int,
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get specific audit report by sequence number"""
    reserve = await get_reserve_contract(chain_id)
    service = ReserveService(reserve, chain_id)
    report = await service.get_audit_report(seq)
    if not report:
        raise HTTPException(status_code=404, detail="Audit report not found")
    return AuditReportResponse(**report)


@router.post("/audit-proof", response_model=dict)
async def submit_audit_proof(
    request: ReserveProofRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_auditor),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Submit audit proof hash (requires AUDITOR_ROLE)"""
    reserve = await get_reserve_contract(chain_id)
    service = ReserveService(reserve, chain_id)
    tx_hash = await service.submit_audit_proof(
        request.proof_hash, request.reported_fiat_idr.to_wei(), request.caller
    )
    return {"tx_hash": tx_hash, "status": "PENDING"}


@router.post("/oracle/update", response_model=dict)
async def update_fiat_balance(
    request: ReserveOracleUpdateRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_oracle),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Update fiat balance from oracle (requires ORACLE_ROLE)"""
    reserve = await get_reserve_contract(chain_id)
    service = ReserveService(reserve, chain_id)
    tx_hash = await service.update_fiat_balance(request.new_balance_idr.to_wei(), request.caller)
    return {"tx_hash": tx_hash, "status": "PENDING"}


@router.post("/oracle/set", response_model=dict)
async def set_oracle(
    new_oracle: AddressStr,
    caller: AddressStr,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Set new oracle address (requires DEFAULT_ADMIN_ROLE)"""
    # Check if caller has admin role
    reserve = await get_reserve_contract(chain_id)
    service = ReserveService(reserve, chain_id)

    if not await service.has_role("DEFAULT_ADMIN_ROLE", caller):
        raise HTTPException(status_code=403, detail="Requires DEFAULT_ADMIN_ROLE")

    tx_hash = await service.set_oracle(new_oracle, caller)
    return {"tx_hash": tx_hash, "status": "PENDING"}


@router.get("/verify-proof")
async def verify_proof(
    report_data: str,
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Verify audit proof against on-chain hash"""
    reserve = await get_reserve_contract(chain_id)
    service = ReserveService(reserve, chain_id)
    is_valid = await service.verify_proof(report_data)
    return {"valid": is_valid}


@router.get("/collateralisation-check")
async def check_collateralisation(
    token_supply: str = Query(..., description="Token total supply in wei"),
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Check if reserve is fully collateralised"""
    reserve = await get_reserve_contract(chain_id)
    service = ReserveService(reserve, chain_id)
    is_fully = await service.check_collateralisation(int(token_supply))
    ratio = await service.reserve_ratio(int(token_supply))
    return {
        "is_fully_collateralised": is_fully,
        "reserve_ratio": Decimal(ratio) / 10**18,
        "min_ratio": Decimal(1.0)
    }