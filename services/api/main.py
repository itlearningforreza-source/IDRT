"""
IDRC FastAPI Application
Production-ready API for IDR Coin stablecoin system
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from .database import init_db, close_db
from .auth import get_current_user, require_roles
from .routers import token, multisig, reserve, bridge, admin, health, ledger
from .models import User

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("idrc-api")

# Sentry initialization
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[
            FastApiIntegration(auto_enable=True),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment=os.getenv("ENVIRONMENT", "development"),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting IDRC API...")
    await init_db()

    # Initialize blockchain connections
    from .blockchain import init_blockchain
    await init_blockchain()

    logger.info("IDRC API started successfully")
    yield

    # Shutdown
    logger.info("Shutting down IDRC API...")
    await close_db()
    logger.info("IDRC API shut down complete")


app = FastAPI(
    title="IDRC API",
    description="Production API for IDR Coin (IDRC) Stablecoin System",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None,
    redoc_url="/redoc" if os.getenv("ENVIRONMENT") != "production" else None,
    openapi_url="/openapi.json" if os.getenv("ENVIRONMENT") != "production" else None,
    lifespan=lifespan,
)

# Security middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# Static files for frontend
static_dir = os.getenv("STATIC_DIR", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code}
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    if os.getenv("ENVIRONMENT") == "production":
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "status_code": 500}
        )
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "status_code": 500}
    )


# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(token.router, prefix="/api/v1/token", tags=["Token"])
app.include_router(multisig.router, prefix="/api/v1/multisig", tags=["Multisig"])
app.include_router(reserve.router, prefix="/api/v1/reserve", tags=["Reserve"])
app.include_router(bridge.router, prefix="/api/v1/bridge", tags=["Bridge"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])


# Root endpoint
@app.get("/")
async def root():
    return {
        "name": "IDRC API",
        "version": "1.0.0",
        "description": "IDR Coin Stablecoin API",
        "docs": "/docs",
        "health": "/api/v1/health"
    }


# WebSocket endpoint for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket):
    """WebSocket for real-time blockchain event updates"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # Echo for now - in production, subscribe to event streams
            await websocket.send_text(f"Echo: {data}")
    except Exception as e:
        logger.warning(f"WebSocket disconnected: {e}")
    finally:
        await websocket.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("ENVIRONMENT") == "development",
        workers=int(os.getenv("WORKERS", 1)),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
