"""
tests/test_deploy.py
====================
Integration tests for the full deployment and upgrade pipeline (Section 7).
Covers: deploy_idrc(), verify_deployment(), upgrade_idrc(), and the
        end-to-end multisig-governed mint/burn lifecycle.
"""

import pytest

from idrc.access_control import (
    BLACKLISTER_ROLE,
    BURNER_ROLE,
    DEFAULT_ADMIN_ROLE,
    MINTER_ROLE,
    PAUSER_ROLE,
    UPGRADER_ROLE,
)
from idrc.deploy import deploy_idrc, upgrade_idrc, verify_deployment
from idrc.exceptions import MissingRoleError
from idrc.token import IDRCToken

# ─── V2 stub for upgrade tests ────────────────────────────────────────────────

class IDRCTokenV2(IDRCToken):
    VERSION: str = "2.0.0"


# ─── Fixtures ────────────────────────────────────────────────────────────────

OWNERS    = ["Alice", "Bob", "Carol", "Dave", "Eve"]
DEPLOYER  = "0xDeployer"
ORACLE    = "0xOracle"


@pytest.fixture
def deployment():
    return deploy_idrc(
        deployer=DEPLOYER,
        multisig_owners=OWNERS,
        multisig_threshold=3,
        reserve_oracle=ORACLE,
        network="testnet",
    )


# ─── Deployment Sanity ───────────────────────────────────────────────────────

class TestDeployment:
    def test_verify_deployment_passes(self, deployment):
        assert verify_deployment(deployment) is True

    def test_initial_supply_is_zero(self, deployment):
        assert deployment.token.total_supply == 0

    def test_token_name_and_symbol(self, deployment):
        assert deployment.token.name == "IDR Coin"
        assert deployment.token.symbol == "IDRC"

    def test_token_decimals(self, deployment):
        assert deployment.token.decimals == 18

    def test_deployer_has_no_admin_role(self, deployment):
        assert not deployment.token.has_role(DEFAULT_ADMIN_ROLE, DEPLOYER)

    def test_deployer_has_no_minter_role(self, deployment):
        assert not deployment.token.has_role(MINTER_ROLE, DEPLOYER)

    def test_multisig_holds_all_roles(self, deployment):
        ms = deployment.multisig_address
        token = deployment.token
        for role in [MINTER_ROLE, BURNER_ROLE, PAUSER_ROLE,
                     UPGRADER_ROLE, BLACKLISTER_ROLE, DEFAULT_ADMIN_ROLE]:
            assert token.has_role(role, ms), f"Multisig missing {role}"

    def test_token_not_paused_at_deployment(self, deployment):
        assert not deployment.token.paused

    def test_reserve_oracle_is_set(self, deployment):
        assert deployment.reserve._oracle == ORACLE

    def test_proxy_admin_owner_is_multisig(self, deployment):
        assert deployment.proxy_admin.owner == deployment.multisig_address


# ─── End-to-End Mint/Burn via Multisig ───────────────────────────────────────

class TestMintBurnLifecycle:
    def test_multisig_mint_then_user_burn(self, deployment):
        """
        Full lifecycle:
        1. Multisig proposes + approves + executes mint to a user.
        2. User burns their own tokens.
        """
        ms      = deployment.multisig
        ms_addr = deployment.multisig_address
        token   = deployment.token
        user    = "0xEndUser"
        amount  = 1_000_000 * 10**18  # 1M IDRC

        # ── Mint via multisig ──
        tx_id = ms.propose(
            "Mint 1M IDRC to user",
            fn=token.mint,
            fn_kwargs={"to": user, "amount": amount, "caller": ms_addr},
            caller="Alice",
        )
        ms.approve(tx_id, caller="Bob")
        ms.approve(tx_id, caller="Carol")
        ms.execute(tx_id, caller="Alice")

        assert token.balance_of(user) == amount
        assert token.total_supply == amount

        # ── User burns half ──
        token.burn(amount // 2, caller=user)
        assert token.balance_of(user) == amount // 2
        assert token.total_supply == amount // 2

    def test_multisig_issuer_burn(self, deployment):
        """Multisig calls issuer_burn after fiat redemption."""
        ms      = deployment.multisig
        ms_addr = deployment.multisig_address
        token   = deployment.token
        user    = "0xRedeemer"
        amount  = 500_000 * 10**18

        # First mint
        tx_mint = ms.propose("Mint", fn=token.mint,
                             fn_kwargs={"to": user, "amount": amount, "caller": ms_addr},
                             caller="Alice")
        ms.approve(tx_mint, caller="Bob")
        ms.approve(tx_mint, caller="Carol")
        ms.execute(tx_mint, caller="Alice")

        # Then issuer_burn after fiat is sent back
        tx_burn = ms.propose("IssuerBurn", fn=token.issuer_burn,
                             fn_kwargs={"from_": user, "amount": amount, "caller": ms_addr},
                             caller="Alice")
        ms.approve(tx_burn, caller="Bob")
        ms.approve(tx_burn, caller="Carol")
        ms.execute(tx_burn, caller="Alice")

        assert token.balance_of(user) == 0
        assert token.total_supply == 0

    def test_multisig_pause_then_unpause(self, deployment):
        """Multisig can pause and unpause transfers."""
        ms      = deployment.multisig
        ms_addr = deployment.multisig_address
        token   = deployment.token

        # Pause
        tx_id = ms.propose("Pause", fn=token.pause,
                           fn_kwargs={"caller": ms_addr}, caller="Alice")
        ms.approve(tx_id, caller="Bob")
        ms.approve(tx_id, caller="Carol")
        ms.execute(tx_id, caller="Alice")
        assert token.paused

        # Unpause
        tx_id2 = ms.propose("Unpause", fn=token.unpause,
                            fn_kwargs={"caller": ms_addr}, caller="Alice")
        ms.approve(tx_id2, caller="Bob")
        ms.approve(tx_id2, caller="Carol")
        ms.execute(tx_id2, caller="Alice")
        assert not token.paused

    def test_random_account_cannot_mint(self, deployment):
        with pytest.raises(MissingRoleError):
            deployment.token.mint("0xRandom", 1000, caller="0xRandom")


# ─── Upgrade Integration ──────────────────────────────────────────────────────

class TestUpgradeIntegration:
    def test_upgrade_preserves_all_balances(self, deployment):
        """After a UUPS upgrade, all user balances remain intact."""
        ms      = deployment.multisig
        ms_addr = deployment.multisig_address
        token   = deployment.token
        users   = [f"0xUser{i}" for i in range(5)]
        amount  = 100_000 * 10**18

        for user in users:
            tx = ms.propose(f"Mint to {user}", fn=token.mint,
                            fn_kwargs={"to": user, "amount": amount, "caller": ms_addr},
                            caller="Alice")
            ms.approve(tx, caller="Bob")
            ms.approve(tx, caller="Carol")
            ms.execute(tx, caller="Alice")

        total_before = token.total_supply
        balances_before = {u: token.balance_of(u) for u in users}

        # Upgrade
        upgrade_idrc(deployment, IDRCTokenV2, upgrader=ms_addr)

        token_v2 = deployment.token
        assert token_v2.total_supply == total_before
        for user in users:
            assert token_v2.balance_of(user) == balances_before[user]

    def test_non_upgrader_cannot_upgrade(self, deployment):
        from idrc.exceptions import UpgradeError
        with pytest.raises(UpgradeError):
            upgrade_idrc(deployment, IDRCTokenV2, upgrader="0xEvil")


# ─── Reserve Integration ──────────────────────────────────────────────────────

class TestReserveIntegration:
    def test_reserve_collateralisation_after_mint(self, deployment):
        """After minting, fiat oracle must show ≥ 1:1 ratio."""
        ms      = deployment.multisig
        ms_addr = deployment.multisig_address
        token   = deployment.token
        amount  = 1_000_000 * 10**18

        # Mint
        tx = ms.propose("Mint", fn=token.mint,
                        fn_kwargs={"to": "0xUser", "amount": amount, "caller": ms_addr},
                        caller="Alice")
        ms.approve(tx, caller="Bob")
        ms.approve(tx, caller="Carol")
        ms.execute(tx, caller="Alice")

        # Oracle reports fiat balance = minted amount (fully backed)
        deployment.reserve.update_fiat_balance(amount, caller=ORACLE)
        assert deployment.reserve.is_fully_collateralised(token.total_supply)
