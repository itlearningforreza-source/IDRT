"""
KYC/AML Integration Service for IDRC
Implements multi-tier KYC, sanctions screening, transaction monitoring, and regulatory reporting
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

import aiohttp
import asyncpg
from pydantic import BaseModel, Field, validator

logger = logging.getLogger("idrc.kyc_aml")


# =============================================================================
# ENUMS & DATA MODELS
# =============================================================================

class KYCTier(str, Enum):
    """KYC tier levels with increasing limits"""
    TIER_0 = "tier_0"      # Email only
    TIER_1 = "tier_1"      # Basic eKYC (KTP + selfie)
    TIER_2 = "tier_2"      # Enhanced (POA, source of funds)
    TIER_3 = "tier_3"      # Institutional/Corporate


class KYCStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REQUIRES_UPDATE = "requires_update"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TransactionType(str, Enum):
    MINT = "mint"
    BURN = "burn"
    TRANSFER = "transfer"
    BRIDGE = "bridge"


class AlertType(str, Enum):
    VELOCITY = "velocity"
    GEOGRAPHY = "geography"
    COUNTERPARTY = "counterparty"
    PATTERN = "pattern"
    SANCTIONS = "sanctions"
    PEP = "pep"
    ADVERSE_MEDIA = "adverse_media"


@dataclass
class KYCLimits:
    """Daily/monthly limits per KYC tier"""
    daily_limit_idr: int
    monthly_limit_idr: int
    max_single_tx_idr: int
    requires_enhanced_due_diligence: bool = False


TIER_LIMITS = {
    KYCTier.TIER_0: KYCLimits(
        daily_limit_idr=1_000_000,      # 1M IDR
        monthly_limit_idr=10_000_000,   # 10M IDR
        max_single_tx_idr=500_000,
    ),
    KYCTier.TIER_1: KYCLimits(
        daily_limit_idr=50_000_000,     # 50M IDR
        monthly_limit_idr=500_000_000,  # 500M IDR
        max_single_tx_idr=25_000_000,
    ),
    KYCTier.TIER_2: KYCLimits(
        daily_limit_idr=500_000_000,    # 500M IDR
        monthly_limit_idr=5_000_000_000, # 5B IDR
        max_single_tx_idr=250_000_000,
        requires_enhanced_due_diligence=True,
    ),
    KYCTier.TIER_3: KYCLimits(
        daily_limit_idr=10_000_000_000,  # 10B IDR
        monthly_limit_idr=100_000_000_000, # 100B IDR
        max_single_tx_idr=5_000_000_000,
        requires_enhanced_due_diligence=True,
    ),
}


@dataclass
class UserProfile:
    user_id: str
    email: str
    kyc_tier: KYCTier
    kyc_status: KYCStatus
    risk_level: RiskLevel
    kyc_expiry: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KYCDocument:
    document_id: str
    user_id: str
    document_type: str  # ktp, passport, selfie, poa, source_of_funds
    file_hash: str
    status: KYCStatus
    extracted_data: Dict[str, Any]
    verified_at: Optional[datetime]
    verified_by: Optional[str]


@dataclass
class TransactionMonitoringRule:
    rule_id: str
    name: str
    alert_type: AlertType
    condition: str  # SQL-like or expression
    threshold: float
    window_seconds: int
    severity: str
    enabled: bool = True


@dataclass
class Alert:
    alert_id: str
    user_id: str
    alert_type: AlertType
    severity: str
    message: str
    transaction_hash: Optional[str]
    amount_idr: Optional[int]
    counterparty: Optional[str]
    created_at: datetime
    acknowledged: bool = False
    resolved: bool = False


@dataclass
class SanctionsMatch:
    list_name: str  # OFAC, UN, EU, UK, etc.
    entity_name: str
    match_score: float
    matched_fields: List[str]
    list_entry_id: str


# =============================================================================
# EXTERNAL PROVIDER INTERFACES
# =============================================================================

class EKYCProvider(ABC):
    """Abstract base for eKYC providers (e.g., Indonesian Dukcapil, private vendors)"""
    
    @abstractmethod
    async def verify_ktp(self, ktp_number: str, name: str, dob: str) -> Dict[str, Any]:
        """Verify KTP against Dukcapil/database"""
        pass
    
    @abstractmethod
    async def verify_face_match(self, selfie_base64: str, ktp_photo_base64: str) -> Dict[str, Any]:
        """Compare selfie with KTP photo"""
        pass
    
    @abstractmethod
    async def verify_liveness(self, video_base64: str) -> Dict[str, Any]:
        """Liveness detection for selfie"""
        pass


class SanctionsScreeningProvider(ABC):
    """Abstract base for sanctions/PEP/adverse media screening"""
    
    @abstractmethod
    async def screen_entity(self, name: str, dob: Optional[str] = None, 
                           nationality: Optional[str] = None, 
                           address: Optional[str] = None) -> List[SanctionsMatch]:
        """Screen against OFAC, UN, EU, UK, PEP, adverse media lists"""
        pass
    
    @abstractmethod
    async def screen_transaction(self, sender: str, receiver: str, 
                                amount: int, currency: str) -> List[SanctionsMatch]:
        """Screen transaction counterparties"""
        pass


class BankAPIProvider(ABC):
    """Abstract base for bank custodian API (BI-FAST, ISO 20022)"""
    
    @abstractmethod
    async def get_account_balance(self, account_id: str) -> int:
        """Get current fiat balance in IDR (smallest unit)"""
        pass
    
    @abstractmethod
    async def initiate_transfer(self, from_account: str, to_account: str, 
                               amount: int, reference: str) -> Dict[str, Any]:
        """Initiate fiat transfer via BI-FAST"""
        pass
    
    @abstractmethod
    async def get_transaction_status(self, reference: str) -> Dict[str, Any]:
        """Check transfer status"""
        pass


# =============================================================================
# MOCK PROVIDERS FOR DEVELOPMENT
# =============================================================================

class MockEKYCProvider(EKYCProvider):
    """Mock eKYC provider for development/testing"""
    
    async def verify_ktp(self, ktp_number: str, name: str, dob: str) -> Dict[str, Any]:
        # Simulate API call
        await asyncio.sleep(0.1)
        # Mock: valid if KTP format correct (16 digits)
        is_valid = len(ktp_number) == 16 and ktp_number.isdigit()
        return {
            "valid": is_valid,
            "ktp_number": ktp_number,
            "name_match": is_valid,
            "dob_match": is_valid,
            "address": "Jl. Sudirman No. 1, Jakarta" if is_valid else None,
            "provider": "mock_dukcapil",
            "verified_at": datetime.utcnow().isoformat(),
        }
    
    async def verify_face_match(self, selfie_base64: str, ktp_photo_base64: str) -> Dict[str, Any]:
        await asyncio.sleep(0.1)
        return {
            "match": True,
            "confidence": 0.98,
            "provider": "mock_face_verify",
            "verified_at": datetime.utcnow().isoformat(),
        }
    
    async def verify_liveness(self, video_base64: str) -> Dict[str, Any]:
        await asyncio.sleep(0.1)
        return {
            "live": True,
            "confidence": 0.95,
            "provider": "mock_liveness",
            "verified_at": datetime.utcnow().isoformat(),
        }


class MockSanctionsProvider(SanctionsScreeningProvider):
    """Mock sanctions screening provider"""
    
    # Mock sanctioned entities for testing
    SANCTIONED_ENTITIES = {
        "john doe": ["OFAC", "UN"],
        "blocked entity": ["EU", "UK"],
        "sanctioned corp": ["OFAC"],
    }
    
    PEP_ENTITIES = {
        "politically exposed": ["PEP_DOMESTIC"],
        "foreign official": ["PEP_FOREIGN"],
    }
    
    async def screen_entity(self, name: str, dob: Optional[str] = None,
                           nationality: Optional[str] = None,
                           address: Optional[str] = None) -> List[SanctionsMatch]:
        await asyncio.sleep(0.05)
        matches = []
        name_lower = name.lower()
        
        for entity, lists in self.SANCTIONED_ENTITIES.items():
            if entity in name_lower:
                for list_name in lists:
                    matches.append(SanctionsMatch(
                        list_name=list_name,
                        entity_name=entity,
                        match_score=0.95,
                        matched_fields=["name"],
                        list_entry_id=f"{list_name}_{entity}",
                    ))
        
        for entity, lists in self.PEP_ENTITIES.items():
            if entity in name_lower:
                for list_name in lists:
                    matches.append(SanctionsMatch(
                        list_name=list_name,
                        entity_name=entity,
                        match_score=0.90,
                        matched_fields=["name"],
                        list_entry_id=f"{list_name}_{entity}",
                    ))
        
        return matches
    
    async def screen_transaction(self, sender: str, receiver: str,
                                amount: int, currency: str) -> List[SanctionsMatch]:
        # Screen both sender and receiver
        sender_matches = await self.screen_entity(sender)
        receiver_matches = await self.screen_entity(receiver)
        return sender_matches + receiver_matches


class MockBankProvider(BankAPIProvider):
    """Mock bank provider for development"""
    
    def __init__(self):
        self.balances = {"IDRC_RESERVE_001": 10_000_000_000_000_000_000}  # 10B IDR in smallest unit
        self.transactions = {}
    
    async def get_account_balance(self, account_id: str) -> int:
        await asyncio.sleep(0.05)
        return self.balances.get(account_id, 0)
    
    async def initiate_transfer(self, from_account: str, to_account: str,
                               amount: int, reference: str) -> Dict[str, Any]:
        await asyncio.sleep(0.1)
        tx_id = f"BI-FAST-{uuid4().hex[:12]}"
        self.transactions[tx_id] = {
            "from": from_account,
            "to": to_account,
            "amount": amount,
            "reference": reference,
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat(),
        }
        return {
            "transaction_id": tx_id,
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    async def get_transaction_status(self, reference: str) -> Dict[str, Any]:
        await asyncio.sleep(0.05)
        return self.transactions.get(reference, {"status": "not_found"})


# =============================================================================
# KYC/AML SERVICE
# =============================================================================

class KYCAMLService:
    """Main KYC/AML orchestration service"""
    
    def __init__(self, 
                 db_pool: asyncpg.Pool,
                 ekyc_provider: EKYCProvider,
                 sanctions_provider: SanctionsScreeningProvider,
                 bank_provider: BankAPIProvider,
                 config: Dict[str, Any]):
        self.db = db_pool
        self.ekyc = ekyc_provider
        self.sanctions = sanctions_provider
        self.bank = bank_provider
        self.config = config
        self.monitoring_rules: List[TransactionMonitoringRule] = []
        self._load_monitoring_rules()
    
    def _load_monitoring_rules(self):
        """Load transaction monitoring rules from config/database"""
        # Default rules
        self.monitoring_rules = [
            TransactionMonitoringRule(
                rule_id="velocity_1",
                name="High Velocity - More than 10 tx/hour",
                alert_type=AlertType.VELOCITY,
                condition="count(tx) > 10",
                threshold=10,
                window_seconds=3600,
                severity="high",
            ),
            TransactionMonitoringRule(
                rule_id="velocity_2",
                name="High Volume - More than 1B IDR/hour",
                alert_type=AlertType.VELOCITY,
                condition="sum(amount) > 1000000000",
                threshold=1_000_000_000,
                window_seconds=3600,
                severity="high",
            ),
            TransactionMonitoringRule(
                rule_id="geography_1",
                name="High Risk Jurisdiction",
                alert_type=AlertType.GEOGRAPHY,
                condition="counterparty_country in HIGH_RISK_COUNTRIES",
                threshold=1,
                window_seconds=86400,
                severity="high",
            ),
            TransactionMonitoringRule(
                rule_id="counterparty_1",
                name="Sanctioned Counterparty",
                alert_type=AlertType.COUNTERPARTY,
                condition="sanctions_match == true",
                threshold=1,
                window_seconds=0,
                severity="critical",
            ),
            TransactionMonitoringRule(
                rule_id="pattern_1",
                name="Structuring - Multiple tx just below threshold",
                alert_type=AlertType.PATTERN,
                condition="count(tx where amount > threshold * 0.9 and amount < threshold) > 3",
                threshold=0.9,
                window_seconds=86400,
                severity="high",
            ),
        ]
    
    # =========================================================================
    # USER KYC MANAGEMENT
    # =========================================================================
    
    async def create_user(self, email: str) -> UserProfile:
        """Create new user with Tier 0 KYC"""
        user_id = f"usr_{uuid4().hex[:16]}"
        now = datetime.utcnow()
        
        async with self.db.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, email, kyc_tier, kyc_status, risk_level, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, user_id, email, KYCTier.TIER_0.value, KYCStatus.PENDING.value, 
                RiskLevel.LOW.value, now, now)
        
        return UserProfile(
            user_id=user_id,
            email=email,
            kyc_tier=KYCTier.TIER_0,
            kyc_status=KYCStatus.PENDING,
            risk_level=RiskLevel.LOW,
            kyc_expiry=None,
            created_at=now,
            updated_at=now,
        )
    
    async def submit_kyc_tier1(self, user_id: str, ktp_number: str, name: str, 
                               dob: str, selfie_base64: str, ktp_photo_base64: str) -> Dict[str, Any]:
        """Submit Tier 1 KYC (KTP + selfie)"""
        # Verify KTP
        ktp_result = await self.ekyc.verify_ktp(ktp_number, name, dob)
        if not ktp_result.get("valid"):
            return {"success": False, "reason": "Invalid KTP", "details": ktp_result}
        
        # Verify face match
        face_result = await self.ekyc.verify_face_match(selfie_base64, ktp_photo_base64)
        if not face_result.get("match") or face_result.get("confidence", 0) < 0.8:
            return {"success": False, "reason": "Face match failed", "details": face_result}
        
        # Verify liveness
        liveness_result = await self.ekyc.verify_liveness(selfie_base64)
        if not liveness_result.get("live"):
            return {"success": False, "reason": "Liveness check failed", "details": liveness_result}
        
        # Screen for sanctions/PEP
        sanctions_matches = await self.sanctions.screen_entity(name)
        if sanctions_matches:
            risk_level = RiskLevel.CRITICAL
            kyc_status = KYCStatus.REJECTED
        else:
            risk_level = RiskLevel.LOW
            kyc_status = KYCStatus.APPROVED
        
        # Update user
        kyc_expiry = datetime.utcnow() + timedelta(days=365)  # 1 year
        async with self.db.acquire() as conn:
            await conn.execute("""
                UPDATE users SET kyc_tier = $1, kyc_status = $2, risk_level = $3, 
                               kyc_expiry = $4, updated_at = $5
                WHERE user_id = $6
            """, KYCTier.TIER_1.value, kyc_status.value, risk_level.value, 
                kyc_expiry, datetime.utcnow(), user_id)
            
            # Store documents
            for doc_type, doc_data in [
                ("ktp", {"ktp_number": ktp_number, "name": name, "dob": dob}),
                ("selfie", {"base64": selfie_base64}),
                ("ktp_photo", {"base64": ktp_photo_base64}),
            ]:
                doc_hash = hashlib.sha256(json.dumps(doc_data, sort_keys=True).encode()).hexdigest()
                await conn.execute("""
                    INSERT INTO kyc_documents (document_id, user_id, document_type, file_hash, status, extracted_data, verified_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, f"doc_{uuid4().hex[:16]}", user_id, doc_type, doc_hash, 
                    KYCStatus.APPROVED.value, json.dumps(doc_data), datetime.utcnow())
        
        return {
            "success": True,
            "kyc_tier": KYCTier.TIER_1.value,
            "kyc_status": kyc_status.value,
            "risk_level": risk_level.value,
            "kyc_expiry": kyc_expiry.isoformat(),
            "limits": TIER_LIMITS[KYCTier.TIER_1].__dict__,
        }
    
    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get user KYC profile"""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            if not row:
                return None
            return UserProfile(
                user_id=row["user_id"],
                email=row["email"],
                kyc_tier=KYCTier(row["kyc_tier"]),
                kyc_status=KYCStatus(row["kyc_status"]),
                risk_level=RiskLevel(row["risk_level"]),
                kyc_expiry=row["kyc_expiry"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                metadata=row["metadata"] or {},
            )
    
    async def check_transaction_limits(self, user_id: str, amount_idr: int) -> Dict[str, Any]:
        """Check if transaction exceeds user's KYC tier limits"""
        profile = await self.get_user_profile(user_id)
        if not profile:
            return {"allowed": False, "reason": "User not found"}
        
        limits = TIER_LIMITS[profile.kyc_tier]
        
        # Check single transaction limit
        if amount_idr > limits.max_single_tx_idr:
            return {
                "allowed": False, 
                "reason": f"Amount exceeds single transaction limit for {profile.kyc_tier.value}",
                "limit": limits.max_single_tx_idr,
            }
        
        # Check daily limit (would query transaction history)
        # Simplified for now
        daily_used = await self._get_daily_volume(user_id)
        if daily_used + amount_idr > limits.daily_limit_idr:
            return {
                "allowed": False,
                "reason": f"Daily limit exceeded for {profile.kyc_tier.value}",
                "limit": limits.daily_limit_idr,
                "used": daily_used,
            }
        
        # Check monthly limit
        monthly_used = await self._get_monthly_volume(user_id)
        if monthly_used + amount_idr > limits.monthly_limit_idr:
            return {
                "allowed": False,
                "reason": f"Monthly limit exceeded for {profile.kyc_tier.value}",
                "limit": limits.monthly_limit_idr,
                "used": monthly_used,
            }
        
        return {"allowed": True, "limits": limits.__dict__}
    
    async def _get_daily_volume(self, user_id: str) -> int:
        """Get user's transaction volume in last 24 hours"""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT COALESCE(SUM(amount_idr), 0) as volume
                FROM transactions
                WHERE user_id = $1 AND created_at > NOW() - INTERVAL '24 hours'
            """, user_id)
            return row["volume"] if row else 0
    
    async def _get_monthly_volume(self, user_id: str) -> int:
        async with self.db.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT COALESCE(SUM(amount_idr), 0) as volume
                FROM transactions
                WHERE user_id = $1 AND created_at > NOW() - INTERVAL '30 days'
            """, user_id)
            return row["volume"] if row else 0
    
    # =========================================================================
    # TRANSACTION MONITORING
    # =========================================================================
    
    async def monitor_transaction(self, 
                                  user_id: str,
                                  tx_hash: str,
                                  tx_type: TransactionType,
                                  amount_idr: int,
                                  counterparty: Optional[str] = None,
                                  counterparty_address: Optional[str] = None) -> List[Alert]:
        """Monitor transaction for suspicious activity"""
        alerts = []
        
        # Get user profile
        profile = await self.get_user_profile(user_id)
        if not profile:
            return alerts
        
        # Check limits
        limit_check = await self.check_transaction_limits(user_id, amount_idr)
        if not limit_check["allowed"]:
            alerts.append(Alert(
                alert_id=f"alert_{uuid4().hex[:16]}",
                user_id=user_id,
                alert_type=AlertType.VELOCITY,
                severity="high",
                message=f"Transaction exceeds limits: {limit_check['reason']}",
                transaction_hash=tx_hash,
                amount_idr=amount_idr,
                counterparty=counterparty,
                created_at=datetime.utcnow(),
            ))
        
        # Screen counterparty for sanctions
        if counterparty:
            sanctions_matches = await self.sanctions.screen_entity(counterparty)
            if sanctions_matches:
                for match in sanctions_matches:
                    alerts.append(Alert(
                        alert_id=f"alert_{uuid4().hex[:16]}",
                        user_id=user_id,
                        alert_type=AlertType.SANCTIONS,
                        severity="critical",
                        message=f"Counterparty matches sanctions list: {match.list_name} - {match.entity_name}",
                        transaction_hash=tx_hash,
                        amount_idr=amount_idr,
                        counterparty=counterparty,
                        created_at=datetime.utcnow(),
                    ))
        
        # Screen transaction
        if counterparty_address:
            tx_matches = await self.sanctions.screen_transaction(
                user_id, counterparty_address, amount_idr, "IDR"
            )
            if tx_matches:
                for match in tx_matches:
                    alerts.append(Alert(
                        alert_id=f"alert_{uuid4().hex[:16]}",
                        user_id=user_id,
                        alert_type=AlertType.SANCTIONS,
                        severity="critical",
                        message=f"Transaction counterparty sanctioned: {match.entity_name}",
                        transaction_hash=tx_hash,
                        amount_idr=amount_idr,
                        counterparty=counterparty_address,
                        created_at=datetime.utcnow(),
                    ))
        
        # Run velocity rules
        velocity_alerts = await self._check_velocity_rules(user_id, amount_idr, tx_hash, counterparty)
        alerts.extend(velocity_alerts)
        
        # Store alerts
        for alert in alerts:
            await self._store_alert(alert)
        
        return alerts
    
    async def _check_velocity_rules(self, user_id: str, amount_idr: int, 
                                   tx_hash: str, counterparty: Optional[str]) -> List[Alert]:
        """Check velocity-based rules"""
        alerts = []
        async with self.db.acquire() as conn:
            # Last hour transaction count
            tx_count = await conn.fetchval("""
                SELECT COUNT(*) FROM transactions
                WHERE user_id = $1 AND created_at > NOW() - INTERVAL '1 hour'
            """, user_id)
            
            if tx_count >= 10:
                alerts.append(Alert(
                    alert_id=f"alert_{uuid4().hex[:16]}",
                    user_id=user_id,
                    alert_type=AlertType.VELOCITY,
                    severity="high",
                    message=f"High transaction velocity: {tx_count} transactions in last hour",
                    transaction_hash=tx_hash,
                    amount_idr=amount_idr,
                    counterparty=counterparty,
                    created_at=datetime.utcnow(),
                ))
            
            # Last hour volume
            volume = await conn.fetchval("""
                SELECT COALESCE(SUM(amount_idr), 0) FROM transactions
                WHERE user_id = $1 AND created_at > NOW() - INTERVAL '1 hour'
            """, user_id)
            
            if volume > 1_000_000_000:  # 1B IDR
                alerts.append(Alert(
                    alert_id=f"alert_{uuid4().hex[:16]}",
                    user_id=user_id,
                    alert_type=AlertType.VELOCITY,
                    severity="high",
                    message=f"High volume in last hour: {volume:,} IDR",
                    transaction_hash=tx_hash,
                    amount_idr=amount_idr,
                    counterparty=counterparty,
                    created_at=datetime.utcnow(),
                ))
        
        return alerts
    
    async def _store_alert(self, alert: Alert):
        async with self.db.acquire() as conn:
            await conn.execute("""
                INSERT INTO alerts (alert_id, user_id, alert_type, severity, message, 
                                   transaction_hash, amount_idr, counterparty, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, alert.alert_id, alert.user_id, alert.alert_type.value, alert.severity,
                alert.message, alert.transaction_hash, alert.amount_idr, 
                alert.counterparty, alert.created_at)
    
    # =========================================================================
    # SANCTIONS LIST MANAGEMENT
    # =========================================================================
    
    async def update_sanctions_lists(self) -> Dict[str, int]:
        """Update local sanctions lists from provider"""
        # In production, this would download and parse official lists
        # For now, return mock counts
        return {
            "ofac": 15000,
            "un": 8000,
            "eu": 5000,
            "uk": 3000,
            "pep_domestic": 2000,
            "pep_foreign": 5000,
            "adverse_media": 10000,
        }
    
    async def screen_bulk_addresses(self, addresses: List[str]) -> Dict[str, List[SanctionsMatch]]:
        """Screen multiple addresses for sanctions"""
        results = {}
        for addr in addresses:
            matches = await self.sanctions.screen_entity(addr)
            if matches:
                results[addr] = matches
        return results
    
    # =========================================================================
    # REGULATORY REPORTING
    # =========================================================================
    
    async def generate_sar(self, alert_ids: List[str]) -> Dict[str, Any]:
        """Generate Suspicious Activity Report for PPATK"""
        async with self.db.acquire() as conn:
            alerts = await conn.fetch("""
                SELECT * FROM alerts WHERE alert_id = ANY($1)
            """, alert_ids)
            
            if not alerts:
                return {"success": False, "reason": "No alerts found"}
            
            # Aggregate by user
            users = {}
            for alert in alerts:
                uid = alert["user_id"]
                if uid not in users:
                    user = await self.get_user_profile(uid)
                    users[uid] = user
            
            sar = {
                "sar_id": f"SAR-{uuid4().hex[:16]}",
                "generated_at": datetime.utcnow().isoformat(),
                "reporting_entity": "IDRC Stablecoin",
                "alert_count": len(alerts),
                "users_involved": len(users),
                "total_amount_idr": sum(a["amount_idr"] or 0 for a in alerts),
                "alert_types": list(set(a["alert_type"] for a in alerts)),
                "severity": max(a["severity"] for a in alerts),
                "details": [
                    {
                        "alert_id": a["alert_id"],
                        "user_id": a["user_id"],
                        "alert_type": a["alert_type"],
                        "severity": a["severity"],
                        "message": a["message"],
                        "amount_idr": a["amount_idr"],
                        "counterparty": a["counterparty"],
                        "created_at": a["created_at"].isoformat() if a["created_at"] else None,
                    }
                    for a in alerts
                ],
                "user_profiles": {
                    uid: {
                        "email": u.email,
                        "kyc_tier": u.kyc_tier.value,
                        "risk_level": u.risk_level.value,
                    }
                    for uid, u in users.items()
                },
            }
            
            # Store SAR
            await conn.execute("""
                INSERT INTO sar_reports (sar_id, alert_ids, report_data, generated_at, status)
                VALUES ($1, $2, $3, $4, $5)
            """, sar["sar_id"], alert_ids, json.dumps(sar), datetime.utcnow(), "generated")
            
            return {"success": True, "sar": sar}
    
    async def get_compliance_dashboard(self) -> Dict[str, Any]:
        """Get compliance metrics for dashboard"""
        async with self.db.acquire() as conn:
            # User counts by tier
            tier_counts = await conn.fetch("""
                SELECT kyc_tier, COUNT(*) as count
                FROM users
                GROUP BY kyc_tier
            """)
            
            # Alert counts by severity
            alert_counts = await conn.fetch("""
                SELECT severity, COUNT(*) as count
                FROM alerts
                WHERE created_at > NOW() - INTERVAL '24 hours'
                GROUP BY severity
            """)
            
            # SAR reports
            sar_count = await conn.fetchval("""
                SELECT COUNT(*) FROM sar_reports
                WHERE generated_at > NOW() - INTERVAL '30 days'
            """)
            
            # Transaction volume
            volume_24h = await conn.fetchval("""
                SELECT COALESCE(SUM(amount_idr), 0) FROM transactions
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            
            return {
                "user_tiers": {row["kyc_tier"]: row["count"] for row in tier_counts},
                "alerts_24h": {row["severity"]: row["count"] for row in alert_counts},
                "sar_reports_30d": sar_count,
                "volume_24h_idr": volume_24h,
                "generated_at": datetime.utcnow().isoformat(),
            }


# =============================================================================
# FACTORY & CONFIGURATION
# =============================================================================

def create_kyc_aml_service(config: Dict[str, Any], db_pool: asyncpg.Pool) -> KYCAMLService:
    """Factory to create KYC/AML service with configured providers"""
    
    env = config.get("ENVIRONMENT", "development")
    
    if env == "production":
        # TODO: Initialize real providers
        # ekyc = RealEKYCProvider(config["ekyc"])
        # sanctions = RealSanctionsProvider(config["sanctions"])
        # bank = RealBankProvider(config["bank"])
        raise NotImplementedError("Production providers not yet implemented")
    else:
        # Development mock providers
        ekyc = MockEKYCProvider()
        sanctions = MockSanctionsProvider()
        bank = MockBankProvider()
    
    return KYCAMLService(db_pool, ekyc, sanctions, bank, config)


# =============================================================================
# DATABASE SCHEMA (for reference)
# =============================================================================

DATABASE_SCHEMA = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(64) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    kyc_tier VARCHAR(20) NOT NULL DEFAULT 'tier_0',
    kyc_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    risk_level VARCHAR(20) NOT NULL DEFAULT 'low',
    kyc_expiry TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- KYC Documents
CREATE TABLE IF NOT EXISTS kyc_documents (
    document_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id),
    document_type VARCHAR(50) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    extracted_data JSONB,
    verified_at TIMESTAMP WITH TIME ZONE,
    verified_by VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Transactions
CREATE TABLE IF NOT EXISTS transactions (
    tx_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id),
    tx_hash VARCHAR(66),
    tx_type VARCHAR(20) NOT NULL,
    amount_idr BIGINT NOT NULL,
    counterparty VARCHAR(255),
    counterparty_address VARCHAR(255),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Alerts
CREATE TABLE IF NOT EXISTS alerts (
    alert_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id),
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    transaction_hash VARCHAR(66),
    amount_idr BIGINT,
    counterparty VARCHAR(255),
    acknowledged BOOLEAN DEFAULT FALSE,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- SAR Reports
CREATE TABLE IF NOT EXISTS sar_reports (
    sar_id VARCHAR(64) PRIMARY KEY,
    alert_ids TEXT[] NOT NULL,
    report_data JSONB NOT NULL,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'generated',
    submitted_at TIMESTAMP WITH TIME ZONE,
    submitted_by VARCHAR(64)
);

-- Monitoring Rules
CREATE TABLE IF NOT EXISTS monitoring_rules (
    rule_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    condition TEXT NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    window_seconds INTEGER NOT NULL,
    severity VARCHAR(20) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_kyc_tier ON users(kyc_tier);
CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_sar_reports_generated ON sar_reports(generated_at);
"""

if __name__ == "__main__":
    print("KYC/AML Service module loaded")
    print("Database schema:")
    print(DATABASE_SCHEMA)
