"""
tests/test_bridge.py
====================
Unit tests for the cross-chain bridge (Section 10.1).
Covers: lock, relay/mint on destination, replay protection,
        round-trip (src → dst → src), and error paths.
"""

import pytest

from idrc.bridge import BridgeVault, ChainID, IDRCBridge
from idrc.proxy import UUPSProxy
from idrc.token import IDRCToken

RELAYER_ADDR = "0xRelayer"
ADMIN        = "0xAdmin"
MINTER       = "0xMinter"
PAUSER       = "0xPauser"
UPGRADER     = "0xUpgrader"
USER         = "0xUser"


def make_token(name: str = "IDR Coin", symbol: str = "IDRC",
               relayer_as_minter: bool = False) -> object:
    """Helper: deploy a fresh token with MINTER_ROLE for relayer (if needed)."""
    impl = IDRCToken()
    proxy = UUPSProxy(impl)
    t = proxy.as_token()
    minter = RELAYER_ADDR if relayer_as_minter else MINTER
    t.initialize(
        name=name, symbol=symbol,
        admin=ADMIN, minter=minter, pauser=PAUSER, upgrader=UPGRADER,
    )
    if not relayer_as_minter:
        # Also grant MINTER to relayer so it can mint bridged tokens
        t.grant_role("MINTER_ROLE", RELAYER_ADDR, caller=ADMIN)
    return t


@pytest.fixture
def eth_token():
    return make_token()


@pytest.fixture
def poly_token():
    return make_token()


@pytest.fixture
def bridge(eth_token, poly_token):
    b = IDRCBridge(relayer_address=RELAYER_ADDR)
    eth_vault  = BridgeVault(chain=ChainID.ETHEREUM, relayer_address=RELAYER_ADDR)
    poly_vault = BridgeVault(chain=ChainID.POLYGON,  relayer_address=RELAYER_ADDR)

    b.register_chain(ChainID.ETHEREUM, eth_vault, eth_token)
    b.register_chain(ChainID.POLYGON,  poly_vault, poly_token)
    return b


# ─── Construction ─────────────────────────────────────────────────────────────

class TestBridgeConstruction:
    def test_vault_initial_state(self):
        vault = BridgeVault(chain=ChainID.ETHEREUM, relayer_address=RELAYER_ADDR)
        assert vault.total_locked == 0
        assert vault.chain == ChainID.ETHEREUM

    def test_same_src_dst_raises(self, eth_token):
        vault = BridgeVault(chain=ChainID.ETHEREUM, relayer_address=RELAYER_ADDR)
        eth_token.mint(USER, 1_000 * 10**18, caller=MINTER)
        with pytest.raises(ValueError, match="must differ"):
            vault.lock(eth_token, USER, USER, 1_000 * 10**18, ChainID.ETHEREUM)


# ─── Transfer (Lock + Relay) ──────────────────────────────────────────────────

class TestBridgeTransfer:
    def test_lock_burns_on_source(self, bridge, eth_token):
        eth_token.mint(USER, 1_000 * 10**18, caller=MINTER)
        assert eth_token.total_supply == 1_000 * 10**18

        bridge.transfer(
            src_chain=ChainID.ETHEREUM,
            dst_chain=ChainID.POLYGON,
            sender=USER,
            recipient=USER,
            amount=1_000 * 10**18,
        )

        # Source tokens burned
        assert eth_token.total_supply == 0
        assert eth_token.balance_of(USER) == 0

    def test_relay_mints_on_destination(self, bridge, eth_token, poly_token):
        eth_token.mint(USER, 1_000 * 10**18, caller=MINTER)
        lock_ev = bridge.transfer(
            src_chain=ChainID.ETHEREUM,
            dst_chain=ChainID.POLYGON,
            sender=USER,
            recipient=USER,
            amount=1_000 * 10**18,
        )

        bridge.complete_transfer(lock_ev)

        assert poly_token.balance_of(USER) == 1_000 * 10**18
        assert poly_token.total_supply == 1_000 * 10**18

    def test_total_cross_chain_supply_conserved(self, bridge, eth_token, poly_token):
        """
        Key invariant: total IDRC across all chains remains constant
        (ignoring gas fees, which don't apply in our simulation).
        """
        initial_eth_mint = 5_000 * 10**18
        bridge_amount    = 2_000 * 10**18

        eth_token.mint(USER, initial_eth_mint, caller=MINTER)

        lock_ev = bridge.transfer(
            src_chain=ChainID.ETHEREUM,
            dst_chain=ChainID.POLYGON,
            sender=USER,
            recipient=USER,
            amount=bridge_amount,
        )
        bridge.complete_transfer(lock_ev)

        total = eth_token.total_supply + poly_token.total_supply
        assert total == initial_eth_mint


# ─── Replay Protection ────────────────────────────────────────────────────────

class TestReplayProtection:
    def test_replay_same_lock_event_raises(self, bridge, eth_token, poly_token):
        eth_token.mint(USER, 2_000 * 10**18, caller=MINTER)
        lock_ev = bridge.transfer(
            src_chain=ChainID.ETHEREUM,
            dst_chain=ChainID.POLYGON,
            sender=USER,
            recipient=USER,
            amount=1_000 * 10**18,
        )

        bridge.complete_transfer(lock_ev)

        with pytest.raises(ValueError, match="already processed"):
            bridge.complete_transfer(lock_ev)   # replay attempt

    def test_different_nonces_process_independently(self, bridge, eth_token, poly_token):
        eth_token.mint(USER, 3_000 * 10**18, caller=MINTER)

        lock1 = bridge.transfer(ChainID.ETHEREUM, ChainID.POLYGON, USER, USER, 1_000 * 10**18)
        lock2 = bridge.transfer(ChainID.ETHEREUM, ChainID.POLYGON, USER, USER, 1_000 * 10**18)

        bridge.complete_transfer(lock1)
        bridge.complete_transfer(lock2)

        assert poly_token.balance_of(USER) == 2_000 * 10**18


# ─── Error Paths ─────────────────────────────────────────────────────────────

class TestBridgeErrors:
    def test_transfer_zero_amount_raises(self, bridge, eth_token):
        eth_token.mint(USER, 100 * 10**18, caller=MINTER)
        with pytest.raises(ValueError, match="amount must be > 0"):
            bridge.transfer(ChainID.ETHEREUM, ChainID.POLYGON, USER, USER, 0)

    def test_transfer_unregistered_src_raises(self, bridge, eth_token):
        eth_token.mint(USER, 100 * 10**18, caller=MINTER)
        with pytest.raises(ValueError, match="not registered"):
            bridge.transfer(ChainID.BSC, ChainID.POLYGON, USER, USER, 100 * 10**18)

    def test_transfer_unregistered_dst_raises(self, bridge, eth_token):
        eth_token.mint(USER, 100 * 10**18, caller=MINTER)
        with pytest.raises(ValueError, match="not registered"):
            bridge.transfer(ChainID.ETHEREUM, ChainID.BSC, USER, USER, 100 * 10**18)

    def test_transfer_insufficient_balance_raises(self, bridge, eth_token):
        eth_token.mint(USER, 100 * 10**18, caller=MINTER)
        from idrc.exceptions import InsufficientBalanceError
        with pytest.raises(InsufficientBalanceError):
            bridge.transfer(
                ChainID.ETHEREUM, ChainID.POLYGON, USER, USER,
                999_999 * 10**18  # way more than balance
            )


# ─── Events ───────────────────────────────────────────────────────────────────

class TestBridgeEvents:
    def test_lock_event_logged(self, bridge, eth_token):
        eth_token.mint(USER, 500 * 10**18, caller=MINTER)
        bridge.transfer(ChainID.ETHEREUM, ChainID.POLYGON, USER, USER, 500 * 10**18)

        eth_vault, _ = bridge._chains[ChainID.ETHEREUM]
        assert len(eth_vault.events) == 1
        assert eth_vault.events[0].bridge_nonce == 1

    def test_mint_event_logged_on_relay(self, bridge, eth_token):
        eth_token.mint(USER, 500 * 10**18, caller=MINTER)
        lock_ev = bridge.transfer(ChainID.ETHEREUM, ChainID.POLYGON, USER, USER, 500 * 10**18)
        bridge.complete_transfer(lock_ev)

        assert len(bridge.relayer.events) == 1
        assert bridge.relayer.events[0].bridge_nonce == 1
