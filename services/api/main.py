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

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from .database import init_db, close_db
from .auth import get_current_user, require_roles
from .routers import token, multisig, reserve, bridge, admin, health, ledger
from .config import get_settings
from .middleware.rate_limiter import rate_limit_middleware, init_rate_limiter, close_rate_limiter
from .middleware.idempotency import IdempotencyMiddleware, init_idempotency_store, close_idempotency_store
from .middleware.correlation import CorrelationIDMiddleware
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
    settings = get_settings()
    
    # Startup
    logger.info("Starting IDRC API...")
    await init_db()

    # Initialize blockchain connections
    from .blockchain import init_blockchain
    await init_blockchain()

    # Initialize rate limiter
    if settings.RATE_LIMIT_ENABLED:
        await init_rate_limiter(settings.REDIS_URL)
        logger.info("Rate limiter initialized")
    
    # Initialize idempotency store
    if settings.IDEMPOTENCY_ENABLED:
        await init_idempotency_store(settings.REDIS_URL)
        logger.info("Idempotency store initialized")

    logger.info("IDRC API started successfully")
    yield

    # Shutdown
    logger.info("Shutting down IDRC API...")
    await close_db()
    await close_rate_limiter()
    await close_idempotency_store()
    logger.info("IDRC API shut down complete")


settings = get_settings()

app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.APP_VERSION,
    docs_url="/docs" if not settings.is_production() else None,
    redoc_url="/redoc" if not settings.is_production() else None,
    openapi_url="/openapi.json" if not settings.is_production() else None,
    lifespan=lifespan,
)

# Security middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS
)

# Correlation ID middleware (first - for tracing)
app.add_middleware(CorrelationIDMiddleware, header_name=settings.CORRELATION_HEADER_NAME)

# Idempotency middleware (early - for financial operations)
if settings.IDEMPOTENCY_ENABLED:
    app.add_middleware(IdempotencyMiddleware)

# Rate limiting middleware (early - before processing)
if settings.RATE_LIMIT_ENABLED:
    app.middleware("http")(rate_limit_middleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# Static files for frontend
if os.path.exists(settings.STATIC_DIR):
    app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")


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
