"""
Monitor Service - Alert engine and dashboard
"""
from typing import List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from web3 import Web3
from web3.contract import Contract

from ..models import AlertLevel, AddressStr, IDRCAmount


@dataclass
class AlertEvent:
    level: AlertLevel
    code: str
    message: str
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class MonitorService:
    def __init__(self, token_contract: Contract, reserve_contract: Contract, chain_id: int):
        self.token = token_contract
        self.reserve = reserve_contract
        self.chain_id = chain_id
        self.w3 = token_contract.w3

        # Alert thresholds
        self.LARGE_MINT_THRESHOLD = 100_000_000 * 10**18  # 100M IDRC
        self.SUPPLY_CAP = 10_000_000_000 * 10**18  # 10B IDRC
        self.RESERVE_LAG_SECONDS = 86_400  # 24 hours

    async def run_alert_checks(self) -> List[AlertEvent]:
        """Run all alert checks"""
        alerts = []

        # 1. Check for large mints (would need event indexing in production)
        # This is a simplified check
        alerts.extend(await self._check_large_mints())

        # 2. Supply cap breach
        alerts.extend(await self._check_supply_cap())

        # 3. Reserve oracle staleness
        alerts.extend(await self._check_oracle_staleness())

        # 4. Under-collateralisation
        alerts.extend(await self._check_collateralisation())

        # 5. Blacklist events
        alerts.extend(await self._check_blacklist_events())

        return alerts

    async def _check_large_mints(self) -> List[AlertEvent]:
        """Check for large mint events"""
        # In production, query indexed events
        return []

    async def _check_supply_cap(self) -> List[AlertEvent]:
        """Check if total supply exceeds cap"""
        alerts = []
        supply = self.token.functions.totalSupply().call()
        cap = self.token.functions.supplyCap().call()
        if supply > cap:
            alerts.append(AlertEvent(
                level=AlertLevel.CRITICAL,
                code="SUPPLY_CAP_BREACH",
                message=f"Total supply {IDRCAmount(supply / 10**18):,.0f} IDRC exceeds cap {IDRCAmount(cap / 10**18):,.0f} IDRC"
            ))
        return alerts

    async def _check_oracle_staleness(self) -> List[AlertEvent]:
        """Check if oracle hasn't updated recently"""
        alerts = []
        last_update = self.reserve.functions.lastOracleUpdate().call()
        if last_update == 0:
            alerts.append(AlertEvent(
                level=AlertLevel.WARNING,
                code="ORACLE_NEVER_UPDATED",
                message="Reserve oracle has never pushed a fiat balance update."
            ))
        else:
            age = datetime.utcnow().timestamp() - last_update
            if age > self.RESERVE_LAG_SECONDS:
                alerts.append(AlertEvent(
                    level=AlertLevel.WARNING,
                    code="ORACLE_STALE",
                    message=f"Reserve oracle last updated {age / 3600:.1f}h ago (threshold: {self.RESERVE_LAG_SECONDS / 3600:.0f}h)"
                ))
        return alerts

    async def _check_collateralisation(self) -> List[AlertEvent]:
        """Check collateralisation ratio"""
        alerts = []
        supply = self.token.functions.totalSupply().call()
        if supply > 0:
            fiat = self.reserve.functions.fiatBalanceIdr().call()
            ratio = (fiat * 10**18) / supply
            if ratio < 10**18:
                alerts.append(AlertEvent(
                    level=AlertLevel.CRITICAL,
                    code="UNDER_COLLATERALISED",
                    message=f"Reserve ratio = {ratio / 10**18:.4f} — below required 1.0 "
                            f"(fiat={IDRCAmount(fiat / 10**18):,.0f} IDR, "
                            f"supply={IDRCAmount(supply / 10**18):,.0f} IDRC)"
                ))
        return alerts

    async def _check_blacklist_events(self) -> List[AlertEvent]:
        """Check for blacklist events"""
        # In production, query indexed events
        return []

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for dashboard"""
        supply = self.token.functions.totalSupply().call()
        fiat = self.reserve.functions.fiatBalanceIdr().call()
        ratio = (fiat * 10**18) / supply if supply > 0 else float('inf')

        alerts = await self.run_alert_checks()

        return {
            "token": {
                "name": self.token.functions.name().call(),
                "symbol": self.token.functions.symbol().call(),
                "total_supply": IDRCAmount(supply / 10**18),
                "total_minted": IDRCAmount(0),  # Would need indexing
                "total_burned": IDRCAmount(0),  # Would need indexing
                "holder_count": 0,  # Would need indexing
                "paused": self.token.functions.paused().call()
            },
            "reserve": {
                "fiat_balance_idr": IDRCAmount(fiat / 10**18),
                "reserve_ratio": ratio / 10**18 if ratio != float('inf') else float('inf'),
                "is_fully_collateralised": ratio >= 10**18,
                "audit_reports": self.reserve.functions.auditReportCount().call()
            },
            "alerts": [
                {"level": a.level.value, "code": a.code, "message": a.message, "timestamp": a.timestamp.isoformat()}
                for a in alerts
            ],
            "top_holders": []  # Would need indexing
        }