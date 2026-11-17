"""
tests/test_permit.py
====================
Unit tests for EIP-2612 Permit functionality (Section 4.4 & 4.1).
Covers: valid permit, expired deadline, invalid signature, nonce increment.
"""

import time

import pytest

from idrc.exceptions import PermitError, PermitExpiredError
from idrc.token import IDRCToken


@pytest.fixture
def token():
    t = IDRCToken()
    t.initialize(
        name="IDR Coin",
        symbol="IDRC",
        admin="0xAdmin",
        minter="0xMinter",
        pauser="0xPauser",
        upgrader="0xUpgrader",
    )
    return t


@pytest.fixture
def funded_token(token):
    token.mint("0xOwner", 1_000 * 10**18, caller="0xMinter")
    return token


class TestPermit:
    def test_permit_sets_allowance(self, funded_token):
        """A valid permit signature grants allowance without a gas transaction."""
        owner   = "0xOwner"
        spender = "0xSpender"
        value   = 500 * 10**18
        deadline = int(time.time()) + 3600  # 1 hour from now

        sig = funded_token.generate_permit_signature(owner, spender, value, deadline)
        funded_token.permit(owner, spender, value, deadline, sig)

        assert funded_token.allowance(owner, spender) == value

    def test_permit_expired_deadline_reverts(self, funded_token):
        """Permit with a past deadline must revert."""
        owner    = "0xOwner"
        spender  = "0xSpender"
        value    = 100 * 10**18
        deadline = int(time.time()) - 1  # already expired

        sig = funded_token.generate_permit_signature(owner, spender, value, deadline)
        with pytest.raises(PermitExpiredError):
            funded_token.permit(owner, spender, value, deadline, sig)

    def test_permit_invalid_signature_reverts(self, funded_token):
        """Tampered signature must revert."""
        owner    = "0xOwner"
        spender  = "0xSpender"
        value    = 100 * 10**18
        deadline = int(time.time()) + 3600

        with pytest.raises(PermitError):
            funded_token.permit(owner, spender, value, deadline, "bad_signature_hex")

    def test_permit_nonce_increments(self, funded_token):
        """Each successful permit increments the owner's nonce."""
        owner    = "0xOwner"
        spender  = "0xSpender"
        deadline = int(time.time()) + 3600

        assert funded_token.nonce_of(owner) == 0

        sig = funded_token.generate_permit_signature(owner, spender, 100, deadline)
        funded_token.permit(owner, spender, 100, deadline, sig)

        assert funded_token.nonce_of(owner) == 1

    def test_permit_replay_attack_fails(self, funded_token):
        """Re-using a consumed permit signature must fail (nonce changed)."""
        owner    = "0xOwner"
        spender  = "0xSpender"
        value    = 100 * 10**18
        deadline = int(time.time()) + 3600

        sig = funded_token.generate_permit_signature(owner, spender, value, deadline)
        funded_token.permit(owner, spender, value, deadline, sig)

        # Replay attempt: same sig, nonce is now stale
        with pytest.raises(PermitError):
            funded_token.permit(owner, spender, value, deadline, sig)

    def test_permit_then_transfer_from(self, funded_token):
        """After permit, spender can transferFrom without prior on-chain approve."""
        owner    = "0xOwner"
        spender  = "0xSpender"
        recipient = "0xRecipient"
        value    = 200 * 10**18
        deadline = int(time.time()) + 3600

        sig = funded_token.generate_permit_signature(owner, spender, value, deadline)
        funded_token.permit(owner, spender, value, deadline, sig)

        funded_token.transfer_from(owner, recipient, value, caller=spender)
        assert funded_token.balance_of(recipient) == value
        assert funded_token.allowance(owner, spender) == 0
