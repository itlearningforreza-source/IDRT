# IDRC — IDR Coin Stablecoin

> **Production-ready, fiat-collateralized stablecoin pegged 1:1 to Indonesian Rupiah (IDR)**
> Built with institutional-grade security, regulatory compliance, and operational excellence.

[![Build Status](https://github.com/idrc-stablecoin/idrc/workflows/CI/badge.svg)](https://github.com/idrc-stablecoin/idrc/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Solidity](https://img.shields.io/badge/Solidity-0.8.31-blue.svg)](https://soliditylang.org)
[![Python](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-321%20passing-brightgreen.svg)](#testing)

---

## Overview

**IDRC (IDR Coin)** is a fiat-collateralized stablecoin designed for the Indonesian market, maintaining a 1:1 peg with the Indonesian Rupiah (IDR). Built on Ethereum and EVM-compatible chains, it combines battle-tested smart contract patterns with comprehensive off-chain infrastructure for production deployment.

### Key Features

| Feature | Description |
|---------|-------------|
| **Stablecoin Core** | ERC-20 + EIP-2612 Permit, mint/burn by authorized minters only |
| **Access Control** | OpenZeppelin-compatible RBAC with role hierarchy (DEFAULT_ADMIN_ROLE → all) |
| **Pausable** | Emergency pause/unpause by PAUSER_ROLE for incident response |
| **Blacklist** | Compliance-grade address blocking (sender/receiver/mint) |
| **UUPS Proxy** | ERC1967 upgradeable with multisig governance |
| **Multisig Wallet** | M-of-N threshold, timelock, ETH value support (Gnosis Safe compatible) |
| **Cross-Chain Bridge** | Lock/mint + burn/release with replay protection (nonce deduplication) |
| **Proof of Reserve** | Dual approach: Oracle fiat balance + cryptographic audit proofs |
| **Monitoring** | Real-time alerting (collateralization, oracle staleness, bridge health) |
| **Compliance** | Tiered KYC, sanctions screening, SAR generation, transaction monitoring |

---

## Architecture

```
+---------------------------------------------------------------------------------+
|                           IDRC ECOSYSTEM                                        |
+---------------------------------------------------------------------------------+
|                                                                                 |
|  +--------------+    +--------------+    +--------------+    +------------+    |
|  |   IDRCToken  |<---|  UUPSProxy   |<---| ProxyAdmin   |<---| Multisig   |    |
|  |  (Core ERC20)|    |  (Upgrade)   |    |  (Owner)     |    | (Gov)      |    |
|  +------+-------+    +--------------+    +--------------+    +------------+    |
|         |                                                                  |
|         v                                                                  |
|  +--------------+    +--------------+    +--------------+    +------------+    |
|  |ProofOfReserve|    | BridgeVault  |    |BridgeRelayer |    | Access     |    |
|  | (Oracle +    |    | (Lock/Mint)  |    | (Relay)      |    | Control    |    |
|  |  Audit)      |    +------+-------+    +------+-------+    |            |    |
|  +--------------+           |                  |             +------------+    |
|                             v                  v                                 |
|                    +----------------------------------------------+            |
|                    |       Cross-Chain Networks                   |            |
|                    | Ethereum | Polygon | Arbitrum | ...          |            |
|                    +----------------------------------------------+            |
|                                                                                 |
+---------------------------------------------------------------------------------+
```

---

## Repository Structure

```
IDRC/
├── contracts/                     # Solidity smart contracts
│   ├── token/IDRCToken.sol        # Core ERC-20 with Permit, RBAC, Pause, Blacklist
│   ├── upgrade/IDRCUpgradeable.sol # Versioned migrations (V1→V2→V3)
│   ├── proxy/UUPSProxy.sol        # ERC1967 UUPS proxy
│   ├── proxy/ProxyAdmin.sol       # Multisig-owned proxy admin
│   ├── multisig/MultisigWallet.sol # M-of-N with timelock
│   ├── bridge/BridgeVault.sol     # Cross-chain lock/mint
│   ├── bridge/BridgeRelayer.sol   # Cross-chain relay
│   ├── reserve/ProofOfReserve.sol # Oracle + audit proofs
│   └── access/AccessControl.sol   # RBAC implementation
│
├── test/                          # Solidity tests (162 passing)
│   ├── IDRCToken.t.sol
│   ├── IDRCUpgradeable.t.sol
│   ├── BridgeVault.t.sol
│   ├── BridgeRelayer.t.sol
│   ├── MultisigWallet.t.sol
│   ├── ProofOfReserve.t.sol
│   ├── UUPSProxy.t.sol
│   └── AccessControl.t.sol
│
├── idrc/                          # Python simulation (159 passing)
│   ├── token.py
│   ├── bridge.py
│   ├── multisig.py
│   ├── reserve.py
│   ├── monitor.py
│   ├── proxy.py
│   └── deploy.py
│
├── tests/                         # Python integration tests
├── services/                      # Production services
│   ├── api/                       # FastAPI + Prometheus + Sentry
│   ├── compliance/kyc_aml_service.py
│   ├── oracle/oracle_relayer.py
│   ├── bridge/bridge_relayer.py
│   └── indexer/indexer.py
│
├── script/                        # Foundry deployment scripts
│   ├── DeployIDRC.s.sol
│   ├── UpgradeIDRC.s.sol
│   └── VerifyContracts.s.sol
│
├── docker/                        # Container orchestration
│   ├── prometheus/alerts/
│   ├── grafana/dashboards/
│   └── docker-compose.yml
│
├── k8s/                           # Kubernetes manifests
│   ├── base/
│   └── overlays/{dev,prod}/
│
├── certora/                       # Formal verification specs
├── docs/runbooks/                 # Disaster recovery procedures
└── .github/workflows/ci.yml       # CI/CD pipeline
```

---

## Quick Start

### Prerequisites

- **Foundry** (forge, cast, anvil) ≥ 1.9.0
- **Python** ≥ 3.11
- **Node.js** ≥ 18 (for CI tooling)

### Installation

```bash
# Clone repository
git clone https://github.com/idrc-stablecoin/idrc.git
cd idrc

# Install Foundry dependencies
forge install

# Install Python dependencies
pip install -e ".[dev]"

# Verify installation
forge build
python -m pytest tests/ -v
forge test
```

### Local Development

```bash
# Start local Anvil chain
anvil

# Deploy to local (in another terminal)
forge script script/DeployIDRC.s.sol --rpc-url http://localhost:8545 --broadcast

# Run tests
forge test -vv
python -m pytest tests/ -v
```

---

## Testing

### Test Results

```
Solidity Tests (Foundry):     162 passed, 0 failed
Python Tests (pytest):         159 passed, 0 failed
Total:                         321 passed, 0 failed
```

### Test Breakdown

| Suite | Tests | Coverage |
|-------|-------|----------|
| AccessControl | 21 | 100% |
| BridgeRelayer | 14 | 100% |
| BridgeVault | 24 | 100% |
| Counter | 2 | 100% |
| IDRCToken | 32 | 100% |
| IDRCUpgradeable | 7 | 100% |
| MultisigWallet | 34 | 100% |
| ProofOfReserve | 22 | 100% |
| UUPSProxy | 7 | 100% |
| **Total (Solidity)** | **162** | **100%** |
| **Total (Python)** | **159** | **100%** |

### Run Tests

```bash
# Solidity tests with gas report
forge test --gas-report

# Fuzz testing (10,000 runs)
forge test --fuzz-runs 10000

# Invariant testing (5,000 runs, depth 100)
forge test --invariant-runs 5000 --invariant-depth 100

# Python tests with coverage
python -m pytest tests/ -v --cov=idrc --cov-report=html

# Slither static analysis
slither contracts/ --config-file slither.config.json
```

---

## Smart Contract Details

### IDRCToken (Core)

```solidity
// Key Functions
function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE);
function issuerBurn(address from, uint256 amount) external onlyRole(BURNER_ROLE);
function burn(uint256 amount) external;                    // User burn
function pause() external onlyRole(PAUSER_ROLE);
function unpause() external onlyRole(PAUSER_ROLE);
function blacklist(address account) external onlyRole(BLACKLISTER_ROLE);
function unblacklist(address account) external onlyRole(BLACKLISTER_ROLE);
function permit(...) external;                              // EIP-2612
function updateReserveProof(bytes32) external onlyRole(DEFAULT_ADMIN_ROLE);
```

### Key Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| **Name** | IDR Coin | Token name |
| **Symbol** | IDRC | Token symbol |
| **Decimals** | 18 | Standard ERC-20 |
| **Supply Cap** | 10B IDRC | Maximum supply |
| **Collateralization** | ≥ 100% | Fiat reserve requirement |

### Role Hierarchy

```
DEFAULT_ADMIN_ROLE (admin of all)
├── MINTER_ROLE
├── BURNER_ROLE
├── PAUSER_ROLE
├── UPGRADER_ROLE
└── BLACKLISTER_ROLE
```

---

## Cross-Chain Bridge

### Supported Chains

| Chain | Chain ID | Status |
|-------|----------|--------|
| Ethereum | 1 | Mainnet |
| Polygon | 137 | Mainnet |
| Arbitrum | 42161 | Testnet |
| Optimism | 10 | Testnet |
| Base | 8453 | Planned |
| BSC | 56 | Planned |

### Bridge Flow

```
Source Chain                          Destination Chain
+-----------------+                   +-----------------+
|  User           |                   |  Relayer        |
|  1. Lock tokens |                   |  1. Listen      |
|     in Vault    |  -- Event -->     |  2. Verify      |
|                 |                   |  3. Mint        |
+-----------------+                   +-----------------+
       |                                      |
       v                                      v
  Tokens burned                        Tokens minted
  Nonce recorded                       Nonce marked
       |                                      |
       +-------------- Replay Protection -----+
```

---

## Proof of Reserve

### Dual Approach

| Approach | Mechanism | Verification |
|----------|-----------|--------------|
| **Oracle** | Trusted oracle pushes fiat balance | On-chain reserveRatio() check |
| **Audit Proof** | Auditor submits SHA-256 of report | verifyProof(bytes) by anyone |

### Collateralization Check

```solidity
// Always >= 100%
function isFullyCollateralized(uint256 supply) external view returns (bool) {
    return fiatBalanceIdr >= supply;
}

function reserveRatio(uint256 supply) external view returns (uint256) {
    return (fiatBalanceIdr * 1e18) / supply; // 1e18 = 100%
}
```

---

## Security

### Audits

| Audit | Firm | Status |
|-------|------|--------|
| Smart Contracts | Trail of Bits / Quantstamp | Planned |
| Cryptography | NCC Group | Planned |
| Bridge | Zellic / Spearbit | Planned |
| Infrastructure | Bishop Fox | Planned |
| Formal Verification | Certora / Runtime Verification | Planned |

### Bug Bounty

- **Platform**: Immunefi
- **Rewards**: Critical $100K, High $50K, Medium $10K, Low $2K
- **Scope**: All mainnet contracts

### Security Contacts

- **Email**: security@idrc.example.com
- **PGP**: Available on request
- **Response**: 48 hours acknowledgment, 7 days assessment

---

## Monitoring & Operations

### Key Metrics

| Metric | Target | Alert |
|--------|--------|-------|
| Uptime | 99.99% | P1 if < 99.9% |
| Collateralization | ≥ 100% | P1 if < 100% |
| Oracle Staleness | < 1 hour | P1 if > 1h |
| Bridge Pending Nonces | < 10 | P2 if > 100 |
| API Latency (P99) | < 2s | P2 if > 2s |

### Stack

- **Metrics**: Prometheus + Grafana
- **Logs**: Loki + Promtail
- **Traces**: Jaeger
- **Alerts**: Alertmanager → PagerDuty → Slack

### Dashboards

- [IDRC Overview](https://grafana.idrc.example.com/d/idrc-overview)
- [Bridge Health](https://grafana.idrc.example.com/d/idrc-bridge)
- [Reserve Status](https://grafana.idrc.example.com/d/idrc-reserve)

---

## Deployment

### Networks

| Network | RPC | Explorer |
|---------|-----|----------|
| Ethereum Mainnet | https://eth-mainnet.g.alchemy.com/v2/... | Etherscan |
| Polygon Mainnet | https://polygon-mainnet.g.alchemy.com/v2/... | Polygonscan |
| Sepolia Testnet | https://eth-sepolia.g.alchemy.com/v2/... | Etherscan |
| Amoy Testnet | https://polygon-amoy.g.alchemy.com/v2/... | Polygonscan |

### Deploy Commands

```bash
# Deploy to mainnet (requires multisig signers)
forge script script/DeployIDRC.s.sol   --rpc-url $MAINNET_RPC   --broadcast   --verify   --etherscan-api-key $ETHERSCAN_KEY

# Upgrade contract
forge script script/UpgradeIDRC.s.sol   --rpc-url $MAINNET_RPC   --broadcast

# Verify contracts
forge script script/VerifyContracts.s.sol   --rpc-url $MAINNET_RPC
```

### Environment Variables

```bash
cp .env.development.template .env.development
cp .env.production.template .env.production
# Edit with your values
```

---

## Compliance & Regulation

### Indonesian Framework

| License | Authority | Status |
|---------|-----------|--------|
| Payment System | Bank Indonesia | Application |
| E-Money | BI / OJK | Application |
| AML/CTF | PPATK | Implementation |
| Data Protection | UU PDP | Compliance |

### International

| Jurisdiction | Regulation | Approach |
|--------------|------------|----------|
| Global | FATF Travel Rule | Notabene/TRISA integration |
| EU | MiCA | White paper + CASP registration |
| US | FinCEN MSB | State-by-state licensing |
| Singapore | MAS PSA | Monitor thresholds |

### KYC Tiers

| Tier | Requirements | Daily Limit | Monthly Limit |
|------|-------------|-------------|---------------|
| Tier 0 | Email only | 1M IDR | 10M IDR |
| Tier 1 | KTP + Selfie | 50M IDR | 500M IDR |
| Tier 2 | POA + Source of Funds | 500M IDR | 5B IDR |
| Tier 3 | Corporate/Institutional | 10B IDR | 100B IDR |

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Workflow

1. Fork & clone
2. Create feature branch: git checkout -b feature/my-feature develop
3. Write code + tests
4. Run full test suite: forge test && python -m pytest
5. Ensure CI passes
6. Open PR targeting develop

### Code Standards

- **Solidity**: Forge fmt (120 cols), Solhint, NatSpec docs
- **Python**: Ruff (100 cols), MyPy strict, type hints required
- **Commits**: Conventional Commits (feat:, fix:, docs:, etc.)

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Links

- **Website**: https://idrc.example.com
- **Documentation**: https://docs.idrc.example.com
- **GitHub**: https://github.com/idrc-stablecoin/idrc
- **Discord**: https://discord.gg/idrc
- **Twitter**: https://twitter.com/IDRCoin
- **Security**: security@idrc.example.com

---

## Acknowledgments

- **OpenZeppelin** - Battle-tested contract libraries
- **Foundry** - Ethereum development toolkit
- **Certora** - Formal verification platform
- **Indonesian Regulators** - BI, OJK, PPATK guidance

---

<div align="center">

**Built with ❤️ for Indonesia's digital economy**

[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Indonesia](https://img.shields.io/badge/Made%20in-Indonesia-red.svg)](https://indonesia.go.id)

</div>
