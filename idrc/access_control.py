"""
idrc/access_control.py
======================
Role-based access control system — mirrors OpenZeppelin's AccessControl.

Roles are arbitrary strings (equivalent to keccak256 hashes in Solidity).
Every account may hold zero or more roles. The DEFAULT_ADMIN_ROLE is the
super-role that can grant / revoke any other role.

Usage
-----
    ac = AccessControl(admin="0xAdmin")
    ac.grant_role(MINTER_ROLE, "0xMinter", caller="0xAdmin")
    ac.check_role(MINTER_ROLE, "0xMinter")   # raises MissingRoleError if absent
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .exceptions import MissingRoleError

# ─── Well-known roles (mirrors keccak256 hashes in Solidity) ────────────────
DEFAULT_ADMIN_ROLE = "DEFAULT_ADMIN_ROLE"
MINTER_ROLE        = "MINTER_ROLE"
BURNER_ROLE        = "BURNER_ROLE"
PAUSER_ROLE        = "PAUSER_ROLE"
UPGRADER_ROLE      = "UPGRADER_ROLE"
BLACKLISTER_ROLE   = "BLACKLISTER_ROLE"

ALL_ROLES = {
    DEFAULT_ADMIN_ROLE,
    MINTER_ROLE,
    BURNER_ROLE,
    PAUSER_ROLE,
    UPGRADER_ROLE,
    BLACKLISTER_ROLE,
}


@dataclass
class RoleGrantedEvent:
    role: str
    account: str
    sender: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return (
            f"[{self.timestamp.isoformat()}] RoleGranted "
            f"role={self.role} account={self.account} by={self.sender}"
        )


@dataclass
class RoleRevokedEvent:
    role: str
    account: str
    sender: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return (
            f"[{self.timestamp.isoformat()}] RoleRevoked "
            f"role={self.role} account={self.account} by={self.sender}"
        )


class AccessControl:
    """
    Implements role-based access control identical to OpenZeppelin AccessControl.

    Key invariants
    --------------
    * Only holders of DEFAULT_ADMIN_ROLE may grant/revoke roles.
    * An account may renounce its own role.
    * Role membership is idempotent — granting an already-held role is a no-op
      (same as OpenZeppelin: event still emitted for transparency).
    """

    def __init__(self, admin: str) -> None:
        if not admin:
            raise ValueError("Admin address must not be empty")
        # role → set of accounts
        self._roles: dict[str, set[str]] = {role: set() for role in ALL_ROLES}
        self._event_log: list = []

        # Bootstrap: give admin the super-role
        self._roles[DEFAULT_ADMIN_ROLE].add(admin)
        event = RoleGrantedEvent(
            role=DEFAULT_ADMIN_ROLE, account=admin, sender="SYSTEM"
        )
        self._event_log.append(event)

    # ── Queries ──────────────────────────────────────────────────────────────

    def has_role(self, role: str, account: str) -> bool:
        """Return True if `account` holds `role`."""
        return account in self._roles.get(role, set())

    def check_role(self, role: str, account: str) -> None:
        """Raise MissingRoleError if `account` does not hold `role`."""
        if not self.has_role(role, account):
            raise MissingRoleError(account, role)

    def get_role_members(self, role: str) -> set[str]:
        """Return a copy of all accounts holding `role`."""
        return set(self._roles.get(role, set()))

    # ── Mutations ────────────────────────────────────────────────────────────

    def grant_role(self, role: str, account: str, *, caller: str) -> None:
        """
        Grant `role` to `account`.
        Caller must hold DEFAULT_ADMIN_ROLE.
        """
        self.check_role(DEFAULT_ADMIN_ROLE, caller)
        if role not in self._roles:
            self._roles[role] = set()
        self._roles[role].add(account)
        event = RoleGrantedEvent(role=role, account=account, sender=caller)
        self._event_log.append(event)

    def revoke_role(self, role: str, account: str, *, caller: str) -> None:
        """
        Revoke `role` from `account`.
        Caller must hold DEFAULT_ADMIN_ROLE.
        """
        self.check_role(DEFAULT_ADMIN_ROLE, caller)
        self._roles.get(role, set()).discard(account)
        event = RoleRevokedEvent(role=role, account=account, sender=caller)
        self._event_log.append(event)

    def renounce_role(self, role: str, *, caller: str) -> None:
        """An account may renounce its own role."""
        self._roles.get(role, set()).discard(caller)
        event = RoleRevokedEvent(role=role, account=caller, sender=caller)
        self._event_log.append(event)

    # ── Introspection ────────────────────────────────────────────────────────

    @property
    def events(self) -> list:
        return list(self._event_log)

    def __repr__(self) -> str:
        summary = {role: list(members) for role, members in self._roles.items() if members}
        return f"AccessControl(roles={summary})"
