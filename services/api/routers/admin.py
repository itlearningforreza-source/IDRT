"""
Admin router - Administrative operations
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session_dependency
from ..auth import get_current_user, require_admin, require_upgrader
from ..models import (
    UpgradeRequest, RoleGrantRequest, RoleRevokeRequest,
    PauseRequest, BlacklistRequest, Role, RoleResponse,
    AddressStr, TransactionResponse
)
from ..blockchain import get_token_contract, get_reserve_contract, get_proxy_admin_contract
from ..services.admin_service import AdminService

router = APIRouter()


@router.post("/upgrade", response_model=TransactionResponse)
async def upgrade_contract(
    request: UpgradeRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_upgrader),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Upgrade token implementation via UUPS proxy (requires UPGRADER_ROLE)"""
    proxy_admin = await get_proxy_admin_contract(chain_id)
    service = AdminService(proxy_admin, chain_id)

    if request.init_data:
        tx_hash = await service.upgrade_and_call(
            request.new_implementation, request.init_data, request.caller
        )
    else:
        tx_hash = await service.upgrade(request.new_implementation, request.caller)

    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.get("/implementation")
async def get_implementation(
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get current implementation address"""
    proxy_admin = await get_proxy_admin_contract(chain_id)
    service = AdminService(proxy_admin, chain_id)
    impl = await service.get_implementation()
    return {"implementation": impl}


@router.get("/implementation-history")
async def get_implementation_history(
    chain_id: int = Query(1, description="Chain ID"),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get implementation upgrade history"""
    proxy_admin = await get_proxy_admin_contract(chain_id)
    service = AdminService(proxy_admin, chain_id)
    history = await service.get_implementation_history()
    return {"history": history}


@router.post("/role/grant", response_model=RoleResponse)
async def grant_role(
    request: RoleGrantRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_admin),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Grant role to address (requires DEFAULT_ADMIN_ROLE)"""
    token = await get_token_contract(chain_id)
    service = AdminService(token, chain_id)
    await service.grant_role(request.role.value, request.account, request.caller)
    members = await service.get_role_members(request.role.value)
    return RoleResponse(role=request.role, members=members)


@router.post("/role/revoke", response_model=RoleResponse)
async def revoke_role(
    request: RoleRevokeRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_admin),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Revoke role from address (requires DEFAULT_ADMIN_ROLE)"""
    token = await get_token_contract(chain_id)
    service = AdminService(token, chain_id)
    await service.revoke_role(request.role.value, request.account, request.caller)
    members = await service.get_role_members(request.role.value)
    return RoleResponse(role=request.role, members=members)


@router.get("/role/{role}/members", response_model=RoleResponse)
async def get_role_members(
    role: Role,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get all members of a role"""
    token = await get_token_contract(chain_id)
    service = AdminService(token, chain_id)
    members = await service.get_role_members(role.value)
    return RoleResponse(role=role, members=members)


@router.post("/pause", response_model=TransactionResponse)
async def pause_system(
    request: PauseRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_admin),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Pause entire system (token + bridge + reserve)"""
    # Pause token
    token = await get_token_contract(chain_id)
    admin_service = AdminService(token, chain_id)
    tx_hash = await admin_service.pause_token(request.caller)

    # Pause bridge
    from ..blockchain import get_bridge_contracts
    bridge_contracts = await get_bridge_contracts(chain_id)
    bridge_service = AdminService(bridge_contracts["relayer"], chain_id)
    await bridge_service.pause_bridge(request.caller)

    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.post("/unpause", response_model=TransactionResponse)
async def unpause_system(
    request: PauseRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_admin),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Unpause entire system"""
    token = await get_token_contract(chain_id)
    admin_service = AdminService(token, chain_id)
    tx_hash = await admin_service.unpause_token(request.caller)

    from ..blockchain import get_bridge_contracts
    bridge_contracts = await get_bridge_contracts(chain_id)
    bridge_service = AdminService(bridge_contracts["relayer"], chain_id)
    await bridge_service.unpause_bridge(request.caller)

    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.post("/blacklist", response_model=TransactionResponse)
async def blacklist_address_admin(
    request: BlacklistRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_admin),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Blacklist address via admin (requires DEFAULT_ADMIN_ROLE)"""
    token = await get_token_contract(chain_id)
    service = AdminService(token, chain_id)
    tx_hash = await service.blacklist(request.account, request.caller)
    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.post("/unblacklist", response_model=TransactionResponse)
async def unblacklist_address_admin(
    request: BlacklistRequest,
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_admin),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Unblacklist address via admin"""
    token = await get_token_contract(chain_id)
    service = AdminService(token, chain_id)
    tx_hash = await service.unblacklist(request.account, request.caller)
    return TransactionResponse(tx_hash=tx_hash, status="PENDING")


@router.get("/dashboard")
async def get_admin_dashboard(
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(require_admin),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get admin dashboard with system status"""
    from ..blockchain import get_token_contract, get_reserve_contract, get_multisig_contract, get_bridge_contracts
    from ..services.token_service import TokenService
    from ..services.reserve_service import ReserveService
    from ..services.multisig_service import MultisigService
    from ..services.bridge_service import BridgeService

    token = await get_token_contract(chain_id)
    reserve = await get_reserve_contract(chain_id)
    multisig = await get_multisig_contract(chain_id)
    bridge = await get_bridge_contracts(chain_id)

    token_service = TokenService(token, chain_id)
    reserve_service = ReserveService(reserve, chain_id)
    multisig_service = MultisigService(multisig, chain_id)
    bridge_service = BridgeService(bridge)

    # Gather all info
    token_info = await token_service.get_token_info()
    reserve_status = await reserve_service.get_status(token_info.total_supply)
    multisig_owners = await multisig_service.get_owners()
    multisig_threshold = await multisig_service.get_threshold()
    bridge_status = await bridge_service.get_all_chains_status()

    # Get alerts
    from ..services.monitor_service import MonitorService
    monitor = MonitorService(token, reserve, chain_id)
    alerts = await monitor.run_alert_checks()

    return {
        "token": token_info,
        "reserve": reserve_status,
        "multisig": {
            "owners": multisig_owners,
            "threshold": multisig_threshold,
            "address": str(multisig.address)
        },
        "bridge": bridge_status,
        "alerts": [{"level": a.level, "code": a.code, "message": a.message} for a in alerts]
    }


@router.get("/roles")
async def get_all_roles(
    chain_id: int = Query(1, description="Chain ID"),
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dependency),
):
    """Get all roles and their members"""
    token = await get_token_contract(chain_id)
    service = AdminService(token, chain_id)

    roles = [
        "DEFAULT_ADMIN_ROLE", "MINTER_ROLE", "BURNER_ROLE",
        "PAUSER_ROLE", "UPGRADER_ROLE", "BLACKLISTER_ROLE"
    ]

    result = {}
    for role in roles:
        members = await service.get_role_members(role)
        result[role] = members

    return {"roles": result}