"""
tests/test_erc20.py
===================
Unit tests for ERC20Base (Section 6.1).
Covers: transfer, approve, transferFrom, allowance, mint, burn,
        increaseAllowance, decreaseAllowance, edge cases.
"""

import pytest

from idrc.erc20 import ZERO_ADDRESS, ERC20Base
from idrc.exceptions import (
    InsufficientAllowanceError,
    InsufficientBalanceError,
    ZeroAddressError,
    ZeroAmountError,
)


@pytest.fixture
def token():
    t = ERC20Base("IDR Coin", "IDRC")
    t._mint("Alice", 1_000 * 10**18)
    return t


# ─── Metadata ────────────────────────────────────────────────────────────────

class TestMetadata:
    def test_name(self, token):
        assert token.name == "IDR Coin"

    def test_symbol(self, token):
        assert token.symbol == "IDRC"

    def test_decimals(self, token):
        assert token.decimals == 18

    def test_initial_total_supply(self, token):
        assert token.total_supply == 1_000 * 10**18


# ─── Balance ─────────────────────────────────────────────────────────────────

class TestBalance:
    def test_balance_after_mint(self, token):
        assert token.balance_of("Alice") == 1_000 * 10**18

    def test_zero_balance_for_unknown(self, token):
        assert token.balance_of("Unknown") == 0


# ─── Transfer ────────────────────────────────────────────────────────────────

class TestTransfer:
    def test_valid_transfer(self, token):
        token.transfer("Bob", 500 * 10**18, caller="Alice")
        assert token.balance_of("Alice") == 500 * 10**18
        assert token.balance_of("Bob")   == 500 * 10**18

    def test_full_balance_transfer(self, token):
        token.transfer("Bob", 1_000 * 10**18, caller="Alice")
        assert token.balance_of("Alice") == 0

    def test_transfer_to_zero_address_reverts(self, token):
        with pytest.raises(ZeroAddressError):
            token.transfer(ZERO_ADDRESS, 100, caller="Alice")

    def test_transfer_insufficient_balance_reverts(self, token):
        with pytest.raises(InsufficientBalanceError):
            token.transfer("Bob", 9_999 * 10**18, caller="Alice")

    def test_transfer_zero_amount_reverts(self, token):
        with pytest.raises(ZeroAmountError):
            token.transfer("Bob", 0, caller="Alice")

    def test_transfer_emits_event(self, token):
        token.transfer("Bob", 100, caller="Alice")
        events = [e for e in token.events if hasattr(e, "sender") and e.sender == "Alice"]
        assert len(events) == 1
        assert events[0].amount == 100


# ─── Approve / Allowance ─────────────────────────────────────────────────────

class TestApproval:
    def test_approve_sets_allowance(self, token):
        token.approve("Bob", 500 * 10**18, caller="Alice")
        assert token.allowance("Alice", "Bob") == 500 * 10**18

    def test_approve_overwrites_allowance(self, token):
        token.approve("Bob", 500 * 10**18, caller="Alice")
        token.approve("Bob", 200 * 10**18, caller="Alice")
        assert token.allowance("Alice", "Bob") == 200 * 10**18

    def test_increase_allowance(self, token):
        token.approve("Bob", 100, caller="Alice")
        token.increase_allowance("Bob", 50, caller="Alice")
        assert token.allowance("Alice", "Bob") == 150

    def test_decrease_allowance(self, token):
        token.approve("Bob", 100, caller="Alice")
        token.decrease_allowance("Bob", 30, caller="Alice")
        assert token.allowance("Alice", "Bob") == 70

    def test_decrease_allowance_below_zero_reverts(self, token):
        token.approve("Bob", 50, caller="Alice")
        with pytest.raises(InsufficientAllowanceError):
            token.decrease_allowance("Bob", 100, caller="Alice")

    def test_approve_zero_address_spender_reverts(self, token):
        with pytest.raises(ZeroAddressError):
            token.approve(ZERO_ADDRESS, 100, caller="Alice")


# ─── TransferFrom ─────────────────────────────────────────────────────────────

class TestTransferFrom:
    def test_transfer_from_within_allowance(self, token):
        token.approve("Bob", 300 * 10**18, caller="Alice")
        token.transfer_from("Alice", "Carol", 200 * 10**18, caller="Bob")
        assert token.balance_of("Carol")        == 200 * 10**18
        assert token.allowance("Alice", "Bob")  == 100 * 10**18

    def test_transfer_from_exceeds_allowance_reverts(self, token):
        token.approve("Bob", 100, caller="Alice")
        with pytest.raises(InsufficientAllowanceError):
            token.transfer_from("Alice", "Carol", 200, caller="Bob")

    def test_transfer_from_unlimited_allowance(self, token):
        """2^256-1 allowance should not be decremented."""
        MAX = 2**256 - 1
        token.approve("Bob", MAX, caller="Alice")
        token.transfer_from("Alice", "Carol", 500 * 10**18, caller="Bob")
        assert token.allowance("Alice", "Bob") == MAX


# ─── Mint ────────────────────────────────────────────────────────────────────

class TestMint:
    def test_mint_increases_supply(self):
        t = ERC20Base("T", "T")
        t._mint("Alice", 1000)
        assert t.total_supply == 1000
        assert t.balance_of("Alice") == 1000

    def test_mint_to_zero_address_reverts(self):
        t = ERC20Base("T", "T")
        with pytest.raises(ZeroAddressError):
            t._mint(ZERO_ADDRESS, 1000)

    def test_mint_zero_amount_reverts(self):
        t = ERC20Base("T", "T")
        with pytest.raises(ZeroAmountError):
            t._mint("Alice", 0)


# ─── Burn ────────────────────────────────────────────────────────────────────

class TestBurn:
    def test_burn_reduces_supply(self, token):
        initial = token.total_supply
        token._burn("Alice", 100)
        assert token.total_supply == initial - 100
        assert token.balance_of("Alice") == initial - 100

    def test_burn_more_than_balance_reverts(self, token):
        with pytest.raises(InsufficientBalanceError):
            token._burn("Alice", 99999 * 10**18)

    def test_burn_from_zero_address_reverts(self, token):
        with pytest.raises(ZeroAddressError):
            token._burn(ZERO_ADDRESS, 100)

    def test_burn_zero_amount_reverts(self, token):
        with pytest.raises(ZeroAmountError):
            token._burn("Alice", 0)

    def test_total_supply_invariant(self, token):
        """
        Invariant: total_supply == sum(balance_of(x) for x in all_accounts).
        """
        token._mint("Bob", 500)
        token._burn("Alice", 200)
        holders = {
            "Alice": token.balance_of("Alice"),
            "Bob":   token.balance_of("Bob"),
        }
        assert token.total_supply == sum(holders.values())
