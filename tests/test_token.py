"""
tests/test_token.py
===================
Unit tests for IDRCToken (Section 6.1).
Covers: initialization, access control (roles), minting, burning, pausing,
blacklisting, and the integration of these features with ERC-20 transfers.
"""

import pytest

from idrc.access_control import (
    BLACKLISTER_ROLE,
    BURNER_ROLE,
    DEFAULT_ADMIN_ROLE,
    MINTER_ROLE,
    PAUSER_ROLE,
)
from idrc.exceptions import (
    AlreadyInitializedError,
    BlacklistedError,
    MissingRoleError,
    PausedError,
)
from idrc.token import IDRCToken


@pytest.fixture
def addresses():
    class Addrs:
        admin = "0xAdmin"
        minter = "0xMinter"
        pauser = "0xPauser"
        upgrader = "0xUpgrader"
        user1 = "0xUser1"
        user2 = "0xUser2"
    return Addrs


@pytest.fixture
def token(addresses):
    t = IDRCToken()
    t.initialize(
        name="IDR Coin",
        symbol="IDRC",
        admin=addresses.admin,
        minter=addresses.minter,
        pauser=addresses.pauser,
        upgrader=addresses.upgrader,
    )
    return t


# ─── Initialization ──────────────────────────────────────────────────────────

class TestInitialization:
    def test_cannot_initialize_twice(self, token, addresses):
        with pytest.raises(AlreadyInitializedError):
            token.initialize(
                "Fake", "FAKE",
                addresses.admin, addresses.minter,
                addresses.pauser, addresses.upgrader
            )

    def test_roles_assigned_correctly(self, token, addresses):
        assert token.has_role(DEFAULT_ADMIN_ROLE, addresses.admin)
        assert token.has_role(MINTER_ROLE, addresses.minter)
        assert token.has_role(PAUSER_ROLE, addresses.pauser)
        # Burner and blacklister should default to minter and admin respectively
        assert token.has_role(BURNER_ROLE, addresses.minter)
        assert token.has_role(BLACKLISTER_ROLE, addresses.admin)


# ─── Minting & Burning ───────────────────────────────────────────────────────

class TestMintBurn:
    def test_mint_success(self, token, addresses):
        token.mint(addresses.user1, 1000, caller=addresses.minter)
        assert token.balance_of(addresses.user1) == 1000

    def test_mint_missing_role(self, token, addresses):
        with pytest.raises(MissingRoleError):
            token.mint(addresses.user1, 1000, caller=addresses.user1)

    def test_issuer_burn_success(self, token, addresses):
        token.mint(addresses.user1, 1000, caller=addresses.minter)
        token.issuer_burn(addresses.user1, 400, caller=addresses.minter)
        assert token.balance_of(addresses.user1) == 600

    def test_user_burn_success(self, token, addresses):
        token.mint(addresses.user1, 1000, caller=addresses.minter)
        token.burn(300, caller=addresses.user1)
        assert token.balance_of(addresses.user1) == 700


# ─── Pausable ────────────────────────────────────────────────────────────────

class TestPausable:
    def test_pause_unpause(self, token, addresses):
        assert not token.paused
        token.pause(caller=addresses.pauser)
        assert token.paused
        token.unpause(caller=addresses.pauser)
        assert not token.paused

    def test_pause_missing_role(self, token, addresses):
        with pytest.raises(MissingRoleError):
            token.pause(caller=addresses.user1)

    def test_cannot_transfer_when_paused(self, token, addresses):
        token.mint(addresses.user1, 1000, caller=addresses.minter)
        token.pause(caller=addresses.pauser)

        with pytest.raises(PausedError):
            token.transfer(addresses.user2, 100, caller=addresses.user1)

        token.unpause(caller=addresses.pauser)
        token.transfer(addresses.user2, 100, caller=addresses.user1)
        assert token.balance_of(addresses.user2) == 100

    def test_cannot_mint_burn_when_paused(self, token, addresses):
        token.mint(addresses.user1, 1000, caller=addresses.minter)
        token.pause(caller=addresses.pauser)

        with pytest.raises(PausedError):
            token.mint(addresses.user1, 500, caller=addresses.minter)

        with pytest.raises(PausedError):
            token.burn(200, caller=addresses.user1)


# ─── Blacklist ───────────────────────────────────────────────────────────────

class TestBlacklist:
    def test_blacklist_unblacklist(self, token, addresses):
        assert not token.is_blacklisted(addresses.user1)
        token.blacklist(addresses.user1, caller=addresses.admin)
        assert token.is_blacklisted(addresses.user1)
        token.un_blacklist(addresses.user1, caller=addresses.admin)
        assert not token.is_blacklisted(addresses.user1)

    def test_blacklist_missing_role(self, token, addresses):
        with pytest.raises(MissingRoleError):
            token.blacklist(addresses.user1, caller=addresses.user1)

    def test_blacklisted_cannot_send(self, token, addresses):
        token.mint(addresses.user1, 1000, caller=addresses.minter)
        token.blacklist(addresses.user1, caller=addresses.admin)

        with pytest.raises(BlacklistedError):
            token.transfer(addresses.user2, 100, caller=addresses.user1)

    def test_blacklisted_cannot_receive(self, token, addresses):
        token.mint(addresses.user1, 1000, caller=addresses.minter)
        token.blacklist(addresses.user2, caller=addresses.admin)

        with pytest.raises(BlacklistedError):
            token.transfer(addresses.user2, 100, caller=addresses.user1)

    def test_blacklisted_cannot_burn(self, token, addresses):
        token.mint(addresses.user1, 1000, caller=addresses.minter)
        token.blacklist(addresses.user1, caller=addresses.admin)

        with pytest.raises(BlacklistedError):
            token.burn(100, caller=addresses.user1)

    def test_cannot_mint_to_blacklisted(self, token, addresses):
        token.blacklist(addresses.user1, caller=addresses.admin)
        with pytest.raises(BlacklistedError):
            token.mint(addresses.user1, 1000, caller=addresses.minter)
