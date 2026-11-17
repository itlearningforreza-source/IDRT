"""
idrc/multisig.py
================
Gnosis-Safe-style Multisig Wallet simulation (Section 7.2 & 7.3).

Implements the M-of-N threshold signature pattern used to control all
privileged operations: minting, burning, pausing, upgrading.

Flow
----
1. Any owner proposes a transaction (returns a tx_id).
2. Other owners approve the transaction.
3. Once threshold M approvals are reached, any owner can execute it.
4. A timelock delay (optional) must elapse before execution.

Supports both on-chain-callable functions (as Python callables) and
arbitrary metadata for off-chain workflows.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# ─── Status Enum ─────────────────────────────────────────────────────────────

class TxStatus(Enum):
    PENDING   = "PENDING"
    APPROVED  = "APPROVED"    # threshold reached but not yet executed
    EXECUTED  = "EXECUTED"
    CANCELLED = "CANCELLED"


# ─── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class MultisigTx:
    tx_id: int
    description: str
    fn: Callable | None           # Python callable to execute
    fn_kwargs: dict                   # keyword arguments passed to fn
    proposed_by: str
    approvals: set[str] = field(default_factory=set)
    status: TxStatus = TxStatus.PENDING
    proposed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: datetime | None = None
    timelock_until: float | None = None  # UNIX timestamp

    def __str__(self) -> str:
        return (
            f"[TX #{self.tx_id}] {self.description} | "
            f"status={self.status.value} | "
            f"approvals={len(self.approvals)}/{self.tx_id} | "
            f"by={self.proposed_by}"
        )


@dataclass
class MultisigEvent:
    kind: str   # "PROPOSED", "APPROVED", "EXECUTED", "CANCELLED"
    tx_id: int
    actor: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return (
            f"[{self.timestamp.isoformat()}] Multisig:{self.kind} "
            f"tx_id={self.tx_id} actor={self.actor}"
        )


# ─── MultisigWallet ───────────────────────────────────────────────────────────

class MultisigWallet:
    """
    M-of-N multisig wallet with optional timelock.

    Parameters
    ----------
    owners     : list of owner addresses
    threshold  : minimum approvals needed to execute
    timelock_s : seconds to wait after threshold is reached before execution
                 (0 = no timelock)

    Example (3-of-5)
    ----------------
        ms = MultisigWallet(
            owners=["Alice","Bob","Carol","Dave","Eve"],
            threshold=3,
            timelock_s=0
        )
        tx_id = ms.propose("Mint 1M IDRC", fn=token.mint,
                           fn_kwargs={"to":"0xUser","amount":1_000_000,"caller":"ms"},
                           caller="Alice")
        ms.approve(tx_id, caller="Bob")
        ms.approve(tx_id, caller="Carol")
        ms.execute(tx_id, caller="Alice")
    """

    def __init__(
        self,
        owners: list[str],
        threshold: int,
        timelock_s: int = 0,
    ) -> None:
        if not owners:
            raise ValueError("Multisig: owners list must not be empty")
        if not (1 <= threshold <= len(owners)):
            raise ValueError(
                f"Multisig: threshold {threshold} is invalid for {len(owners)} owners"
            )
        self._owners: set[str] = set(owners)
        self._threshold: int = threshold
        self._timelock_s: int = timelock_s
        self._txs: dict[int, MultisigTx] = {}
        self._next_id: int = 1
        self._event_log: list = []

    # ── Owner Management ─────────────────────────────────────────────────────

    def add_owner(self, new_owner: str, *, caller: str) -> None:
        """Add a new owner. Caller must already be an owner (for demo purposes)."""
        self._require_owner(caller)
        self._owners.add(new_owner)

    def remove_owner(self, owner: str, *, caller: str) -> None:
        """Remove an owner. Ensures threshold remains achievable."""
        self._require_owner(caller)
        if owner not in self._owners:
            raise ValueError(f"Multisig: {owner} is not an owner")
        if len(self._owners) - 1 < self._threshold:
            raise ValueError("Multisig: cannot remove owner — threshold would be unreachable")
        self._owners.discard(owner)

    @property
    def owners(self) -> set[str]:
        return set(self._owners)

    @property
    def threshold(self) -> int:
        return self._threshold

    # ── Transaction Lifecycle ─────────────────────────────────────────────────

    def propose(
        self,
        description: str,
        fn: Callable | None = None,
        fn_kwargs: dict | None = None,
        *,
        caller: str,
    ) -> int:
        """
        Propose a new transaction.
        The proposer's approval is counted automatically.
        Returns tx_id.
        """
        self._require_owner(caller)
        tx_id = self._next_id
        self._next_id += 1

        timelock_until = None
        if self._timelock_s > 0:
            timelock_until = time.time() + self._timelock_s

        tx = MultisigTx(
            tx_id=tx_id,
            description=description,
            fn=fn,
            fn_kwargs=fn_kwargs or {},
            proposed_by=caller,
            approvals={caller},   # proposer auto-approves
            timelock_until=timelock_until,
        )
        self._txs[tx_id] = tx
        self._event_log.append(MultisigEvent("PROPOSED", tx_id, caller))
        self._maybe_mark_approved(tx)
        return tx_id

    def approve(self, tx_id: int, *, caller: str) -> None:
        """Add caller's approval to an existing pending/approved transaction."""
        self._require_owner(caller)
        tx = self._get_pending_tx(tx_id)
        tx.approvals.add(caller)
        self._event_log.append(MultisigEvent("APPROVED", tx_id, caller))
        self._maybe_mark_approved(tx)

    def execute(self, tx_id: int, *, caller: str) -> object:
        """
        Execute a transaction that has reached threshold.
        Returns the result of the callable (if any).
        """
        self._require_owner(caller)
        tx = self._txs.get(tx_id)
        if tx is None:
            raise ValueError(f"Multisig: TX #{tx_id} not found")
        if tx.status == TxStatus.EXECUTED:
            raise ValueError(f"Multisig: TX #{tx_id} already executed")
        if tx.status == TxStatus.CANCELLED:
            raise ValueError(f"Multisig: TX #{tx_id} was cancelled")
        if len(tx.approvals) < self._threshold:
            raise ValueError(
                f"Multisig: TX #{tx_id} needs {self._threshold} approvals, "
                f"has {len(tx.approvals)}"
            )
        if tx.timelock_until and time.time() < tx.timelock_until:
            remaining = tx.timelock_until - time.time()
            raise ValueError(
                f"Multisig: TX #{tx_id} is still timelocked "
                f"({remaining:.0f}s remaining)"
            )

        result = None
        if tx.fn is not None:
            result = tx.fn(**tx.fn_kwargs)

        tx.status = TxStatus.EXECUTED
        tx.executed_at = datetime.now(timezone.utc)
        self._event_log.append(MultisigEvent("EXECUTED", tx_id, caller))
        return result

    def cancel(self, tx_id: int, *, caller: str) -> None:
        """Cancel a pending transaction (only proposer or admin can cancel)."""
        self._require_owner(caller)
        tx = self._get_pending_tx(tx_id)
        if tx.proposed_by != caller:
            raise ValueError(
                f"Multisig: only proposer {tx.proposed_by} can cancel TX #{tx_id}"
            )
        tx.status = TxStatus.CANCELLED
        self._event_log.append(MultisigEvent("CANCELLED", tx_id, caller))

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_tx(self, tx_id: int) -> MultisigTx:
        if tx_id not in self._txs:
            raise ValueError(f"Multisig: TX #{tx_id} not found")
        return self._txs[tx_id]

    def pending_txs(self) -> list[MultisigTx]:
        return [t for t in self._txs.values() if t.status == TxStatus.PENDING]

    def approved_txs(self) -> list[MultisigTx]:
        return [t for t in self._txs.values() if t.status == TxStatus.APPROVED]

    @property
    def events(self) -> list:
        return list(self._event_log)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _require_owner(self, caller: str) -> None:
        if caller not in self._owners:
            raise PermissionError(f"Multisig: {caller!r} is not an owner")

    def _get_pending_tx(self, tx_id: int) -> MultisigTx:
        tx = self._txs.get(tx_id)
        if tx is None:
            raise ValueError(f"Multisig: TX #{tx_id} not found")
        if tx.status not in (TxStatus.PENDING, TxStatus.APPROVED):
            raise ValueError(
                f"Multisig: TX #{tx_id} is not pending (status={tx.status.value})"
            )
        return tx

    def _maybe_mark_approved(self, tx: MultisigTx) -> None:
        if (
            len(tx.approvals) >= self._threshold
            and tx.status == TxStatus.PENDING
        ):
            tx.status = TxStatus.APPROVED

    def __repr__(self) -> str:
        return (
            f"MultisigWallet(owners={len(self._owners)}, "
            f"threshold={self._threshold}, "
            f"txs={len(self._txs)})"
        )
