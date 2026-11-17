"""
idrc/proxy.py
=============
UUPS (Universal Upgradeable Proxy Standard) — Python simulation.

Architecture (mirrors Section 3 of the design doc):

  Proxy  ─delegatecall→  Implementation (IDRCToken V1, V2, …)

The Proxy holds ALL state. The Implementation contains ONLY logic.
When upgraded:
  1. Admin calls proxy.upgrade_to(new_impl, caller=upgrader)
  2. Proxy calls new_impl.authorize_upgrade(new_impl, caller=upgrader)
  3. Proxy stores new_impl as the active implementation.
  4. All future calls are forwarded to the new implementation.

In Python we model "delegatecall" by copying the proxy's state dict INTO the
implementation object before each call, then copying it back out afterwards.
This ensures state is always stored on the Proxy side, not the Implementation.

ProxyAdmin
----------
A lightweight wrapper that owns the proxy and is itself owned by a Multisig.
"""

from __future__ import annotations

import copy
from typing import Any

from .exceptions import MissingRoleError, UpgradeError


class _ProxyState:
    """Bucket that holds ALL mutable state for the proxy."""

    def __init__(self) -> None:
        self._initialized: bool = False
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
        self._access: Any = None
        self._reserve_proof_hash: str = ""


class UUPSProxy:
    """
    Transparent UUPS proxy.

    Usage
    -----
        impl_v1 = IDRCToken()
        proxy = UUPSProxy(impl_v1)
        token = proxy.as_token()          # obtain a live delegate-call handle
        token.initialize(...)             # first call
        token.mint(to, 1_000, caller=minter)

        # Upgrade
        impl_v2 = IDRCTokenV2()
        proxy.upgrade_to(impl_v2, caller=upgrader)
        token = proxy.as_token()          # obtain fresh handle to new impl
    """

    def __init__(self, initial_implementation: Any) -> None:
        self._state = _ProxyState()
        self._impl = initial_implementation
        self._impl_history: list = [initial_implementation]  # audit trail

    # ── Upgrade ───────────────────────────────────────────────────────────────

    def upgrade_to(self, new_implementation: Any, *, caller: str) -> None:
        """
        Replace the active implementation.
        1. Flush current state into the current impl to authorise.
        2. Current impl checks UPGRADER_ROLE (authorize_upgrade).
        3. If ok, swap to new_implementation.

        Mirrors UUPS: the logic to authorise the upgrade lives in the
        *current* implementation, not in the proxy.
        """
        # Sync state so the current impl can do its access check
        self._sync_state_to_impl(self._impl)
        try:
            self._impl.authorize_upgrade(new_implementation, caller=caller)
        except MissingRoleError:
            raise UpgradeError(
                f"UUPS: caller {caller} is not authorised to upgrade"
            ) from None

        # Validate new_implementation has the expected interface
        for attr in ("initialize", "mint", "burn", "transfer"):
            if not hasattr(new_implementation, attr):
                raise UpgradeError(
                    f"UUPS: new implementation missing required method '{attr}'"
                )

        # Perform the upgrade
        prev = self._impl
        self._impl = new_implementation
        self._impl_history.append(new_implementation)

        # Sync state into the new implementation
        self._sync_state_to_impl(self._impl)

        print(
            f"[UUPSProxy] Upgraded from {prev.__class__.__name__} "
            f"v{getattr(prev, 'VERSION', '?')} → "
            f"{new_implementation.__class__.__name__} "
            f"v{getattr(new_implementation, 'VERSION', '?')} "
            f"by {caller}"
        )

    def upgrade_and_call(
        self, new_implementation: Any, init_data: dict, *, caller: str
    ) -> None:
        """Upgrade then call a re-initializer on the new implementation."""
        self.upgrade_to(new_implementation, caller=caller)
        token = self.as_token()
        fn_name = init_data.pop("fn", None)
        if fn_name:
            getattr(token, fn_name)(**init_data)

    # ── Token Handle ──────────────────────────────────────────────────────────

    def as_token(self) -> _TokenHandle:
        """Return a live delegate-call handle to the current implementation."""
        return _TokenHandle(self)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _sync_state_to_impl(self, impl: Any) -> None:
        """Copy proxy state attributes into `impl`."""
        for attr, val in self._state.__dict__.items():
            # Deep-copy mutable objects so proxy and impl don't alias
            setattr(impl, attr, copy.deepcopy(val))

    def _sync_state_from_impl(self, impl: Any) -> None:
        """Copy state back from `impl` into proxy storage."""
        for attr in self._state.__dict__:
            self._state.__dict__[attr] = copy.deepcopy(getattr(impl, attr, None))

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def implementation_address(self) -> str:
        return f"<{self._impl.__class__.__name__} v{getattr(self._impl, 'VERSION', '?')}>"

    @property
    def implementation_history(self) -> list:
        return [
            f"<{i.__class__.__name__} v{getattr(i, 'VERSION', '?')}>"
            for i in self._impl_history
        ]


class _TokenHandle:
    """
    Delegate-call handle: every attribute access or method call is forwarded
    to the proxy's current implementation WITH the proxy's state injected first
    and extracted afterwards.

    This faithfully simulates Solidity delegatecall semantics.
    """

    def __init__(self, proxy: UUPSProxy) -> None:
        object.__setattr__(self, "_proxy", proxy)

    def __getattr__(self, name: str) -> Any:
        proxy: UUPSProxy = object.__getattribute__(self, "_proxy")
        impl = proxy._impl

        # Sync state into implementation
        proxy._sync_state_to_impl(impl)

        attr = getattr(impl, name)

        if not callable(attr):
            # For non-callable (e.g. .paused, .total_supply) just return value
            return attr

        def delegated(*args, **kwargs):
            proxy._sync_state_to_impl(impl)
            result = attr(*args, **kwargs)
            proxy._sync_state_from_impl(impl)
            return result

        return delegated


# ─── ProxyAdmin ───────────────────────────────────────────────────────────────

class ProxyAdmin:
    """
    Manages proxy ownership and upgrade governance.
    In production this role is held by a Gnosis Safe multisig.
    """

    def __init__(self, owner: str) -> None:
        self._owner = owner
        self._proxies: dict = {}

    def register_proxy(self, proxy_name: str, proxy: UUPSProxy) -> None:
        self._proxies[proxy_name] = proxy

    def upgrade(
        self, proxy_name: str, new_implementation: Any, *, caller: str
    ) -> None:
        if caller != self._owner:
            raise UpgradeError(
                f"ProxyAdmin: caller {caller} is not the owner {self._owner}"
            )
        if proxy_name not in self._proxies:
            raise UpgradeError(f"ProxyAdmin: unknown proxy '{proxy_name}'")
        self._proxies[proxy_name].upgrade_to(new_implementation, caller=caller)

    @property
    def owner(self) -> str:
        return self._owner

    def __repr__(self) -> str:
        return f"ProxyAdmin(owner={self._owner!r}, proxies={list(self._proxies)})"
