"""
Idempotency Middleware
Ensures financial operations are safely retryable
"""
import hashlib
import json
import time
from typing import Optional, Any, Dict
from functools import wraps

from fastapi import Request, HTTPException, status, Response
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as redis

from .config import get_settings


class IdempotencyError(HTTPException):
    def __init__(self, detail: str = "Idempotency key already processed"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail
        )


class IdempotencyStore:
    """Redis-backed idempotency key store"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.settings = get_settings()
        self.default_ttl = 86400 * 7  # 7 days
    
    async def check_and_store(
        self,
        idempotency_key: str,
        request_hash: str,
        response_data: Optional[Dict] = None,
        ttl: Optional[int] = None
    ) -> tuple[bool, Optional[Dict]]:
        """
        Check if idempotency key exists and store result.
        Returns (is_new, existing_response)
        """
        key = f"idempotency:{idempotency_key}"
        
        # Try to get existing
        existing = await self.redis.get(key)
        if existing:
            try:
                stored = json.loads(existing)
                # Verify request hash matches
                if stored.get("request_hash") != request_hash:
                    raise IdempotencyError(
                        "Idempotency key reused with different request payload"
                    )
                # Return existing response
                return False, stored.get("response")
            except json.JSONDecodeError:
                # Corrupted data, treat as new
                pass
        
        # Store new entry
        ttl = ttl or self.default_ttl
        entry = {
            "request_hash": request_hash,
            "response": response_data,
            "created_at": time.time(),
            "status": "processing" if response_data is None else "completed"
        }
        await self.redis.setex(key, ttl, json.dumps(entry))
        return True, None
    
    async def update_response(
        self,
        idempotency_key: str,
        response_data: Dict
    ) -> bool:
        """Update stored response after processing"""
        key = f"idempotency:{idempotency_key}"
        existing = await self.redis.get(key)
        if not existing:
            return False
        
        try:
            stored = json.loads(existing)
            stored["response"] = response_data
            stored["status"] = "completed"
            stored["completed_at"] = time.time()
            await self.redis.set(key, json.dumps(stored))
            return True
        except json.JSONDecodeError:
            return False
    
    async def get_status(self, idempotency_key: str) -> Optional[Dict]:
        """Get idempotency key status"""
        key = f"idempotency:{idempotency_key}"
        existing = await self.redis.get(key)
        if not existing:
            return None
        try:
            return json.loads(existing)
        except json.JSONDecodeError:
            return None
    
    async def delete(self, idempotency_key: str) -> bool:
        """Delete idempotency key"""
        key = f"idempotency:{idempotency_key}"
        result = await self.redis.delete(key)
        return result > 0


# Global idempotency store
_idempotency_store: Optional[IdempotencyStore] = None


def get_idempotency_store() -> Optional[IdempotencyStore]:
    return _idempotency_store


async def init_idempotency_store(redis_url: str) -> IdempotencyStore:
    """Initialize global idempotency store"""
    global _idempotency_store
    client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    _idempotency_store = IdempotencyStore(client)
    return _idempotency_store


async def close_idempotency_store():
    """Close idempotency store connection"""
    global _idempotency_store
    if _idempotency_store and _idempotency_store.redis:
        await _idempotency_store.redis.close()
    _idempotency_store = None


# ============================================================
# Middleware
# ============================================================

class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware to handle idempotency keys for financial operations"""
    
    # Endpoints that require idempotency
    IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH"}
    IDEMPOTENT_PATHS = {
        "/api/v1/token/mint",
        "/api/v1/token/burn",
        "/api/v1/token/user-burn",
        "/api/v1/token/transfer",
        "/api/v1/bridge/lock",
        "/api/v1/bridge/release",
        "/api/v1/bridge/relay",
        "/api/v1/reserve/update-fiat-balance",
        "/api/v1/reserve/submit-audit-proof",
        "/api/v1/multisig/transactions",
        "/api/v1/admin/mint",
        "/api/v1/admin/burn",
        "/api/v1/admin/pause",
        "/api/v1/admin/unpause",
    }
    
    async def dispatch(self, request: Request, call_next):
        # Only apply to mutating methods on financial endpoints
        if request.method not in self.IDEMPOTENT_METHODS:
            return await call_next(request)
        
        # Check if path requires idempotency
        path = request.url.path
        requires_idempotency = any(path.startswith(p) for p in self.IDEMPOTENT_PATHS)
        
        if not requires_idempotency:
            return await call_next(request)
        
        # Get idempotency key
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Idempotency-Key header required for this endpoint"
            )
        
        # Validate key format (UUID or similar)
        if len(idempotency_key) < 16 or len(idempotency_key) > 128:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Idempotency-Key format"
            )
        
        # Read request body for hashing
        body = await request.body()
        request_hash = hashlib.sha256(body).hexdigest()
        
        # Check idempotency store
        store = get_idempotency_store()
        if not store:
            # No store configured, skip idempotency check
            return await call_next(request)
        
        try:
            is_new, existing_response = await store.check_and_store(
                idempotency_key=idempotency_key,
                request_hash=request_hash
            )
        except IdempotencyError as e:
            return Response(
                content=json.dumps({"error": "Idempotency conflict", "detail": e.detail}),
                status_code=status.HTTP_409_CONFLICT,
                media_type="application/json"
            )
        
        if not is_new and existing_response:
            # Return cached response
            return Response(
                content=json.dumps(existing_response.get("body", {})),
                status_code=existing_response.get("status_code", 200),
                headers=existing_response.get("headers", {}),
                media_type="application/json"
            )
        
        # Process request
        response = await call_next(request)
        
        # Capture response for caching
        if response.status_code < 400:
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk
            
            try:
                response_data = json.loads(response_body.decode())
            except json.JSONDecodeError:
                response_data = {"raw": response_body.decode()}
            
            # Update store with response
            await store.update_response(
                idempotency_key=idempotency_key,
                response_data={
                    "body": response_data,
                    "status_code": response.status_code,
                    "headers": dict(response.headers)
                }
            )
            
            # Return new response with captured body
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )
        
        return response


# ============================================================
# Decorator for Function-Level Idempotency
# ============================================================

def idempotent(key_func: Optional[callable] = None, ttl: int = 86400 * 7):
    """Decorator for function-level idempotency"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            store = get_idempotency_store()
            if not store:
                return await func(*args, **kwargs)
            
            # Extract request
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request:
                request = kwargs.get("request")
            
            if not request:
                return await func(*args, **kwargs)
            
            # Get or generate idempotency key
            idempotency_key = request.headers.get("Idempotency-Key")
            if not idempotency_key:
                if key_func:
                    idempotency_key = key_func(request)
                else:
                    # Generate from function name and user
                    user_id = getattr(request.state, "user_id", "anonymous")
                    idempotency_key = f"auto:{func.__name__}:{user_id}:{time.time()}"
            
            # Read body for hash
            body = await request.body()
            request_hash = hashlib.sha256(body).hexdigest()
            
            # Check store
            is_new, existing = await store.check_and_store(
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                ttl=ttl
            )
            
            if not is_new and existing:
                return existing
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Store result
            await store.update_response(idempotency_key, result)
            
            return result
        return wrapper
    return decorator
