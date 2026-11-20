"""
Application Configuration
Centralized settings management using Pydantic Settings
"""
import os
from typing import List, Optional
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Application
    APP_NAME: str = "IDRC API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", description="development, staging, production")
    DEBUG: bool = Field(default=True, description="Enable debug mode")
    
    # API
    API_PREFIX: str = "/api/v1"
    API_TITLE: str = "IDRC API"
    API_DESCRIPTION: str = "Production API for IDR Coin (IDRC) Stablecoin System"
    
    # Security
    JWT_SECRET_KEY: str = Field(default="", description="JWT signing secret (required in production)")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_HASH_SCHEMES: List[str] = ["bcrypt"]
    
    # CORS
    CORS_ORIGINS: List[str] = Field(default=["http://localhost:3000"], description="Allowed CORS origins")
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # Trusted Hosts
    ALLOWED_HOSTS: List[str] = Field(default=["localhost", "127.0.0.1"], description="Allowed hosts for TrustedHostMiddleware")
    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/idrc",
        description="PostgreSQL async connection string"
    )
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 3600
    
    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection string")
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_SOCKET_TIMEOUT: int = 5
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT_LIMIT: int = 100
    RATE_LIMIT_DEFAULT_WINDOW: int = 60
    
    # Idempotency
    IDEMPOTENCY_ENABLED: bool = True
    IDEMPOTENCY_DEFAULT_TTL: int = 604800  # 7 days
    
    # Correlation ID
    CORRELATION_HEADER_NAME: str = "X-Correlation-ID"
    
    # Blockchain
    BLOCKCHAIN_RPC_URLS: dict = Field(default_factory=dict, description="JSON string of chain_id -> RPC URL")
    BLOCKCHAIN_CONFIRMATIONS: dict = Field(default_factory=dict, description="Required confirmations per chain")
    BLOCKCHAIN_GAS_LIMIT_MULTIPLIER: float = 1.2
    BLOCKCHAIN_MAX_GAS_PRICE_GWEI: int = 500
    
    # Monitoring
    SENTRY_DSN: Optional[str] = None
    PROMETHEUS_METRICS_ENABLED: bool = True
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    
    # File Storage
    STATIC_DIR: str = "static"
    UPLOAD_MAX_SIZE: int = 10 * 1024 * 1024  # 10 MB
    
    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30
    WS_MAX_CONNECTIONS: int = 1000
    
    # Compliance
    KYC_PROVIDER_URL: Optional[str] = None
    KYC_PROVIDER_API_KEY: Optional[str] = None
    AML_PROVIDER_URL: Optional[str] = None
    AML_PROVIDER_API_KEY: Optional[str] = None
    
    # Oracle
    ORACLE_POLL_INTERVAL_SECONDS: int = 900  # 15 minutes
    ORACLE_STALENESS_THRESHOLD_SECONDS: int = 3600  # 1 hour
    ORACLE_MIN_CONFIRMATIONS: int = 3
    
    # Bridge
    BRIDGE_RELAYER_URL: Optional[str] = None
    BRIDGE_RELAYER_API_KEY: Optional[str] = None
    BRIDGE_FINALITY_CONFIRMATIONS: dict = Field(default_factory=dict)
    
    def get_database_url(self) -> str:
        """Get database URL with asyncpg driver"""
        return self.DATABASE_URL
    
    def get_redis_url(self) -> str:
        """Get Redis URL"""
        return self.REDIS_URL
    
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"
    
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Global settings instance
settings = get_settings()
