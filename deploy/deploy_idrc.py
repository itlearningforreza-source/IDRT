#!/usr/bin/env python3
"""
IDRC Deployment Script
=======================
Automated deployment pipeline for IDR Coin (IDRC) stablecoin system.
This script simulates the full deployment: Token Implementation -> Proxy -> Multisig -> ProxyAdmin -> Reserve.
"""

import json
import os
from dataclasses import dataclass, asdict
from typing import List
from datetime import datetime, timezone

from idrc.token import IDRCToken
from idrc.proxy import UUPSProxy, ProxyAdmin
from idrc.multisig import MultisigWallet
from idrc.reserve import IDRCReserve
from idrc.access_control import (
    DEFAULT_ADMIN_ROLE,
    MINTER_ROLE,
    PAUSER_ROLE,
    UPGRADER_ROLE,
    BURNER_ROLE,
    BLACKLISTER_ROLE,
)


@dataclass
class DeploymentRecord:
    """Stores the complete deployment state for verification and audit."""
    network: str
    deployer: str
    timestamp: str
    token_implementation_address: str
    proxy_address: str
    proxy_admin_address: str
    multisig_address: str
    reserve_address: str
    roles: dict
    token_name: str
    token_symbol: str
    token_decimals: int
    supply_cap: int


class IDRCDeployer:
    """Orchestrates the full IDRC deployment pipeline."""

    def __init__(self, deployer: str, network: str = "testnet"):
        self.deployer = deployer
        self.network = network
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def deploy(self,
               multisig_owners: List[str],
               multisig_threshold: int,
               reserve_oracle: str,
               token_name: str = "IDR Coin",
               token_symbol: str = "IDRC",
               token_decimals: int = 18) -> DeploymentRecord:

        print(f"🚀 Starting IDRC Deployment on {self.network}...")
        print(f"   Deployer: {self.deployer}")
        print(f"   Timestamp: {self.timestamp}")

        # 1. Deploy Token Implementation (Logic Contract)
        print("\n📦 Step 1: Deploying Token Implementation (IDRCToken)...")
        token_impl = IDRCToken()
        token_impl_addr = f"0xTokenImpl{hash(token_name) & 0xFFFFFFFF:08x}"
        print(f"   ✅ Token Implementation deployed at: {token_impl_addr}")

        # 2. Deploy Multisig Wallet (Governance)
        print("\n👥 Step 2: Deploying Multisig Wallet (Gnosis Safe simulation)...")
        multisig = MultisigWallet(
            owners=multisig_owners,
            threshold=multisig_threshold,
            timelock_s=0
        )
        multisig_addr = f"0xMultiSig{hash(tuple(multisig_owners)) & 0xFFFFFFFF:08x}"
        print(f"   ✅ Multisig deployed at: {multisig_addr}")
        print(f"   Owners: {multisig_owners}")
        print(f"   Threshold: {multisig_threshold}/{len(multisig_owners)}")

        # 3. Deploy Proxy Admin (Owner: Multisig)
        print("\n🔐 Step 3: Deploying ProxyAdmin (Owner: Multisig)...")
        proxy_admin = ProxyAdmin(owner=multisig_addr)
        proxy_admin_addr = f"0xProxyAdmin{hash(multisig_addr) & 0xFFFFFFFF:08x}"
        print(f"   ✅ ProxyAdmin deployed at: {proxy_admin_addr}")

        # 4. Deploy UUPS Proxy (Points to Token Implementation, Admin: ProxyAdmin)
        print("\n🔗 Step 4: Deploying UUPS Proxy...")
        proxy = UUPSProxy(initial_implementation=token_impl)
        proxy_addr = f"0xProxy{hash(token_impl_addr) & 0xFFFFFFFF:08x}"
        print(f"   ✅ Proxy deployed at: {proxy_addr}")

        # 5. Initialize Token via Proxy (Transparent Upgradeable Pattern)
        print("\n⚙️  Step 5: Initializing Token through Proxy...")
        # In production, this would be: proxy.initialize(...)
        # Here we simulate by initializing the implementation directly
        token_impl.initialize(
            name=token_name,
            symbol=token_symbol,
            admin=multisig_addr,      # DEFAULT_ADMIN_ROLE -> Multisig
            minter=multisig_addr,     # MINTER_ROLE -> Multisig
            pauser=multisig_addr,     # PAUSER_ROLE -> Multisig
            upgrader=multisig_addr,   # UPGRADER_ROLE -> Multisig
            burner=multisig_addr,     # BURNER_ROLE -> Multisig
            blacklister=multisig_addr # BLACKLISTER_ROLE -> Multisig
        )
        print(f"   ✅ Token initialized: {token_name} ({token_symbol})")
        print(f"   All roles granted to Multisig: {multisig_addr}")

        # 6. Deploy Proof of Reserve
        print("\n🏦 Step 6: Deploying Proof of Reserve Contract...")
        reserve = IDRCReserve(
            admin=multisig_addr,
            oracle=reserve_oracle
        )
        reserve_addr = f"0xReserve{hash(reserve_oracle) & 0xFFFFFFFF:08x}"
        print(f"   ✅ Proof of Reserve deployed at: {reserve_addr}")
        print(f"   Oracle: {reserve_oracle}")

        # Build Deployment Record
        record = DeploymentRecord(
            network=self.network,
            deployer=self.deployer,
            timestamp=self.timestamp,
            token_implementation_address=token_impl_addr,
            proxy_address=proxy_addr,
            proxy_admin_address=proxy_admin_addr,
            multisig_address=multisig_addr,
            reserve_address=reserve_addr,
            roles={
                "DEFAULT_ADMIN_ROLE": multisig_addr,
                "MINTER_ROLE": multisig_addr,
                "PAUSER_ROLE": multisig_addr,
                "UPGRADER_ROLE": multisig_addr,
                "BURNER_ROLE": multisig_addr,
                "BLACKLISTER_ROLE": multisig_addr,
            },
            token_name=token_name,
            token_symbol=token_symbol,
            token_decimals=token_decimals,
            supply_cap=token_impl._supply_cap
        )

        print("\n🎉 Deployment Complete!")
        self._save_deployment(record)
        return record

    def _save_deployment(self, record: DeploymentRecord) -> None:
        """Save deployment record to JSON file."""
        os.makedirs("deployments", exist_ok=True)
        filename = f"deployments/deployment_{self.network}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w") as f:
            json.dump(asdict(record), f, indent=2)
        print(f"💾 Deployment record saved to: {filename}")


def verify_deployment(record: DeploymentRecord) -> bool:
    """Verify deployment integrity."""
    print("\n🔍 Verifying Deployment...")

    checks = [
        ("Token Implementation", record.token_implementation_address.startswith("0x")),
        ("Proxy Address", record.proxy_address.startswith("0x")),
        ("ProxyAdmin Address", record.proxy_admin_address.startswith("0x")),
        ("Multisig Address", record.multisig_address.startswith("0x")),
        ("Reserve Address", record.reserve_address.startswith("0x")),
        ("Admin Role is Multisig", record.roles["DEFAULT_ADMIN_ROLE"] == record.multisig_address),
        ("Minter Role is Multisig", record.roles["MINTER_ROLE"] == record.multisig_address),
        ("Token Name", record.token_name == "IDR Coin"),
        ("Token Symbol", record.token_symbol == "IDRC"),
        ("Decimals", record.token_decimals == 18),
    ]

    all_passed = True
    for name, check in checks:
        status = "✅" if check else "❌"
        print(f"   {status} {name}: {check}")
        if not check:
            all_passed = False

    if all_passed:
        print("\n✅ All verification checks PASSED!")
    else:
        print("\n❌ Some verification checks FAILED!")

    return all_passed


# CLI Entry Point
if __name__ == "__main__":
    import sys

    # Default configuration for quick testing
    DEPLOYER = "0xDeployerAddress123456789012345678901234567890"
    NETWORK = "testnet"
    MULTISIG_OWNERS = [
        "0xAlice111111111111111111111111111111111111111",
        "0xBob222222222222222222222222222222222222222",
        "0xCarol333333333333333333333333333333333333333",
        "0xDave444444444444444444444444444444444444444",
        "0xEve555555555555555555555555555555555555555",
    ]
    MULTISIG_THRESHOLD = 3
    RESERVE_ORACLE = "0xOracleAddress12345678901234567890123456789012"

    print("=" * 60)
    print("  IDR COIN (IDRC) DEPLOYMENT PIPELINE")
    print("=" * 60)

    deployer = IDRCDeployer(deployer=DEPLOYER, network=NETWORK)
    record = deployer.deploy(
        multisig_owners=MULTISIG_OWNERS,
        multisig_threshold=MULTISIG_THRESHOLD,
        reserve_oracle=RESERVE_ORACLE
    )

    success = verify_deployment(record)
    sys.exit(0 if success else 1)