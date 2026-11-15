# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Solidity implementation using OpenZeppelin v5
- External security audit (Trail of Bits / Quantstamp)
- Testnet deployment (Sepolia + Mumbai)

---

## [1.0.0] — 2026-08-31

### Added
- **`idrc.erc20`** — `ERC20Base`: full ERC-20 implementation (balances, transfer,
  approve, allowance, increase/decrease allowance, internal `_mint`/`_burn`/`_transfer`).
- **`idrc.erc20`** — EIP-2612 Permit (`permit()`, `generate_permit_signature()`).
- **`idrc.access_control`** — `AccessControl`: role-based permission system mirroring
  OpenZeppelin's `AccessControl` (grant, revoke, renounce, check roles).
- **`idrc.token`** — `IDRCToken`: main stablecoin composing ERC-20, RBAC, Pausable,
  Blacklist, UUPS upgradeability guard, and reserve proof.
- **`idrc.reserve`** — `IDRCReserve`: proof-of-reserve module supporting:
  - Approach A: off-chain audit hash (SHA-256 of auditor PDF).
  - Approach B: oracle-pushed fiat balance with collateralisation ratio check.
- **`idrc.proxy`** — `UUPSProxy` + `ProxyAdmin`: UUPS upgrade pattern with full
  implementation history tracking.
- **`idrc.multisig`** — `MultisigWallet`: M-of-N multisig with optional timelock,
  modelling Gnosis Safe behaviour (propose → approve → execute).
- **`idrc.deploy`** — `deploy_idrc()`, `upgrade_idrc()`, `verify_deployment()`:
  full deployment pipeline with post-deployment sanity checks.
- **`idrc.monitor`** — `IDRCMonitor`: on-chain event indexer and alert engine
  (large-mint alert, supply-cap alert, oracle-staleness alert, under-collateralisation,
  blacklist actions).
- **`idrc.bridge`** — `IDRCBridge` + `BridgeVault` + `BridgeRelayer`: burn-and-mint
  cross-chain bridge supporting Ethereum, Polygon, BSC, Arbitrum, Optimism.
- **`idrc.exceptions`** — Typed exception hierarchy mirroring Solidity `revert` semantics.
- **158 unit + integration tests** — 100 % pass rate, zero external dependencies.
- **`pyproject.toml`** — PEP 517/518 packaging, pytest, coverage, mypy, ruff config.
- **`py.typed`** — PEP 561 inline type annotations marker.
- **`CHANGELOG.md`**, **`CONTRIBUTING.md`**, **`SECURITY.md`**, **`LICENSE`** (MIT).
- **`.github/workflows/ci.yml`** — GitHub Actions CI on every push/PR.

[Unreleased]: https://github.com/idrc-stablecoin/idrc-python/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/idrc-stablecoin/idrc-python/releases/tag/v1.0.0
