# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | ✅ Yes    |
| < 1.0   | ❌ No     |

---

## Scope

This repository contains a **Python simulation** of the IDRC stablecoin smart contract
logic. It is intended as a reference implementation and test harness — not as
production on-chain code.

Security vulnerabilities in the following areas are in scope:

- Logic errors in token minting, burning, or transfer that could lead to supply
  manipulation.
- Access control bypasses that allow unprivileged callers to invoke privileged
  functions (`mint`, `burn`, `pause`, `blacklist`, upgrades).
- Replay attacks on EIP-2612 permit signatures.
- Bridge nonce deduplication failures enabling double-spend.
- Multisig threshold bypass (executing proposals without reaching quorum).
- Reserve ratio manipulation that could mask under-collateralisation.

**Out of scope** (Python simulation limitations):
- Solidity-specific attack vectors (e.g., reentrancy through EVM call stacks,
  `delegatecall` storage collisions) — these are addressed in the forthcoming
  Solidity implementation.
- Python runtime vulnerabilities.
- Denial of service attacks.

---

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Instead, send a detailed report by email to:

> **security@idrc-stablecoin.example.com**

Include the following in your report:

1. **Description** — a clear explanation of the vulnerability and its impact.
2. **Steps to reproduce** — minimal code or test case demonstrating the issue.
3. **Affected version(s)**.
4. **Suggested fix** (optional but appreciated).

### What to expect

| Timeframe       | Action                                     |
|-----------------|--------------------------------------------|
| Within 48 hours | Acknowledgement of receipt                 |
| Within 7 days   | Initial severity assessment and response   |
| Within 30 days  | Patch released (for critical/high issues)  |
| After patch     | Public disclosure with CVE (if applicable) |

We follow **responsible disclosure** — we will credit reporters in the changelog
and release notes unless you prefer to remain anonymous.

---

## Security Design Principles

This simulation implements the following mitigations (documented here for
transparency):

| Control | Implementation |
|---------|---------------|
| Role-based access control | Every privileged function calls `_access.check_role()` before any state mutation |
| Checks-Effects-Interactions | All state changes occur before any external-style callbacks |
| Replay protection (permits) | Per-owner nonce incremented on each successful `permit()` call |
| Bridge replay protection | Per-chain nonce set tracks processed transfer IDs |
| Multisig quorum | Transactions require ≥ `threshold` distinct approvals before execution |
| Timelock | Optional `timelock_s` delay enforced before multisig execution |
| Upgradeability guard | `authorize_upgrade()` restricted to `UPGRADER_ROLE` (held by multisig) |
| Pause mechanism | `_before_token_transfer` hook rejects all transfers when paused |
| Blacklist | `_before_token_transfer` hook blocks blacklisted addresses |
| Reserve ratio | `check_collateralisation()` raises if fiat < token supply |

---

## Disclosure History

_No vulnerabilities have been disclosed to date._
