"""
idrc/monitor.py
===============
On-chain event monitoring and indexing (Section 9.1).

Mirrors the Tenderly / The Graph / Dune Analytics layer described in the
design document. In a production system this would be a service querying
Ethereum logs via Etherscan API, Alchemy, or a subgraph. Here we provide
an in-process Python simulation that:

  - Indexes all token events into a queryable structure.
  - Computes aggregate statistics (holders, supply history, transfers).
  - Issues alerts when suspicious conditions are detected.
  - Exports a Dune-style summary for dashboards.

Usage
-----
    monitor = IDRCMonitor(token, reserve)
    monitor.sync()                          # pull latest events
    monitor.print_dashboard()               # human-readable stats
    alerts = monitor.run_alert_checks()     # returns list of AlertEvent
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .erc20 import ZERO_ADDRESS, TransferEvent
from .token import BlacklistedEvent, BurnEvent, MintEvent

if TYPE_CHECKING:
    from .reserve import IDRCReserve

# ─── Alert Definitions ────────────────────────────────────────────────────────

@dataclass
class AlertEvent:
    level: str          # "INFO" | "WARNING" | "CRITICAL"
    code: str           # machine-readable alert code
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return f"[{self.level}] {self.code}: {self.message}"


# ─── Transfer Summary ─────────────────────────────────────────────────────────

@dataclass
class TransferSummary:
    total_transfers: int
    total_volume: int       # raw units
    unique_senders: int
    unique_recipients: int
    largest_transfer: int


# ─── IDRCMonitor ──────────────────────────────────────────────────────────────

class IDRCMonitor:
    """
    Event indexer and alert engine for the IDRC stablecoin.

    Parameters
    ----------
    token   : IDRCToken instance (or a _TokenHandle from proxy)
    reserve : IDRCReserve instance (optional)

    Alert Thresholds
    ----------------
    large_mint_threshold   : Mint ≥ this value triggers a WARNING.
    supply_cap             : Total supply above this triggers CRITICAL.
    reserve_lag_seconds    : Oracle stale if last update older than this.
    """

    LARGE_MINT_THRESHOLD = 100_000_000 * 10**18      # 100 M IDRC
    SUPPLY_CAP           = 10_000_000_000 * 10**18   # 10 B IDRC
    RESERVE_LAG_SECONDS  = 86_400                     # 24 hours

    def __init__(
        self,
        token,
        reserve: IDRCReserve | None = None,
    ) -> None:
        self._token   = token
        self._reserve = reserve

        # Indexed data
        self._mint_events:      list[MintEvent]      = []
        self._burn_events:      list[BurnEvent]       = []
        self._transfer_events:  list[TransferEvent]   = []
        self._blacklist_events: list[BlacklistedEvent] = []
        self._alerts:           list[AlertEvent]      = []

        # Supply history: list of (timestamp, total_supply)
        self._supply_history: list[tuple] = []

        self._last_synced: datetime | None = None

    # ── Sync ─────────────────────────────────────────────────────────────────

    def sync(self) -> None:
        """
        Pull all events from the token and classify them.
        In production: query eth_getLogs from the last indexed block.
        """
        self._mint_events.clear()
        self._burn_events.clear()
        self._transfer_events.clear()
        self._blacklist_events.clear()

        for event in self._token.events:
            if isinstance(event, MintEvent):
                self._mint_events.append(event)
            elif isinstance(event, BurnEvent):
                self._burn_events.append(event)
            elif isinstance(event, TransferEvent):
                # Exclude internal mint/burn Transfer events
                if event.sender != ZERO_ADDRESS and event.recipient != ZERO_ADDRESS:
                    self._transfer_events.append(event)
            elif isinstance(event, BlacklistedEvent):
                self._blacklist_events.append(event)

        self._supply_history.append(
            (datetime.now(timezone.utc), self._token.total_supply)
        )
        self._last_synced = datetime.now(timezone.utc)

    # ── Statistics ────────────────────────────────────────────────────────────

    def total_minted(self) -> int:
        """Cumulative tokens ever minted."""
        return sum(e.amount for e in self._mint_events)

    def total_burned(self) -> int:
        """Cumulative tokens ever burned."""
        return sum(e.amount for e in self._burn_events)

    def current_supply(self) -> int:
        """Live total supply from the token contract."""
        return self._token.total_supply

    def holder_count(self) -> int:
        """Number of addresses with a non-zero balance."""
        return len(self._token.all_holders())

    def transfer_summary(self) -> TransferSummary:
        """Aggregate stats for peer-to-peer transfers."""
        transfers = self._transfer_events
        if not transfers:
            return TransferSummary(0, 0, 0, 0, 0)

        volume  = sum(t.amount for t in transfers)
        senders = {t.sender for t in transfers}
        recips  = {t.recipient for t in transfers}
        largest = max(t.amount for t in transfers)

        return TransferSummary(
            total_transfers=len(transfers),
            total_volume=volume,
            unique_senders=len(senders),
            unique_recipients=len(recips),
            largest_transfer=largest,
        )

    def top_holders(self, n: int = 10) -> list[tuple]:
        """Return top-N holders sorted by balance descending."""
        holders = self._token.all_holders()
        return sorted(holders.items(), key=lambda x: x[1], reverse=True)[:n]

    # ── Alert Engine ──────────────────────────────────────────────────────────

    def run_alert_checks(self) -> list[AlertEvent]:
        """
        Execute all alert rules. Returns a list of triggered AlertEvents.
        Mirrors Tenderly Alerts / custom Dune Analytics anomaly detection.
        """
        alerts: list[AlertEvent] = []

        # 1. Large single mint
        for ev in self._mint_events:
            if ev.amount >= self.LARGE_MINT_THRESHOLD:
                alerts.append(AlertEvent(
                    level="WARNING",
                    code="LARGE_MINT",
                    message=(
                        f"Large mint detected: {ev.amount / 10**18:,.0f} IDRC "
                        f"to {ev.to} at {ev.timestamp.isoformat()}"
                    ),
                ))

        # 2. Supply cap breach
        supply = self.current_supply()
        if supply > self.SUPPLY_CAP:
            alerts.append(AlertEvent(
                level="CRITICAL",
                code="SUPPLY_CAP_BREACH",
                message=(
                    f"Total supply {supply / 10**18:,.0f} IDRC exceeds cap "
                    f"{self.SUPPLY_CAP / 10**18:,.0f} IDRC"
                ),
            ))

        # 3. Reserve oracle staleness
        if self._reserve is not None:
            last_update = self._reserve.last_oracle_update
            if last_update is None:
                alerts.append(AlertEvent(
                    level="WARNING",
                    code="ORACLE_NEVER_UPDATED",
                    message="Reserve oracle has never pushed a fiat balance update.",
                ))
            else:
                now = datetime.now(timezone.utc)
                age_seconds = (now - last_update).total_seconds()
                if age_seconds > self.RESERVE_LAG_SECONDS:
                    alerts.append(AlertEvent(
                        level="WARNING",
                        code="ORACLE_STALE",
                        message=(
                            f"Reserve oracle last updated {age_seconds / 3600:.1f}h ago "
                            f"(threshold: {self.RESERVE_LAG_SECONDS / 3600:.0f}h)"
                        ),
                    ))

        # 4. Under-collateralisation
        if self._reserve is not None and supply > 0 and not self._reserve.is_fully_collateralised(supply):
            ratio = self._reserve.reserve_ratio(supply)
            alerts.append(AlertEvent(
                    level="CRITICAL",
                    code="UNDER_COLLATERALISED",
                    message=(
                        f"Reserve ratio = {ratio:.4f} — below required 1.0 "
                        f"(fiat={self._reserve.fiat_balance_idr / 10**18:,.0f} IDR, "
                        f"supply={supply / 10**18:,.0f} IDRC)"
                    ),
                ))

        # 5. Blacklist events (audit trail)
        for blacklist_ev in self._blacklist_events:
            alerts.append(AlertEvent(
                level="INFO",
                code="BLACKLIST_ACTION",
                message=f"Account blacklisted: {blacklist_ev.account} at {blacklist_ev.timestamp.isoformat()}",
            ))

        self._alerts = alerts
        return alerts

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def print_dashboard(self) -> None:
        """Pretty-print a Dune-style analytics dashboard to stdout."""
        dec = 10**18
        ts_str = self._last_synced.isoformat() if self._last_synced else "never"
        summary = self.transfer_summary()
        alerts  = self.run_alert_checks()

        print(f"\n{'═'*62}")
        print(f"  IDRC Monitor Dashboard  │  Synced: {ts_str}")
        print(f"{'═'*62}")
        print(f"  Token         : {self._token.name} ({self._token.symbol})")
        print(f"  Total Supply  : {self.current_supply() / dec:>20,.6f} IDRC")
        print(f"  Total Minted  : {self.total_minted() / dec:>20,.6f} IDRC")
        print(f"  Total Burned  : {self.total_burned() / dec:>20,.6f} IDRC")
        print(f"  Holder Count  : {self.holder_count():>20,}")
        print(f"  Mint Events   : {len(self._mint_events):>20,}")
        print(f"  Burn Events   : {len(self._burn_events):>20,}")
        print(f"  Transfers     : {summary.total_transfers:>20,}")
        if summary.total_transfers:
            print(f"  Transfer Vol  : {summary.total_volume / dec:>20,.6f} IDRC")
            print(f"  Largest Xfer  : {summary.largest_transfer / dec:>20,.6f} IDRC")
        print(f"  Paused        : {self._token.paused!s:>20}")

        if self._reserve is not None:
            print("\n  ── Reserve ──────────────────────────────────────────────")
            fiat = self._reserve.fiat_balance_idr
            supply = self.current_supply()
            ratio = self._reserve.reserve_ratio(supply)
            print(f"  Fiat Balance  : IDR {fiat / dec:>16,.6f}")
            print(f"  Reserve Ratio : {ratio if ratio != float('inf') else '∞':>20}")
            print(f"  Fully Backed  : {self._reserve.is_fully_collateralised(supply)!s:>20}")
            print(f"  Audit Reports : {len(self._reserve.audit_reports):>20,}")

        print("\n  ── Top Holders ──────────────────────────────────────────")
        for i, (addr, bal) in enumerate(self.top_holders(5), 1):
            print(f"  {i}. {addr[:20]:<20}  {bal / dec:>16,.6f} IDRC")

        print(f"\n  ── Alerts ({len(alerts)}) ────────────────────────────────────────")
        if not alerts:
            print("  No alerts. ✓")
        for alert in alerts:
            icon = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(alert.level, "⚪")
            print(f"  {icon} {alert}")
        print(f"{'═'*62}\n")

    # ── Export ────────────────────────────────────────────────────────────────

    def export_csv_rows(self) -> list[dict]:
        """
        Export mint/burn/transfer events as a list of dicts (Dune CSV format).
        In production: feed into a Postgres table or Dune dataset.
        """
        rows = []
        for mint_ev in self._mint_events:
            rows.append({
                "type": "MINT",
                "from": ZERO_ADDRESS,
                "to": mint_ev.to,
                "amount_raw": mint_ev.amount,
                "amount_idrc": mint_ev.amount / 10**18,
                "timestamp": mint_ev.timestamp.isoformat(),
            })
        for burn_ev in self._burn_events:
            rows.append({
                "type": "BURN",
                "from": burn_ev.from_,
                "to": ZERO_ADDRESS,
                "amount_raw": burn_ev.amount,
                "amount_idrc": burn_ev.amount / 10**18,
                "timestamp": burn_ev.timestamp.isoformat(),
            })
        for transfer_ev in self._transfer_events:
            rows.append({
                "type": "TRANSFER",
                "from": transfer_ev.sender,
                "to": transfer_ev.recipient,
                "amount_raw": transfer_ev.amount,
                "amount_idrc": transfer_ev.amount / 10**18,
                "timestamp": transfer_ev.timestamp.isoformat(),
            })
        return rows

    def __repr__(self) -> str:
        return (
            f"IDRCMonitor(supply={self.current_supply():,}, "
            f"holders={self.holder_count()}, "
            f"events={len(self._mint_events) + len(self._burn_events) + len(self._transfer_events)})"
        )
