"""
IDRC API Authentication
JWT-based authentication with role-based access control
"""
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from functools import lru_cache

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session_dependency, User, APIKey, AuditLog
from .models import Role, AddressStr


# ============================================================
# Configuration
# ============================================================

SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ============================================================
# Token Models
# ============================================================

class TokenData(BaseModel):
    sub: str  # user address
    scopes: List[str] = []
    roles: List[str] = []
    exp: int
    iat: int
    type: str  # "access" or "refresh"


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# ============================================================
# Password Hashing
# ============================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# ============================================================
# JWT Functions
# ============================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenData(**payload)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ============================================================
# User Authentication
# ============================================================

async def authenticate_user(
    session: AsyncSession, address: str, password: str
) -> Optional[User]:
    result = await session.execute(select(User).where(User.address == address))
    user = result.scalar_one_or_none()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def get_user_by_address(session: AsyncSession, address: str) -> Optional[User]:
    result = await session.execute(select(User).where(User.address == address))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: str) -> Optional[User]:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ============================================================
# API Key Authentication
# ============================================================

async def get_api_key_hash(api_key: str) -> str:
    """Hash API key for storage"""
    return pwd_context.hash(api_key)


async def verify_api_key(api_key: str, key_hash: str) -> bool:
    return pwd_context.verify(api_key, key_hash)


async def get_user_from_api_key(
    session: AsyncSession, api_key: str
) -> Optional[User]:
    # In production, you'd hash the key and compare
    # For now, simplified lookup
    result = await session.execute(
        select(APIKey).where(APIKey.key_hash == await get_api_key_hash(api_key))
    )
    api_key_obj = result.scalar_one_or_none()
    if not api_key_obj or not api_key_obj.is_active:
        return None
    if api_key_obj.expires_at and api_key_obj.expires_at < datetime.utcnow():
        return None
    return await get_user_by_id(session, str(api_key_obj.user_id))


# ============================================================
# Dependencies
# ============================================================

async def get_current_user_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session_dependency),
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = decode_token(credentials.credentials)
    if token_data.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_user_by_address(session, token_data.sub)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_user_from_api_key(
    api_key: str = Depends(api_key_header),
    session: AsyncSession = Depends(get_session_dependency),
) -> User:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
        )

    user = await get_user_from_api_key(session, api_key)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return user


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session_dependency),
) -> User:
    """Try token auth first, then API key"""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            token_data = decode_token(token)
            if token_data.type == "access":
                user = await get_user_by_address(session, token_data.sub)
                if user and user.is_active:
                    return user
        except HTTPException:
            pass

    api_key = request.headers.get("X-API-Key")
    if api_key:
        user = await get_user_from_api_key(session, api_key)
        if user:
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ============================================================
# Role-based Access Control
# ============================================================

def require_roles(*required_roles: Role):
    """Dependency factory for role-based access control"""
    async def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        user_roles = current_user.roles or []
        if isinstance(user_roles, str):
            import json
            user_roles = json.loads(user_roles)

        # Check if user has any of the required roles
        has_role = any(role.value in user_roles for role in required_roles)
        if not has_role and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role(s): {[r.value for r in required_roles]}"
            )
        return current_user
    return role_checker


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require DEFAULT_ADMIN_ROLE or superuser"""
    return require_roles(Role.DEFAULT_ADMIN)(current_user)


def require_minter(current_user: User = Depends(get_current_user)) -> User:
    """Require MINTER_ROLE"""
    return require_roles(Role.MINTER)(current_user)


def require_burner(current_user: User = Depends(get_current_user)) -> User:
    """Require BURNER_ROLE"""
    return require_roles(Role.BURNER)(current_user)


def require_pauser(current_user: User = Depends(get_current_user)) -> User:
    """Require PAUSER_ROLE"""
    return require_roles(Role.PAUSER)(current_user)


def require_upgrader(current_user: User = Depends(get_current_user)) -> User:
    """Require UPGRADER_ROLE"""
    return require_roles(Role.UPGRADER)(current_user)


def require_blacklister(current_user: User = Depends(get_current_user)) -> User:
    """Require BLACKLISTER_ROLE"""
    return require_roles(Role.BLACKLISTER)(current_user)


def require_oracle(current_user: User = Depends(get_current_user)) -> User:
    """Require ORACLE_ROLE"""
    return require_roles(Role.ORACLE)(current_user)


def require_auditor(current_user: User = Depends(get_current_user)) -> User:
    """Require AUDITOR_ROLE"""
    return require_roles(Role.AUDITOR)(current_user)


def require_relayer(current_user: User = Depends(get_current_user)) -> User:
    """Require RELAYER_ROLE"""
    return require_roles(Role.RELAYER)(current_user)


def require_relayer_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require RELAYER_ADMIN_ROLE"""
    return require_roles(Role.RELAYER_ADMIN)(current_user)


# ============================================================
# Audit Logging
# ============================================================

async def log_audit(
    session: AsyncSession,
    user: User,
    action: str,
    resource_type: str,
    resource_id: str = None,
    details: dict = None,
    request: Request = None,
    success: bool = True,
    error_message: str = None,
) -> AuditLog:
    """Log audit event"""
    audit_log = AuditLog(
        user_id=user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=str(details) if details else None,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("User-Agent") if request else None,
        success=success,
        error_message=error_message,
    )
    session.add(audit_log)
    await session.flush()
    return audit_log


# ============================================================
# Token Pair Creation
# ============================================================

async def create_token_pair(user: User) -> Token:
    """Create access and refresh token pair"""
    user_roles = user.roles or []
    if isinstance(user_roles, str):
        import json
        user_roles = json.loads(user_roles)

    access_token = create_access_token(
        data={"sub": user.address, "roles": user_roles, "scopes": ["read", "write"]}
    )
    refresh_token = create_refresh_token(
        data={"sub": user.address, "roles": user_roles}
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


# ============================================================
# Optional Auth (for public endpoints that can benefit from auth)
# ============================================================

async def get_optional_user(
    request: Request,
    session: AsyncSession = Depends(get_session_dependency),
) -> Optional[User]:
    """Get current user if authenticated, None otherwise"""
    try:
        return await get_current_user(request, session)
    except HTTPException:
        return None