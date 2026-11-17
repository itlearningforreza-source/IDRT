"""
idrc/token.py
=============
IDRCToken — the main stablecoin contract.

This is the Python equivalent of the Solidity contract in Section 4.1 of the
technical design document. It composes:

  - ERC20Base          → token balances, transfer, approve, permit
  - AccessControl      → role-based permission system
  - Pausable           → emergency halt
  - Blacklist          → freeze flagged accounts
  - UUPS upgradeability → contract version management (via Proxy in proxy.py)
  - Reserve Proof      → on-chain hash of audited reserve report

Roles
-----
  DEFAULT_ADMIN_ROLE   - manages all other roles
  MINTER_ROLE          - calls mint()
  BURNER_ROLE          - calls issuer_burn()
  PAUSER_ROLE          - calls pause() / unpause()
  UPGRADER_ROLE        - authorises contract upgrades
  BLACKLISTER_ROLE     - calls blacklist() / un_blacklist()
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .access_control import (
    BLACKLISTER_ROLE,
    BURNER_ROLE,
    DEFAULT_ADMIN_ROLE,
    MINTER_ROLE,
    PAUSER_ROLE,
    UPGRADER_ROLE,
    AccessControl,
)
from .erc20 import ZERO_ADDRESS, ERC20Base
from .exceptions import (
    AlreadyBlacklistedError,
    AlreadyInitializedError,
    BlacklistedError,
    NotBlacklistedError,
    NotPausedError,
    PausedError,
    SupplyCapExceededError,
    ZeroAddressError,
    ZeroAmountError,
)

# ─── Extra Events ─────────────────────────────────────────────────────────────

@dataclass
class MintEvent:
    to: str
    amount: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return f"[{self.timestamp.isoformat()}] Mint to={self.to} amount={self.amount}"


@dataclass
class BurnEvent:
    from_: str
    amount: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return f"[{self.timestamp.isoformat()}] Burn from={self.from_} amount={self.amount}"


@dataclass
class BlacklistedEvent:
    account: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return f"[{self.timestamp.isoformat()}] Blacklisted account={self.account}"


@dataclass
class UnBlacklistedEvent:
    account: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return f"[{self.timestamp.isoformat()}] UnBlacklisted account={self.account}"


@dataclass
class PausedEvent:
    account: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return f"[{self.timestamp.isoformat()}] Paused by={self.account}"


@dataclass
class UnpausedEvent:
    account: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return f"[{self.timestamp.isoformat()}] Unpaused by={self.account}"


@dataclass
class ReserveProofUpdatedEvent:
    proof_hash: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return (
            f"[{self.timestamp.isoformat()}] ReserveProofUpdated "
            f"hash={self.proof_hash[:16]}..."
        )


# ─── IDRCToken ────────────────────────────────────────────────────────────────

class IDRCToken(ERC20Base):
    """
    Full IDRC stablecoin implementation.

    Designed to be registered with a Proxy (see idrc/proxy.py) so that it can
    be swapped out for a new version while retaining the proxy address.

    Initialisation is done via ``initialize()`` (not ``__init__``) so that a
    Proxy can create a bare instance and then call ``initialize()`` — identical
    to OpenZeppelin's ``Initializable`` pattern.
    """

    #: Version string — bumped in each new implementation.
    VERSION: str = "1.0.0"

    def __init__(self) -> None:
        # Do NOT call ERC20Base.__init__ here.
        # Proxy calls initialize() after construction.
        self._initialized: bool = False
        # Populated by initialize():
        self._name: str = ""
        self._symbol: str = ""
        self._total_supply: int = 0
        self._balances: dict = {}
        self._allowances: dict = {}
        self._event_log: list = []
        self._permit_nonces: dict = {}
        self._domain_separator: str = ""
        self._paused: bool = False
        self._blacklisted: dict = {}
        self._access: AccessControl = None  # type: ignore
        self._reserve_proof_hash: str = ""
        self._supply_cap: int = 10_000_000_000 * 10**18

    # ── Initialiser (mirrors Solidity initializer modifier) ───────────────────

    def initialize(
        self,
        name: str,
        symbol: str,
        admin: str,
        minter: str,
        pauser: str,
        upgrader: str,
        burner: str | None = None,
        blacklister: str | None = None,
    ) -> None:
        """
        One-time initialiser — can only be called once.
        Equivalent to OpenZeppelin's `initialize` with `initializer` modifier.
        """
        if self._initialized:
            raise AlreadyInitializedError()

        # ERC20 base setup
        self._name = name
        self._symbol = symbol
        self._total_supply = 0
        self._balances = {}
        self._allowances = {}
        self._event_log = []
        self._permit_nonces = {}
        self._domain_separator = hashlib.sha256(
            f"EIP712Domain:{name}:IDRC:1".encode()
        ).hexdigest()

        # Pausable
        self._paused = False

        # Blacklist
        self._blacklisted = {}

        # Access control
        self._access = AccessControl(admin=admin)
        self._access.grant_role(MINTER_ROLE, minter, caller=admin)
        self._access.grant_role(PAUSER_ROLE, pauser, caller=admin)
        self._access.grant_role(UPGRADER_ROLE, upgrader, caller=admin)
        # Burner defaults to minter if not specified (common pattern)
        self._access.grant_role(BURNER_ROLE, burner or minter, caller=admin)
        # Blacklister defaults to admin if not specified
        self._access.grant_role(BLACKLISTER_ROLE, blacklister or admin, caller=admin)

        # Reserve proof
        self._reserve_proof_hash = ""
        self._supply_cap = 10_000_000_000 * 10**18

        self._initialized = True

    # ── Pausable ──────────────────────────────────────────────────────────────

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self, *, caller: str) -> None:
        """Halt all token transfers. Caller must hold PAUSER_ROLE."""
        self._access.check_role(PAUSER_ROLE, caller)
        if self._paused:
            raise PausedError()
        self._paused = True
        self._event_log.append(PausedEvent(account=caller))

    def unpause(self, *, caller: str) -> None:
        """Resume token transfers. Caller must hold PAUSER_ROLE."""
        self._access.check_role(PAUSER_ROLE, caller)
        if not self._paused:
            raise NotPausedError()
        self._paused = False
        self._event_log.append(UnpausedEvent(account=caller))

    def _require_not_paused(self) -> None:
        if self._paused:
            raise PausedError()

    # ── Blacklist ─────────────────────────────────────────────────────────────

    def is_blacklisted(self, account: str) -> bool:
        return self._blacklisted.get(account, False)

    def blacklist(self, account: str, *, caller: str) -> None:
        """Add `account` to the blacklist. Caller must hold BLACKLISTER_ROLE."""
        self._access.check_role(BLACKLISTER_ROLE, caller)
        if account == ZERO_ADDRESS:
            raise ZeroAddressError("blacklist zero address")
        if self._blacklisted.get(account):
            raise AlreadyBlacklistedError(account)
        self._blacklisted[account] = True
        self._event_log.append(BlacklistedEvent(account=account))

    def un_blacklist(self, account: str, *, caller: str) -> None:
        """Remove `account` from the blacklist. Caller must hold BLACKLISTER_ROLE."""
        self._access.check_role(BLACKLISTER_ROLE, caller)
        if not self._blacklisted.get(account):
            raise NotBlacklistedError(account)
        self._blacklisted[account] = False
        self._event_log.append(UnBlacklistedEvent(account=account))

    # ── _beforeTokenTransfer hook (overrides ERC20Base) ───────────────────────

    def _before_token_transfer(self, sender: str, recipient: str, amount: int) -> None:
        """
        Enforce pause + blacklist on every mint / burn / transfer.
        Mirrors the Solidity _beforeTokenTransfer override.
        """
        self._require_not_paused()
        # During mint, sender is ZERO_ADDRESS — skip blacklist for that side
        if sender != ZERO_ADDRESS and self._blacklisted.get(sender):
            raise BlacklistedError(sender)
        # During burn, recipient is ZERO_ADDRESS — skip blacklist for that side
        if recipient != ZERO_ADDRESS and self._blacklisted.get(recipient):
            raise BlacklistedError(recipient)

    # ── Minting ───────────────────────────────────────────────────────────────

    def mint(self, to: str, amount: int, *, caller: str) -> None:
        """
        Issue new IDRC tokens to `to`.
        Caller must hold MINTER_ROLE.
        Equivalent to off-chain operator calling mint() after receiving fiat deposit.
        """
        self._access.check_role(MINTER_ROLE, caller)
        if to == ZERO_ADDRESS:
            raise ZeroAddressError("mint to zero address")
        if amount <= 0:
            raise ZeroAmountError()
        if self.total_supply + amount > self._supply_cap:
            raise SupplyCapExceededError(self.total_supply + amount, self._supply_cap)
        self._mint(to, amount)
        self._event_log.append(MintEvent(to=to, amount=amount))

    def set_supply_cap(self, new_cap: int, *, caller: str) -> None:
        """Update the maximum token supply cap. Caller must hold DEFAULT_ADMIN_ROLE."""
        self._access.check_role(DEFAULT_ADMIN_ROLE, caller)
        self._supply_cap = new_cap

    # ── Burning ───────────────────────────────────────────────────────────────

    def issuer_burn(self, from_: str, amount: int, *, caller: str) -> None:
        """
        Issuer destroys IDRC held by `from_`.
        Caller must hold BURNER_ROLE.
        Called after fiat has been sent back to the redeemer.
        """
        self._access.check_role(BURNER_ROLE, caller)
        if from_ == ZERO_ADDRESS:
            raise ZeroAddressError("burn from zero address")
        if amount <= 0:
            raise ZeroAmountError()
        self._burn(from_, amount)
        self._event_log.append(BurnEvent(from_=from_, amount=amount))

    def burn(self, amount: int, *, caller: str) -> None:
        """
        Any token holder may destroy their own IDRC tokens.
        Off-chain system will then release fiat to their bank account.
        """
        if amount <= 0:
            raise ZeroAmountError()
        self._burn(caller, amount)
        self._event_log.append(BurnEvent(from_=caller, amount=amount))

    # ── Reserve Proof (Section 4.6) ───────────────────────────────────────────

    @property
    def reserve_proof_hash(self) -> str:
        """Latest published reserve proof hash (SHA-256 of auditor report PDF)."""
        return self._reserve_proof_hash

    def update_reserve_proof(self, new_hash: str, *, caller: str) -> None:
        """
        Admin publishes a new reserve proof.
        Caller must hold DEFAULT_ADMIN_ROLE.
        """
        self._access.check_role(DEFAULT_ADMIN_ROLE, caller)
        self._reserve_proof_hash = new_hash
        self._event_log.append(ReserveProofUpdatedEvent(proof_hash=new_hash))

    # ── Upgradeability Guard (UUPS pattern) ───────────────────────────────────

    def authorize_upgrade(self, new_implementation: object, *, caller: str) -> None:
        """
        Only accounts with UPGRADER_ROLE may approve a new implementation.
        Called by the Proxy before swapping the implementation reference.
        """
        self._access.check_role(UPGRADER_ROLE, caller)

    # ── Access-control pass-throughs ──────────────────────────────────────────

    @property
    def access_control(self) -> AccessControl:
        return self._access

    def grant_role(self, role: str, account: str, *, caller: str) -> None:
        self._access.grant_role(role, account, caller=caller)

    def revoke_role(self, role: str, account: str, *, caller: str) -> None:
        self._access.revoke_role(role, account, caller=caller)

    def has_role(self, role: str, account: str) -> bool:
        return self._access.has_role(role, account)

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def events(self) -> list:
        return list(self._event_log) + self._access.events

    def all_holders(self) -> dict:
        """Return all accounts with a non-zero balance."""
        return {k: v for k, v in self._balances.items() if v > 0}

    def __repr__(self) -> str:
        return (
            f"IDRCToken(version={self.VERSION!r}, "
            f"name={self._name!r}, symbol={self._symbol!r}, "
            f"total_supply={self._total_supply:,}, "
            f"paused={self._paused})"
        )
