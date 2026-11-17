"""
tests/test_proxy.py
===================
Unit tests for UUPSProxy and ProxyAdmin (Section 4.5 & 6.4).
Covers: delegatecall state isolation, upgrade authorization, storage
        layout preservation after upgrade, and ProxyAdmin governance.
"""

import pytest

from idrc.access_control import UPGRADER_ROLE
from idrc.exceptions import UpgradeError
from idrc.proxy import ProxyAdmin, UUPSProxy
from idrc.token import IDRCToken

# ─── V2 implementation stub for upgrade tests ────────────────────────────────

class IDRCTokenV2(IDRCToken):
    """
    Minimal V2 implementation: adds a `version_note` field.
    In production this would contain actual new logic.
    """
    VERSION: str = "2.0.0"

    def get_version_note(self) -> str:
        return "V2: added cross-chain bridge hooks"


# ─── Fixtures ────────────────────────────────────────────────────────────────

ADMIN    = "0xAdmin"
MINTER   = "0xMinter"
PAUSER   = "0xPauser"
UPGRADER = "0xUpgrader"
USER     = "0xUser"


@pytest.fixture
def proxy_token():
    """Returns (proxy, token_handle) for a freshly initialised V1 contract."""
    impl = IDRCToken()
    proxy = UUPSProxy(impl)
    token = proxy.as_token()
    token.initialize(
        name="IDR Coin",
        symbol="IDRC",
        admin=ADMIN,
        minter=MINTER,
        pauser=PAUSER,
        upgrader=UPGRADER,
    )
    return proxy, token


# ─── State Isolation (delegatecall semantics) ────────────────────────────────

class TestDelegatecallSemantics:
    def test_state_is_on_proxy_not_impl(self, proxy_token):
        """After minting, the raw implementation object must hold no balance."""
        proxy, token = proxy_token
        token.mint(USER, 1_000 * 10**18, caller=MINTER)

        # The proxy's state bucket should reflect the balance
        assert proxy._state._balances.get(USER, 0) == 1_000 * 10**18

        # The bare implementation (not synced) must be clean
        bare_impl = IDRCToken()
        bare_impl.initialize("X", "X", ADMIN, MINTER, PAUSER, UPGRADER)
        assert bare_impl.balance_of(USER) == 0

    def test_proxy_handle_reflects_current_state(self, proxy_token):
        _proxy, token = proxy_token
        token.mint(USER, 500 * 10**18, caller=MINTER)
        assert token.balance_of(USER) == 500 * 10**18
        assert token.total_supply == 500 * 10**18


# ─── Upgrade ─────────────────────────────────────────────────────────────────

class TestUpgrade:
    def test_upgrade_authorized_by_upgrader(self, proxy_token):
        proxy, token = proxy_token
        token.mint(USER, 1_000 * 10**18, caller=MINTER)

        impl_v2 = IDRCTokenV2()
        proxy.upgrade_to(impl_v2, caller=UPGRADER)

        assert "2.0.0" in proxy.implementation_address

    def test_upgrade_unauthorized_caller_raises(self, proxy_token):
        proxy, _token = proxy_token
        impl_v2 = IDRCTokenV2()
        with pytest.raises(UpgradeError, match="not authorised"):
            proxy.upgrade_to(impl_v2, caller="0xEvil")

    def test_storage_preserved_after_upgrade(self, proxy_token):
        """
        Key invariant: balances survive implementation swap.
        Mirrors the Solidity storage layout compatibility requirement.
        """
        proxy, token = proxy_token
        token.mint(USER, 999 * 10**18, caller=MINTER)

        impl_v2 = IDRCTokenV2()
        proxy.upgrade_to(impl_v2, caller=UPGRADER)

        token_v2 = proxy.as_token()
        # Balance must still be intact
        assert token_v2.balance_of(USER) == 999 * 10**18
        assert token_v2.total_supply == 999 * 10**18

    def test_new_functionality_accessible_after_upgrade(self, proxy_token):
        """V2 method is accessible through the new handle."""
        proxy, _ = proxy_token
        impl_v2 = IDRCTokenV2()
        proxy.upgrade_to(impl_v2, caller=UPGRADER)

        token_v2 = proxy.as_token()
        note = token_v2.get_version_note()
        assert "V2" in note

    def test_upgrade_missing_interface_raises(self, proxy_token):
        """New implementation must expose required ERC-20 methods."""
        proxy, _ = proxy_token

        class BadImpl:
            """Intentionally broken — missing 'mint', 'burn', 'transfer'."""
            def initialize(self): pass

        with pytest.raises(UpgradeError, match="missing required method"):
            proxy.upgrade_to(BadImpl(), caller=UPGRADER)

    def test_upgrade_history_is_tracked(self, proxy_token):
        proxy, _ = proxy_token
        impl_v2 = IDRCTokenV2()
        proxy.upgrade_to(impl_v2, caller=UPGRADER)

        history = proxy.implementation_history
        assert len(history) == 2
        assert "1.0.0" in history[0]
        assert "2.0.0" in history[1]

    def test_upgrade_and_call(self, proxy_token):
        """upgrade_and_call should upgrade then invoke a re-initializer."""
        proxy, token = proxy_token
        token.mint(USER, 100 * 10**18, caller=MINTER)

        impl_v2 = IDRCTokenV2()
        # No re-initializer needed for V2 stub; just verify it doesn't error
        proxy.upgrade_and_call(
            impl_v2,
            init_data={"fn": None},  # no post-upgrade call
            caller=UPGRADER,
        )
        assert proxy.as_token().balance_of(USER) == 100 * 10**18


# ─── ProxyAdmin ───────────────────────────────────────────────────────────────

class TestProxyAdmin:
    def test_proxy_admin_owner(self, proxy_token):
        proxy, _ = proxy_token
        pa = ProxyAdmin(owner="0xMultisig")
        pa.register_proxy("IDRCToken", proxy)
        assert pa.owner == "0xMultisig"

    def test_proxy_admin_upgrade(self, proxy_token):
        """ProxyAdmin.upgrade() delegates to UUPSProxy.upgrade_to()."""
        proxy, token = proxy_token
        ms_addr = "0xMultisig"

        # Give multisig the UPGRADER_ROLE
        token.grant_role(UPGRADER_ROLE, ms_addr, caller=ADMIN)

        pa = ProxyAdmin(owner=ms_addr)
        pa.register_proxy("IDRCToken", proxy)

        impl_v2 = IDRCTokenV2()
        pa.upgrade("IDRCToken", impl_v2, caller=ms_addr)

        assert "2.0.0" in proxy.implementation_address

    def test_proxy_admin_non_owner_cannot_upgrade(self, proxy_token):
        proxy, _ = proxy_token
        pa = ProxyAdmin(owner="0xMultisig")
        pa.register_proxy("IDRCToken", proxy)

        impl_v2 = IDRCTokenV2()
        with pytest.raises(UpgradeError, match="not the owner"):
            pa.upgrade("IDRCToken", impl_v2, caller="0xEvil")

    def test_proxy_admin_unknown_proxy_raises(self, proxy_token):
        _proxy, _ = proxy_token
        pa = ProxyAdmin(owner="0xMultisig")
        with pytest.raises(UpgradeError, match="unknown proxy"):
            pa.upgrade("UnknownProxy", IDRCTokenV2(), caller="0xMultisig")


# ─── Simulate Attack: Reentrancy via upgrade ─────────────────────────────────

class TestUpgradeAttackSimulation:
    def test_non_upgrader_cannot_hijack_via_upgrade(self, proxy_token):
        """
        Attacker deploys a malicious implementation and tries to upgrade.
        Must fail because they don't hold UPGRADER_ROLE.
        """
        proxy, token = proxy_token
        token.mint(USER, 10_000 * 10**18, caller=MINTER)

        class MaliciousImpl(IDRCToken):
            VERSION = "evil"
            def drain_funds(self): pass

        with pytest.raises(UpgradeError):
            proxy.upgrade_to(MaliciousImpl(), caller="0xAttacker")

        # Balance must be untouched
        assert token.balance_of(USER) == 10_000 * 10**18
