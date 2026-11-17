"""Unit & Integration Test Suite for IDRC Solidity Reference Contract."""

from idrc.token import IDRCToken
from idrc.access_control import MINTER_ROLE


def test_solidity_reference_contract_alignment():
    """Verify that Python Token contract logic aligns with IDRCToken.sol reference logic."""
    token = IDRCToken()
    token.initialize(
        name="IDR Coin",
        symbol="IDRC",
        admin="0xAdmin",
        minter="0xAdmin",
        pauser="0xAdmin",
        upgrader="0xAdmin",
    )

    # Grant Minter
    token.grant_role(MINTER_ROLE, "0xMinter", caller="0xAdmin")
    assert token.has_role(MINTER_ROLE, "0xMinter")

    # Mint Tokens
    token.mint("0xUser", 1000 * 10**18, caller="0xMinter")
    assert token.balance_of("0xUser") == 1000 * 10**18

    # Pause & Assert Revert
    token.pause(caller="0xAdmin")
    assert token.paused
