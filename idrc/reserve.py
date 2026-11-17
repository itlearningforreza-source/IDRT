"""
idrc/reserve.py
===============
IDRCReserve — on-chain reserve management module (Section 4.6).

Handles two proof-of-reserve approaches:

A. Off-chain with Audit Hashes
   - Auditor submits a SHA-256 hash of the reserve report PDF.
   - Anyone can verify by hashing the PDF themselves.
   - `update_reserve_proof(hash, caller=admin)` stores the hash on-chain.

B. Oracle-based (simulated)
   - A trusted oracle (e.g. Chainlink-style) pushes fiat balance updates.
   - The reserve ratio = fiat_balance / token_total_supply is computed on-chain.
   - An alert is raised if the ratio drops below the MIN_RESERVE_RATIO.

Usage
-----
    reserve = IDRCReserve(admin="0xAdmin", oracle="0xOracle")
    reserve.update_fiat_balance(1_000_000 * 10**18, caller="0xOracle")
    ratio = reserve.reserve_ratio(token_total_supply)
    proof  = reserve.submit_audit_proof("sha256:abc123...", caller="0xAdmin")
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .exceptions import AccessControlError, ReserveError

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
MIN_RESERVE_RATIO = 1.0   # 100 % collateralisation required


@dataclass
class AuditReport:
    """Represents a single auditor-submitted reserve report."""
    seq: int
    proof_hash: str          # SHA-256 of the PDF / CSV report
    reported_fiat_idr: int   # Fiat balance in IDR (in raw units, x 10^18)
    submitted_by: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        idr_whole = self.reported_fiat_idr // 10**18
        return (
            f"[Report #{self.seq}] "
            f"hash={self.proof_hash[:16]}... "
            f"fiat=IDR {idr_whole:,} "
            f"by={self.submitted_by} "
            f"at={self.timestamp.isoformat()}"
        )


@dataclass
class OraclePriceUpdatedEvent:
    oracle: str
    new_balance: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return (
            f"[{self.timestamp.isoformat()}] OracleUpdate "
            f"oracle={self.oracle} fiat_balance={self.new_balance}"
        )


class IDRCReserve:
    """
    On-chain reserve management contract.

    Roles
    -----
    admin   → submit audit proofs, set oracle address
    oracle  → push fiat balance updates
    """

    def __init__(self, admin: str, oracle: str | None = None) -> None:
        if not admin:
            raise ValueError("Admin address must not be empty")
        self._admin = admin
        self._oracle = oracle

        # Off-chain proof storage
        self._audit_reports: list[AuditReport] = []
        self._latest_proof_hash: str = ""

        # Oracle-based fiat balance (raw integer, 18 decimals)
        self._fiat_balance_idr: int = 0
        self._last_oracle_update: datetime | None = None

        self._event_log: list = []

    # ── Admin setters ─────────────────────────────────────────────────────────

    def set_oracle(self, oracle_address: str, *, caller: str) -> None:
        """Admin can change the trusted oracle address."""
        self._require_admin(caller)
        self._oracle = oracle_address

    # ── Approach A: Off-chain Audit Proofs ────────────────────────────────────

    def submit_audit_proof(
        self,
        proof_hash: str,
        reported_fiat_idr: int,
        *,
        caller: str,
    ) -> AuditReport:
        """
        Admin submits a new reserve proof hash.
        proof_hash should be SHA-256 of the auditor report file.
        reported_fiat_idr is the total Rupiah in custody (x 10^18).
        """
        self._require_admin(caller)
        if not proof_hash:
            raise ReserveError("Reserve: proof hash must not be empty")
        if reported_fiat_idr < 0:
            raise ReserveError("Reserve: fiat balance cannot be negative")

        seq = len(self._audit_reports) + 1
        report = AuditReport(
            seq=seq,
            proof_hash=proof_hash,
            reported_fiat_idr=reported_fiat_idr,
            submitted_by=caller,
        )
        self._audit_reports.append(report)
        self._latest_proof_hash = proof_hash
        self._event_log.append(report)
        return report

    @staticmethod
    def compute_proof_hash(report_bytes: bytes) -> str:
        """
        Utility: compute the SHA-256 hash of an audit report file.
        Pass the raw bytes of the PDF/CSV to get the on-chain proof hash.
        """
        return hashlib.sha256(report_bytes).hexdigest()

    def verify_proof(self, report_bytes: bytes) -> bool:
        """
        Off-chain verifier: returns True if the hash of `report_bytes`
        matches the latest published on-chain hash.
        """
        if not self._latest_proof_hash:
            return False
        computed = self.compute_proof_hash(report_bytes)
        return computed == self._latest_proof_hash

    # ── Approach B: Oracle-based Fiat Balance ─────────────────────────────────

    def update_fiat_balance(self, new_balance_idr: int, *, caller: str) -> None:
        """
        Trusted oracle pushes the current fiat-in-custody balance.
        new_balance_idr is the total Rupiah held by the custodian bank (x 10^18).
        """
        if caller != self._oracle:
            raise AccessControlError(
                f"Reserve: caller {caller} is not the trusted oracle"
            )
        if new_balance_idr < 0:
            raise ReserveError("Reserve: fiat balance cannot be negative")
        self._fiat_balance_idr = new_balance_idr
        self._last_oracle_update = datetime.now(timezone.utc)
        self._event_log.append(
            OraclePriceUpdatedEvent(oracle=caller, new_balance=new_balance_idr)
        )

    def reserve_ratio(self, token_total_supply: int) -> float:
        """
        Compute the current collateralisation ratio.
        Returns float: ≥ 1.0 means fully backed, < 1.0 means under-collateralised.
        Returns inf if total_supply is 0 (fully backed vacuously).
        """
        if token_total_supply == 0:
            return float("inf")
        return self._fiat_balance_idr / token_total_supply

    def is_fully_collateralised(self, token_total_supply: int) -> bool:
        """True if fiat_balance ≥ token_total_supply (1:1 backing)."""
        return self.reserve_ratio(token_total_supply) >= MIN_RESERVE_RATIO

    def check_collateralisation(self, token_total_supply: int) -> None:
        """Raise ReserveError if reserve ratio drops below minimum."""
        if not self.is_fully_collateralised(token_total_supply):
            ratio = self.reserve_ratio(token_total_supply)
            raise ReserveError(
                f"Reserve: under-collateralised — ratio={ratio:.4f} "
                f"(fiat={self._fiat_balance_idr}, supply={token_total_supply})"
            )

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def latest_proof_hash(self) -> str:
        return self._latest_proof_hash

    @property
    def fiat_balance_idr(self) -> int:
        return self._fiat_balance_idr

    @property
    def last_oracle_update(self) -> datetime | None:
        return self._last_oracle_update

    @property
    def audit_reports(self) -> list:
        return list(self._audit_reports)

    @property
    def events(self) -> list:
        return list(self._event_log)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _require_admin(self, caller: str) -> None:
        if caller != self._admin:
            raise AccessControlError(
                f"Reserve: caller {caller} is not the admin"
            )

    def __repr__(self) -> str:
        return (
            f"IDRCReserve(admin={self._admin!r}, "
            f"oracle={self._oracle!r}, "
            f"fiat_balance={self._fiat_balance_idr:,}, "
            f"reports={len(self._audit_reports)})"
        )
