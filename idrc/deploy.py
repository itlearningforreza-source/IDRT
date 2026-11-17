"""
idrc/deploy.py
==============
Deployment and upgrade scripts (Section 7 of the design document).

Simulates the Hardhat deployment scripts in Python.

Functions
---------
deploy_idrc(...)     - full deployment: token + proxy + admin + multisig + reserve
upgrade_idrc(...)    - upgrade the token implementation via UUPS proxy
verify_deployment(…) - post-deployment sanity checks
print_deployment_summary(result) - pretty-print all deployed addresses
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .access_control import (
    BLACKLISTER_ROLE,
    BURNER_ROLE,
    DEFAULT_ADMIN_ROLE,
    MINTER_ROLE,
    PAUSER_ROLE,
    UPGRADER_ROLE,
)
from .multisig import MultisigWallet
from .proxy import ProxyAdmin, UUPSProxy
from .reserve import IDRCReserve
from .token import IDRCToken

# ─── Deployment Result ────────────────────────────────────────────────────────

@dataclass
class DeploymentResult:
    """Holds references to all deployed contracts (mirrors Ethereum addresses)."""
    proxy: UUPSProxy
    token: Any          # _TokenHandle (delegate-call handle)
    proxy_admin: ProxyAdmin
    multisig: MultisigWallet
    reserve: IDRCReserve
    deployer: str
    multisig_address: str  # logical "address" for the multisig

    # Addresses (simulated as descriptive strings for readability)
    proxy_address: str = "proxy:IDRCToken"
    impl_address: str = "impl:IDRCTokenV1"


# ─── Main Deploy ─────────────────────────────────────────────────────────────

def deploy_idrc(
    deployer: str,
    multisig_owners: list,
    multisig_threshold: int = 3,
    reserve_oracle: str | None = None,
    token_name: str = "IDR Coin",
    token_symbol: str = "IDRC",
    timelock_seconds: int = 0,
    network: str = "testnet",
) -> DeploymentResult:
    """
    Full IDRC deployment pipeline.

    Steps (mirrors Hardhat deploy script, Section 7.2):
    1. Deploy MultisigWallet
    2. Deploy IDRCToken implementation
    3. Deploy UUPSProxy pointing to implementation
    4. Initialize proxy (name, symbol, all roles → multisig)
    5. Deploy ProxyAdmin owned by multisig
    6. Deploy IDRCReserve
    7. Verify all roles are correctly set
    8. Print summary

    Parameters
    ----------
    deployer          : Address of the deploying EOA (temporary admin)
    multisig_owners   : List of addresses for the multisig wallet
    multisig_threshold: Minimum approvals required
    reserve_oracle    : Address of the trusted Chainlink-style oracle
    """
    print(f"\n{'='*60}")
    print(f"  IDRC Deployment — Network: {network.upper()}")
    print(f"{'='*60}")

    # ── Step 1: Multisig ──────────────────────────────────────────────────────
    print("\n[1/6] Deploying MultisigWallet …")
    multisig = MultisigWallet(
        owners=multisig_owners,
        threshold=multisig_threshold,
        timelock_s=timelock_seconds,
    )
    # Use a deterministic "address" for display
    ms_addr = "multisig:" + hashlib.sha256(
        ",".join(sorted(multisig_owners)).encode()
    ).hexdigest()[:20]
    print(f"      MultisigWallet deployed → {ms_addr}")
    print(f"      Owners: {multisig_owners}")
    print(f"      Threshold: {multisig_threshold}-of-{len(multisig_owners)}")

    # ── Step 2: Token Implementation ─────────────────────────────────────────
    print("\n[2/6] Deploying IDRCToken implementation …")
    impl_v1 = IDRCToken()
    impl_addr = f"impl:{impl_v1.__class__.__name__}V{IDRCToken.VERSION}"
    print(f"      Implementation deployed → {impl_addr}")

    # ── Step 3: Proxy ─────────────────────────────────────────────────────────
    print("\n[3/6] Deploying UUPS Proxy …")
    proxy = UUPSProxy(impl_v1)
    proxy_addr = "proxy:IDRCToken"
    print(f"      Proxy deployed → {proxy_addr}")

    # ── Step 4: Initialize ────────────────────────────────────────────────────
    print("\n[4/6] Initializing proxy …")
    token = proxy.as_token()
    token.initialize(
        name=token_name,
        symbol=token_symbol,
        admin=deployer,          # temporary; will be transferred to multisig
        minter=deployer,
        pauser=deployer,
        upgrader=deployer,
        burner=deployer,
        blacklister=deployer,
    )
    print(f"      Token name  : {token_name}")
    print(f"      Token symbol: {token_symbol}")

    # ── Step 4b: Transfer all roles to multisig ───────────────────────────────
    print("\n      Transferring all roles to multisig …")
    for role in [MINTER_ROLE, BURNER_ROLE, PAUSER_ROLE, UPGRADER_ROLE, BLACKLISTER_ROLE]:
        token.grant_role(role, ms_addr, caller=deployer)
        token.revoke_role(role, deployer, caller=deployer)
    # Grant DEFAULT_ADMIN_ROLE to multisig, then renounce deployer's admin
    token.grant_role(DEFAULT_ADMIN_ROLE, ms_addr, caller=deployer)
    token.revoke_role(DEFAULT_ADMIN_ROLE, deployer, caller=deployer)
    print("      All roles transferred ✓")

    # ── Step 5: ProxyAdmin ────────────────────────────────────────────────────
    print("\n[5/6] Deploying ProxyAdmin …")
    proxy_admin = ProxyAdmin(owner=ms_addr)
    proxy_admin.register_proxy("IDRCToken", proxy)
    print(f"      ProxyAdmin deployed → owner={ms_addr}")

    # ── Step 6: Reserve ───────────────────────────────────────────────────────
    print("\n[6/6] Deploying IDRCReserve …")
    reserve = IDRCReserve(admin=ms_addr, oracle=reserve_oracle)
    print(f"      IDRCReserve deployed → admin={ms_addr}, oracle={reserve_oracle}")

    # ── Summary ───────────────────────────────────────────────────────────────
    result = DeploymentResult(
        proxy=proxy,
        token=token,
        proxy_admin=proxy_admin,
        multisig=multisig,
        reserve=reserve,
        deployer=deployer,
        multisig_address=ms_addr,
        proxy_address=proxy_addr,
        impl_address=impl_addr,
    )
    print_deployment_summary(result)
    return result


# ─── Upgrade ─────────────────────────────────────────────────────────────────

def upgrade_idrc(
    deployment: DeploymentResult,
    new_impl_class: type,
    upgrader: str,
) -> None:
    """
    Upgrade the token implementation via UUPS proxy (Section 9.2).

    Steps:
    1. Deploy new implementation.
    2. Call proxy.upgrade_to(new_impl, caller=upgrader).
    3. Print confirmation.
    """
    print(f"\n{'='*60}")
    print(f"  IDRC Upgrade → {new_impl_class.__name__}")
    print(f"{'='*60}")

    new_impl = new_impl_class()
    old_addr = deployment.proxy.implementation_address
    deployment.proxy.upgrade_to(new_impl, caller=upgrader)
    new_addr = deployment.proxy.implementation_address

    # Refresh the token handle to point to the new implementation
    deployment.token = deployment.proxy.as_token()

    print(f"\n  Old implementation: {old_addr}")
    print(f"  New implementation: {new_addr}")
    print(f"  Upgraded by:        {upgrader}")
    print("\n  ✓ Upgrade successful")
    print("\n  Implementation history:")
    for h in deployment.proxy.implementation_history:
        print(f"    → {h}")


# ─── Verification ─────────────────────────────────────────────────────────────

def verify_deployment(result: DeploymentResult) -> bool:
    """
    Post-deployment sanity checks (equivalent to running hardhat verify).
    Returns True if all checks pass.
    """
    print(f"\n{'='*60}")
    print("  Deployment Verification")
    print(f"{'='*60}\n")
    token = result.token
    ms = result.multisig_address
    checks = []

    def check(name: str, condition: bool) -> None:
        status = "✓ PASS" if condition else "✗ FAIL"
        print(f"  {status}  {name}")
        checks.append(condition)

    check("Token name is 'IDR Coin'",            token.name == "IDR Coin")
    check("Token symbol is 'IDRC'",               token.symbol == "IDRC")
    check("Token decimals is 18",                 token.decimals == 18)
    check("Initial total supply is 0",            token.total_supply == 0)
    check("Not paused at deployment",             not token.paused)
    check("Multisig holds MINTER_ROLE",          token.has_role(MINTER_ROLE, ms))
    check("Multisig holds BURNER_ROLE",          token.has_role(BURNER_ROLE, ms))
    check("Multisig holds PAUSER_ROLE",          token.has_role(PAUSER_ROLE, ms))
    check("Multisig holds UPGRADER_ROLE",        token.has_role(UPGRADER_ROLE, ms))
    check("Multisig holds BLACKLISTER_ROLE",     token.has_role(BLACKLISTER_ROLE, ms))
    check("Multisig holds DEFAULT_ADMIN_ROLE",   token.has_role(DEFAULT_ADMIN_ROLE, ms))
    check("Deployer no longer has MINTER_ROLE",
          not token.has_role(MINTER_ROLE, result.deployer))
    check("Deployer no longer has admin role",
          not token.has_role(DEFAULT_ADMIN_ROLE, result.deployer))

    all_pass = all(checks)
    print(f"\n  {'All checks passed ✓' if all_pass else 'Some checks FAILED ✗'}")
    print(f"  ({sum(checks)}/{len(checks)} checks passed)\n")
    return all_pass


# ─── Pretty Printer ───────────────────────────────────────────────────────────

def print_deployment_summary(result: DeploymentResult) -> None:
    print(f"\n{'─'*60}")
    print("  Deployment Summary")
    print(f"{'─'*60}")
    print(f"  Proxy Address    : {result.proxy_address}")
    print(f"  Implementation   : {result.impl_address}")
    print(f"  ProxyAdmin Owner : {result.proxy_admin.owner}")
    print(f"  Multisig Address : {result.multisig_address}")
    print(f"  Multisig Config  : {result.multisig.threshold}-of-{len(result.multisig.owners)}")
    print(f"  Reserve Oracle   : {result.reserve._oracle}")
    print(f"{'─'*60}\n")
