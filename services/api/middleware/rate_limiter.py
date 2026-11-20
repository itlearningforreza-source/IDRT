"""
Rate Limiting Middleware
Redis-backed distributed rate limiting with configurable policies
"""
import time
from typing import Optional, Callable
from functools import wraps

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import redis.asyncio as redis

from .config import get_settings


class RateLimitExceeded(HTTPException):
    def __init__(self, detail: str = "Rate limit exceeded", retry_after: int = 60):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(retry_after)}
        )


class RateLimiter:
    """Redis-backed rate limiter with sliding window algorithm"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.settings = get_settings()
    
    async def is_allowed(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        cost: int = 1
    ) -> tuple[bool, dict]:
        """
        Check if request is allowed under rate limit.
        Returns (allowed, headers_dict)
        """
        now = time.time()
        window_start = now - window_seconds
        
        # Use Redis sorted set for sliding window
        pipe = self.redis.pipeline()
        
        # Remove expired entries
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Count current requests
        pipe.zcard(key)
        
        # Get TTL for retry-after header
        pipe.ttl(key)
        
        results = await pipe.execute()
        current_count = results[1]
        ttl = results[2]
        
        allowed = current_count + cost <= limit
        
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(0, limit - current_count - cost)),
            "X-RateLimit-Reset": str(int(now + (ttl if ttl > 0 else window_seconds))),
        }
        
        if allowed:
            # Add current request
            await self.redis.zadd(key, {f"{now}:{time.perf_counter_ns()}": now})
            await self.redis.expire(key, window_seconds + 1)
        else:
            headers["Retry-After"] = str(ttl if ttl > 0 else window_seconds)
        
        return allowed, headers
    
    async def reset(self, key: str) -> bool:
        """Reset rate limit for a key"""
        result = await self.redis.delete(key)
        return result > 0


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> Optional[RateLimiter]:
    return _rate_limiter


async def init_rate_limiter(redis_url: str) -> RateLimiter:
    """Initialize global rate limiter"""
    global _rate_limiter
    client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    _rate_limiter = RateLimiter(client)
    return _rate_limiter


async def close_rate_limiter():
    """Close rate limiter connection"""
    global _rate_limiter
    if _rate_limiter and _rate_limiter.redis:
        await _rate_limiter.redis.close()
    _rate_limiter = None


# ============================================================
# Rate Limit Policies
# ============================================================

class RateLimitPolicy:
    """Predefined rate limit policies for different endpoint types"""
    
    # Auth endpoints - strict limits
    AUTH_LOGIN = {"limit": 5, "window": 300}  # 5 per 5 min
    AUTH_REGISTER = {"limit": 3, "window": 3600}  # 3 per hour
    AUTH_REFRESH = {"limit": 10, "window": 300}  # 10 per 5 min
    
    # Financial operations - moderate limits
    MINT = {"limit": 20, "window": 60}  # 20 per minute
    BURN = {"limit": 20, "window": 60}
    TRANSFER = {"limit": 100, "window": 60}  # 100 per minute
    BRIDGE = {"limit": 10, "window": 60}  # 10 per minute
    
    # Read operations - generous limits
    BALANCE = {"limit": 200, "window": 60}
    ALLOWANCE = {"limit": 200, "window": 60}
    TOKEN_INFO = {"limit": 500, "window": 60}
    
    # Admin operations - strict
    ADMIN = {"limit": 50, "window": 60}
    
    # Default
    DEFAULT = {"limit": 100, "window": 60}


def get_policy_for_endpoint(path: str, method: str) -> dict:
    """Get rate limit policy for an endpoint"""
    path = path.lower()
    
    if "/auth/login" in path:
        return RateLimitPolicy.AUTH_LOGIN
    elif "/auth/register" in path:
        return RateLimitPolicy.AUTH_REGISTER
    elif "/auth/refresh" in path:
        return RateLimitPolicy.AUTH_REFRESH
    elif "/token/mint" in path:
        return RateLimitPolicy.MINT
    elif "/token/burn" in path or "/token/user-burn" in path:
        return RateLimitPolicy.BURN
    elif "/token/transfer" in path:
        return RateLimitPolicy.TRANSFER
    elif "/bridge" in path:
        return RateLimitPolicy.BRIDGE
    elif "/token/balance" in path:
        return RateLimitPolicy.BALANCE
    elif "/token/allowance" in path:
        return RateLimitPolicy.ALLOWANCE
    elif "/token/info" in path:
        return RateLimitPolicy.TOKEN_INFO
    elif "/admin" in path:
        return RateLimitPolicy.ADMIN
    elif "/multisig" in path:
        return RateLimitPolicy.ADMIN
    elif "/reserve" in path and method in ["POST", "PUT", "PATCH", "DELETE"]:
        return RateLimitPolicy.ADMIN
    
    return RateLimitPolicy.DEFAULT


# ============================================================
# Middleware Function
# ============================================================

async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware"""
    # Skip rate limiting for health checks and metrics
    if request.url.path in ["/health", "/metrics", "/docs", "/redoc", "/openapi.json"]:
        return await call_next(request)
    
    limiter = get_rate_limiter()
    if not limiter:
        return await call_next(request)
    
    # Determine client identifier
    client_ip = request.client.host if request.client else "unknown"
    user_id = getattr(request.state, "user_id", None)
    api_key = request.headers.get("X-API-Key")
    
    # Use user_id if authenticated, otherwise IP
    if user_id:
        identifier = f"user:{user_id}"
    elif api_key:
        identifier = f"apikey:{api_key[:8]}"
    else:
        identifier = f"ip:{client_ip}"
    
    # Get policy for this endpoint
    policy = get_policy_for_endpoint(request.url.path, request.method)
    
    # Create rate limit key
    key = f"ratelimit:{identifier}:{request.url.path}"
    
    # Check limit
    allowed, headers = await limiter.is_allowed(
        key=key,
        limit=policy["limit"],
        window_seconds=policy["window"],
        cost=1
    )
    
    if not allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "Rate limit exceeded",
                "detail": f"Too many requests. Limit: {policy['limit']} per {policy['window']}s",
                "retry_after": headers.get("Retry-After")
            },
            headers=headers
        )
    
    # Add rate limit headers to response
    response = await call_next(request)
    for header_key, header_value in headers.items():
        response.headers[header_key] = header_value
    
    return response


# ============================================================
# Decorator for Function-Level Rate Limiting
# ============================================================

def rate_limit(limit: int, window: int, key_func: Optional[Callable] = None):
    """Decorator for function-level rate limiting"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            limiter = get_rate_limiter()
            if not limiter:
                return await func(*args, **kwargs)
            
            # Extract request from args/kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request:
                request = kwargs.get("request")
            
            if not request:
                return await func(*args, **kwargs)
            
            # Generate key
            if key_func:
                key = key_func(request)
            else:
                client_ip = request.client.host if request.client else "unknown"
                key = f"ratelimit:func:{func.__name__}:{client_ip}"
            
            allowed, headers = await limiter.is_allowed(key, limit, window)
            
            if not allowed:
                raise RateLimitExceeded(
                    detail=f"Rate limit exceeded for {func.__name__}",
                    retry_after=int(headers.get("Retry-After", window))
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator
