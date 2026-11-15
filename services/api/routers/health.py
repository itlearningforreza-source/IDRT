"""
Health check endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session_dependency
from ..blockchain import get_blockchain_status

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check"""
    return {"status": "healthy", "service": "idrc-api"}


@router.get("/health/ready")
async def readiness_check(
    session: AsyncSession = Depends(get_session_dependency),
):
    """Readiness check - verifies database and blockchain connectivity"""
    checks = {}

    # Database check
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)}"

    # Blockchain check
    try:
        blockchain_status = await get_blockchain_status()
        checks["blockchain"] = "healthy" if blockchain_status["connected"] else "unhealthy"
        checks["blockchain_details"] = blockchain_status
    except Exception as e:
        checks["blockchain"] = f"unhealthy: {str(e)}"

    all_healthy = all(v == "healthy" for v in checks.values() if isinstance(v, str))

    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks
    }


@router.get("/health/live")
async def liveness_check():
    """Liveness check - just verifies the process is alive"""
    return {"status": "alive"}


@router.get("/version")
async def version():
    """Version info"""
    return {
        "version": "1.0.0",
        "name": "IDRC API",
        "build": "production"
    }