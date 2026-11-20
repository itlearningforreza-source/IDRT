"""
Correlation ID Middleware
Adds request correlation IDs for distributed tracing
"""
import uuid
import logging
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .config import get_settings


logger = logging.getLogger("idrc.correlation")


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add correlation IDs to requests and responses"""
    
    def __init__(
        self,
        app: ASGIApp,
        header_name: str = "X-Correlation-ID",
        generator: Optional[callable] = None,
        validator: Optional[callable] = None,
    ):
        super().__init__(app)
        self.header_name = header_name
        self.generator = generator or (lambda: str(uuid.uuid4()))
        self.validator = validator or (lambda x: True)
    
    async def dispatch(self, request: Request, call_next):
        # Get or generate correlation ID
        correlation_id = request.headers.get(self.header_name)
        
        if not correlation_id or not self.validator(correlation_id):
            correlation_id = self.generator()
        
        # Add to request state for access in handlers
        request.state.correlation_id = correlation_id
        
        # Add to logging context
        logging_context = {
            "correlation_id": correlation_id,
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else "unknown",
        }
        
        # Bind correlation ID to logger
        logger_ctx = logging.LoggerAdapter(logger, logging_context)
        logger_ctx.info("Request started")
        
        # Process request
        start_time = time.time()
        try:
            response = await call_next(request)
            
            # Add correlation ID to response headers
            response.headers[self.header_name] = correlation_id
            
            # Log completion
            duration = time.time() - start_time
            logger_ctx.info(
                "Request completed",
                extra={
                    "status_code": response.status_code,
                    "duration_ms": round(duration * 1000, 2),
                }
            )
            
            return response
            
        except Exception as e:
            # Log error
            duration = time.time() - start_time
            logger_ctx.error(
                "Request failed",
                extra={
                    "error": str(e),
                    "duration_ms": round(duration * 1000, 2),
                },
                exc_info=True
            )
            raise


def get_correlation_id(request: Request) -> str:
    """Get correlation ID from request state"""
    return getattr(request.state, "correlation_id", "unknown")


def set_correlation_id(request: Request, correlation_id: str):
    """Set correlation ID on request state"""
    request.state.correlation_id = correlation_id
