# SECURITY_FINDINGS.md
# IDRT Security Findings Register
**Date:** 2026-11-18
**Phase:** 0 - Repository Forensics
**Classification:** CONFIDENTIAL - Internal Security Assessment
**Total Findings:** 63 (12 Critical, 15 High, 18 Medium, 10 Low, 8 Informational)

---

## FINDING FORMAT

Each finding includes:
- **Finding ID:** Unique identifier
- **Severity:** Critical/High/Medium/Low/Informational
- **Component:** Affected contract/service/file
- **Location:** File and line numbers
- **Technical Description:** Root cause analysis
- **Exploit/Failure Scenario:** How it can be abused
- **Business Impact:** Financial, reputational, regulatory
- **Remediation:** Specific fix required
- **Verification:** How to confirm fix
- **Status:** Open/In Progress/Fixed/Verified

---

## CRITICAL FINDINGS (12)

### FIND-001: Missing Low-S Signature Enforcement in EIP-2612 Permit
| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Component** | IDRCToken.sol |
| **Location** | Line 307-326 (permit function) |
| **Technical Description** | The `permit` function uses `ecrecover` directly without enforcing that the `s` value is in the lower half of the curve order (secp256k1n/2). This allows signature malleability where a valid signature can be transformed into another valid signature. |
| **Exploit Scenario** | Attacker observes a valid permit signature, flips `s` to `n-s`, submits modified permit. Both signatures recover the same address. Can cause nonce confusion, replay attacks on off-chain systems tracking permits. |
| **Business Impact** | Violates EIP-2612 specification. Permit signatures not universally compatible. Potential for front-running permit transactions. |
| **Remediation** | Add low-s check: `require(s <= 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0, "low-s");` |
| **Verification** | Test with both high-s and low-s signatures; high-s should revert |
| **Status** | Open |

### FIND-002: Domain Separator Vulnerable to Re-initialization
| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Component** | IDRCToken.sol |
| **Location** | Line 112-126 (initialize function) |
| **Technical Description** | `_domainSeparator` is computed from `name_` parameter. If `initialize` is called twice (possible on proxy upgrade with new implementation), the domain separator changes, invalidating all existing permits and enabling replay across versions. |
| **Exploit Scenario** | 1. User signs permit with v1 domain separator. 2. Contract upgraded, re-initialized with different name. 3. Attacker replays old permit - different domain separator means different hash, but if name unchanged, same separator. If name changes, old permits break. |
| **Business Impact** | Permit invalidation on upgrades. Potential replay if domain separator reused. |
| **Remediation** | 1. Make `initialize` only callable once (use `initializer` modifier correctly). 2. Store name/hash in immutable storage. 3. Add version to domain separator. |
| **Verification** | Attempt double initialization; verify permits work across upgrades |
| **Status** | Open |

### FIND-003: Custom AccessControl Replaces Battle-Tested OpenZeppelin
| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Component** | AccessControl.sol |
| **Location** | Entire file (123 lines) |
| **Technical Description** | Full reimplementation of OpenZeppelin AccessControl instead of inheriting from `@openzeppelin/contracts/access/AccessControl.sol`. Missing critical features: `getRoleMember`, `getRoleMemberCount`, `AccessControlDefaultAdminRules`, proper event indexing. |
| **Exploit Scenario** | 1. Admin cannot enumerate role members for audits. 2. No protection against admin renouncing DEFAULT_ADMIN_ROLE. 3. Custom bugs in role granting/revoking logic. 4. Incompatible with tooling expecting OZ interface. |
| **Business Impact** | Unaudited code in critical authorization path. Compliance auditors will flag. Tooling integration broken. |
| **Remediation** | Replace with `import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";` and inherit. Remove custom file. |
| **Verification** | Slither analysis; test all role operations; verify OZ compatibility |
| **Status** | Open |

### FIND-004: updateFiatBalance Accepts Zero Amount
| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Component** | ProofOfReserve.sol |
| **Location** | Line 111-121 (updateFiatBalance), Test line 89-94 |
| **Technical Description** | `updateFiatBalance` allows setting fiat balance to 0. Test `testUpdateFiatBalanceZeroAmount` confirms this is accepted. No validation that balance > 0. |
| **Exploit Scenario** | Oracle (compromised or malicious) sets balance to 0. `isFullyCollateralised` returns false for any supply > 0. Triggers false insolvency alerts. Could be used to manipulate reserve ratio for arbitrage. |
| **Business Impact** | False insolvency signals. Reserve ratio manipulation. Loss of confidence. |
| **Remediation** | Add `require(newBalanceIdr > 0, "ZeroBalance");` or `require(newBalanceIdr >= MIN_RESERVE_THRESHOLD);` |
| **Verification** | Test zero amount reverts; test valid amounts work |
| **Status** | Open |

### FIND-005: verifyProof Always Returns True (Placeholder)
| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Component** | ProofOfReserve.sol |
| **Location** | Line 192-198 (verifyProof function) |
| **Technical Description** | `verifyProof` function is a stub that returns `true` without any verification logic. The function signature suggests it should verify report data against stored proof hash. |
| **Exploit Scenario** | Anyone can call `verifyProof` with arbitrary data and get `true`. False sense of verification. Audit reports cannot be cryptographically verified on-chain. |
| **Business Impact** | "Verified" reserve proofs are meaningless. Regulatory non-compliance. Misleading transparency claims. |
| **Remediation** | Implement actual verification: `return keccak256(reportData) == _latestProofHash;` |
| **Verification** | Test with matching and non-matching report data |
| **Status** | Open |

### FIND-006: Oracle Single Point of Failure - No Attestation
| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Component** | ProofOfReserve.sol, OracleRelayer |
| **Location** | ProofOfReserve line 111-121; OracleRelayer line 40-50 |
| **Technical Description** | Single oracle key controls fiat balance updates. OracleRelayer uses `BankCustodianClient` that returns **random numbers** (line 47-50). No cryptographic attestation from bank (no signatures, certificates, or BI-FAST integration). |
| **Exploit Scenario** | 1. Oracle key compromised → attacker sets arbitrary balance. 2. Bank API compromised → false balance pushed. 3. Oracle service hacked → balance manipulation. No way to detect fraudulent update. |
| **Business Impact** | Complete reserve data compromise. False collateralization. Regulatory violation (no independent verification). |
| **Remediation** | 1. Multi-oracle threshold signatures. 2. Bank-signed attestations (PKI). 3. TEE/HSM for oracle keys. 4. Real BI-FAST/ISO 20022 integration. |
| **Verification** | Penetration test oracle flow; verify attestation verification |
| **Status** | Open |

### FIND-007: Bridge Centralized - Single Relayer Key
| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Component** | BridgeVault.sol, BridgeRelayer.sol, BridgeRelayer service |
| **Location** | BridgeRelayer constructor line 44-50; BridgeRelayer service line 280 |
| **Technical Description** | BridgeRelayer controlled by single `RELAYER_ADMIN_ROLE` key. BridgeRelayer service uses single private key from env. No decentralized network, no threshold signatures, no light client verification. |
| **Exploit Scenario** | 1. Relayer key stolen → attacker mints arbitrary IDRC on destination chain. 2. Relayer service hacked → unauthorized minting. 3. No replay protection across chains beyond nonce. 4. No finality waiting - reorgs cause double-mint. |
| **Business Impact** | Unlimited unauthorized minting. Total supply manipulation. Bridge funds at risk. |
| **Remediation** | 1. Integrate proven bridge (LayerZero, Axelar, Wormhole). 2. Or implement MPC relayer network. 3. Add light client verification. 4. Finality checks per chain. |
| **Verification** | Threat model bridge; test key compromise scenarios |
| **Status** | Open |

### FIND-008: Multisig delegatecall to Self Enables Arbitrary Execution
| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Component** | MultisigWallet.sol |
| **Location** | Line 156-163 (executeTransaction) |
| **Technical Description** | When `txn.to == address(this)`, multisig uses `delegatecall` preserving `msg.sender`. This allows owners to execute arbitrary code in multisig context, including storage manipulation, role changes, self-destruct. |
| **Exploit Scenario** | 1. Owner proposes transaction to multisig with malicious calldata. 2. Threshold reached, execute. 3. `delegatecall` runs attacker code with multisig's storage context. 4. Attacker can: grant roles, change owners, drain ETH, self-destruct. |
| **Business Impact** | Complete multisig compromise if any owner key compromised. Defeats M-of-N security. |
| **Remediation** | 1. Remove self-delegatecall or restrict to specific safe functions. 2. Use `call` not `delegatecall` for self-calls. 3. Implement module system like Gnosis Safe. |
| **Verification** | Test delegatecall attack vectors; verify only safe operations allowed |
| **Status** | Open |

### FIND-009: No Rate Limiting on API Endpoints
| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Component** | FastAPI (services/api/main.py) |
| **Location** | Line 65-140 (app setup) |
| **Technical Description** | No rate limiting middleware configured. All endpoints (including /mint, /burn, /bridge) vulnerable to DoS and brute force. |
| **Exploit Scenario** | 1. Attacker floods /mint endpoint → gas exhaustion for minter. 2. Brute force JWT/API keys. 3. Bridge spam → nonce exhaustion. 4. Oracle update spam. |
| **Business Impact** | Service unavailable. Financial operation disruption. Potential for gas griefing. |
| **Remediation** | Add `slowapi` or custom rate limiter. Configure per-endpoint limits. Use Redis for distributed limiting. |
| **Verification** | Load test with burst requests; verify 429 responses |
| **Status** | Open |

### FIND-010: No Idempotency Keys for Financial Operations
| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Component** | API Routes (token.py, bridge.py, reserve.py) |
| **Location** | All POST endpoints |
| **Technical Description** | No idempotency key support. Retries (network timeout, client retry) cause duplicate mint/burn/bridge operations. |
| **Exploit Scenario** | 1. Client calls /mint, network times out. 2. Client retries. 3. Both succeed → double mint. 4. Same for bridge transfers → double mint on destination. |
| **Business Impact** | Duplicate token issuance. Supply inflation. Financial loss. Reconciliation nightmare. |
| **Remediation** | Add `Idempotency-Key` header requirement. Store keys in Redis with TTL. Check before processing. |
| **Verification** | Test duplicate requests with same idempotency key; verify single execution |
| **Status** | Open |

### FIND-011: Hardcoded Secrets in Docker/K8s Configs
| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Component** | docker/docker-compose.yml, k8s/base/secret.yaml |
| **Location** | docker-compose.yml line 11, 49; k8s/base/secret.yaml |
| **Technical Description** | `POSTGRES_PASSWORD=postgres` hardcoded in docker-compose. K8s secrets contain base64-encoded plaintext. No external secrets manager. |
| **Exploit Scenario** | 1. Git repo leaked → production DB password exposed. 2. K8s config leaked → all secrets exposed. 3. CI/CD logs → secrets in plaintext. |
| **Business Impact** | Full infrastructure compromise. Data breach. Regulatory violation (PDP UU). |
| **Remediation** | 1. Use `.env` files (gitignored) for local. 2. Use ExternalSecrets/SealedSecrets/Vault for K8s. 3. Rotate all exposed secrets. |
| **Verification** | Scan configs for secrets; verify secret manager integration |
| **Status** | Open |

### FIND-012: KYC/AML and Oracle Are Complete Mocks
| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Component** | services/compliance/kyc_aml_service.py, services/oracle/oracle_relayer.py |
| **Location** | kyc_aml_service.py line 862-874; oracle_relayer.py line 40-50 |
| **Technical Description** | `create_kyc_aml_service` raises `NotImplementedError` for production. `BankCustodianClient.get_fiat_balance` returns `random.randint`. No real integrations exist. |
| **Exploit Scenario** | Deployed to mainnet with mock services → no KYC, no sanctions screening, fake reserve data. Regulatory shutdown. Criminal liability. |
| **Business Impact** | **Cannot launch mainnet.** Legal/regulatory violation. Funds at risk. |
| **Remediation** | 1. Integrate real eKYC provider (Onfido, Jumio, Sumsub). 2. Integrate sanctions screening (Chainalysis, TRM, ComplyAdvantage). 3. Integrate BI-FAST/ISO 20022 bank API. 4. Implement PII encryption. |
| **Verification** | End-to-end compliance flow test; regulatory review |
| **Status** | Open |

---

## HIGH FINDINGS (15)

### FIND-013: Permit Nonce Not Protected Against Replay Across Chains
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | IDRCToken.sol |
| **Location** | Line 317-318 (nonce increment) |
| **Technical Description** | Permit nonce is per-address but not chain-aware. Same permit signature valid on multiple chains if domain separator identical (same name, version, contract address). |
| **Exploit Scenario** | User signs permit on Ethereum. Attacker replays on Polygon if same contract address/name. Nonce consumed on both chains. |
| **Remediation** | Include `chainId` in domain separator (already done). Verify chainId matches. |
| **Status** | Open |

### FIND-014: No Timelock Enforcement on Sensitive Role Changes
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | IDRCToken.sol, roles.yaml |
| **Location** | roles.yaml line 96-104 (timelocks config only) |
| **Technical Description** `roles.yaml` defines timelocks (48h upgrade, 24h oracle change) but **no code enforces them**. Role grants/revokes immediate. |
| **Exploit Scenario** | Compromised admin key → instant role changes → mint/burn/pause/upgrade. No time for detection/response. |
| **Remediation** | Implement TimelockController. Queue role changes. Enforce delays in contract. |
| **Status** | Open |

### FIND-015: BridgeVault setRelayer Doesn't Update Immutable Variable
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | BridgeVault.sol |
| **Location** | Line 28-29 (immutable), Line 131-137 (setRelayer) |
| **Technical Description** | `relayer` is `immutable` but `setRelayer` only updates role. Immutable variable never used after constructor, but misleading. |
| **Exploit Scenario** | Confusion in audits. Off-chain tools reading `relayer()` get stale value. |
| **Remediation** | Remove immutable `relayer` or make mutable and update in `setRelayer`. |
| **Status** | Open |

### FIND-016: No Finality Handling in Bridge
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | BridgeRelayer.sol, BridgeRelayer service |
| **Location** | BridgeRelayer line 56-63; bridge_relayer.py line 200-250 |
| **Technical Description** | Bridge processes `TokensLocked` events immediately. No confirmation blocks wait. Reorg on source chain = double mint on destination. |
| **Exploit Scenario** | 1. User locks tokens on Ethereum. 2. Relayer mints on Polygon. 3. Ethereum reorgs, lock tx reverted. 4. Polygon mint stands → unbacked tokens. |
| **Remediation** | Wait for finality (Ethereum: 2 epochs ~12.8min, Polygon: 128 blocks, etc.). Configurable per chain. |
| **Status** | Open |

### FIND-017: No Reorg Protection in Indexer
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | Indexer (services/indexer/indexer.py) |
| **Location** | Line 211-213 (batch indexing) |
| **Technical Description** | Indexer processes blocks up to `latest_block - 1` with no reorg handling. If reorg occurs, indexed events become invalid. No rollback mechanism. |
| **Exploit Scenario** | Reorg causes double-counted mints/burns in off-chain database. Dashboard shows wrong supply. |
| **Remediation** | Track chain head. On reorg, rollback and re-index. Use `blockHash` to detect. |
| **Status** | Open |

### FIND-018: Caller Parameter Trusted from Request Body
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | API Routes (token.py, bridge.py, etc.) |
| **Location** | token.py line 79, 93, 111, etc. |
| **Technical Description** | API endpoints accept `caller` in request body (e.g., `TokenMintRequest.caller`). Auth derives identity from JWT but `caller` used for blockchain `transact`. Mismatch possible. |
| **Exploit Scenario** | Authenticated user A calls /mint with `caller=B`. If B has MINTER_ROLE, mint succeeds as B. Identity confusion. |
| **Remediation** | Derive `caller` from authenticated identity. Remove `caller` from request models. |
| **Status** | Open |

### FIND-019: No Request Correlation IDs
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | FastAPI (services/api/main.py) |
| **Location** | Line 65-140 |
| **Technical Description** | No middleware to generate/propagate `X-Request-ID` or `X-Correlation-ID`. Distributed tracing impossible. |
| **Remediation** | Add correlation ID middleware. Propagate to logs, metrics, downstream services. |
| **Status** | Open |

### FIND-020: Database Models Lack Financial Ledger Tables
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | services/api/database.py |
| **Location** | Line 34-86 (User, APIKey, AuditLog, TokenEvent) |
| **Technical Description** | No double-entry ledger tables. Only `TokenEvent` for blockchain events. No accounts, journals, reconciliations. |
| **Remediation** | Add ledger schema: accounts, journal_entries, journal_lines, reconciliations. |
| **Status** | Open |

### FIND-021: No Alembic Migrations in Evidence
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | services/requirements.txt, services/api/ |
| **Location** | requirements.txt line 9 (alembic listed) |
| **Technical Description** | `alembic` in requirements but no migration scripts, `alembic.ini`, or migration history found. |
| **Remediation** | Initialize alembic. Create baseline migration. Enforce in CI. |
| **Status** | Open |

### FIND-022: No Audit Log Integrity Protection
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | services/api/database.py (AuditLog), services/api/auth.py (log_audit) |
| **Location** | database.py line 71-86; auth.py line 318-343 |
| **Technical Description** | Audit logs stored as mutable database rows. No hash chaining, no Merkle tree, no append-only guarantee. Admin can delete/modify. |
| **Remediation** | Hash chain: each log includes hash of previous. Periodic anchoring to blockchain. |
| **Status** | Open |

### FIND-023: Supply Cap Can Be Lowered Below Total Supply (Reverts But No Warning)
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | IDRCToken.sol |
| **Location** | Line 228-232 (setSupplyCap) |
| **Technical Description** | `setSupplyCap` reverts if `newCap < _totalSupply` but no event for attempted reduction. No monitoring alert. |
| **Remediation** | Emit event on failed attempt. Add monitor check. |
| **Status** | Open |

### FIND-024: Bridge Pause Requires RELAYER_ADMIN Not Multisig
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | BridgeVault.sol, BridgeRelayer.sol, bridge.py router |
| **Location** | BridgeVault line 139-145; bridge.py line 134-149 |
| **Technical Description** | Bridge pause/unpause controlled by `RELAYER_ADMIN_ROLE` (single key), not multisig. Emergency response centralized. |
| **Remediation** | Grant PAUSER_ROLE to multisig. Require multisig for bridge pause. |
| **Status** | Open |

### FIND-025: No Circuit Breaker for Oracle Failures
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | MonitorService, OracleRelayer |
| **Location** | monitor_service.py line 77-95; oracle_relayer.py line 126-130 |
| **Technical Description** | Monitor alerts on stale oracle but no automatic pause of minting. OracleRelayer alerts after 5 failures but continues. |
| **Remediation** | Auto-pause minting if oracle stale > threshold. Circuit breaker pattern. |
| **Status** | Open |

### FIND-026: Web3.py transact() Used Without Gas Estimation Bounds
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | services/api/services/*.py |
| **Location** | token_service.py line 37; bridge_service.py line 57, etc. |
| **Technical Description** | `transact()` calls without gas limits or price bounds. Malicious contract could consume all gas. |
| **Remediation** | Add gas estimation with max cap. Use `estimateGas` + buffer. |
| **Status** | Open |

### FIND-027: No Input Sanitization on Calldata in Multisig
| Field | Value |
|-------|-------|
| **Severity** | High |
| **Component** | MultisigWallet.sol, multisig.py router |
| **Location** | MultisigWallet line 85-102; multisig.py line 36-38 |
| **Technical Description** | `submitTransaction` accepts arbitrary `data` bytes. No validation of selector, no simulation. |
| **Remediation** | Add transaction simulation. Whitelist allowed targets/selectors for multisig. |
| **Status** | Open |

---

## MEDIUM FINDINGS (18)

### FIND-028: Echidna Invariants Referenced But Not Implemented
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | echidna.config.yaml, contracts/ |
| **Location** | echidna.config.yaml line 29-37, 45-50, 60-65, 74-78 |
| **Technical Description** | Echidna config lists invariants like `invariant_totalSupplyEqualsSumOfBalances`, `invariant_pausedPreventsTransfers` but these functions don't exist in contracts. |
| **Remediation** | Implement invariant functions in contracts or remove from config. |
| **Status** | Open |

### FIND-029: Permit Tests Are Placeholders
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | test/IDRCToken.t.sol |
| **Location** | Line 124-138 |
| **Technical Description** | `testPermit`, `testPermitExpired`, `testPermitInvalidSignature` all just `assertEq(true, true)`. No actual permit testing. |
| **Remediation** | Implement proper permit tests using `vm.sign` with unlocked wallets. |
| **Status** | Open |

### FIND-030: No Invariant Tests in Solidity Test Suite
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | test/ |
| **Location** | All test files |
| **Technical Description** | No `invariant_*` functions in any test file. CI runs `forge test --invariant` but no invariants defined. |
| **Remediation** | Add invariant tests for: supply=sum balances, paused blocks transfers, blacklist blocks, only minter mints. |
| **Status** | Open |

### FIND-031: No Integration Tests Between Contracts
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | test/ |
| **Location** | All test files |
| **Technical Description** | Each contract tested in isolation. No tests for: Token+Reserve, Token+Bridge, Token+Multisig, Reserve+Bridge. |
| **Remediation** | Add integration test suite. Test full flows: deposit→mint, redemption→burn, bridge→mint. |
| **Status** | Open |

### FIND-032: Slither Config Excludes Critical Detectors
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | slither.config.json |
| **Location** | Line 3-59 (exclude list) |
| **Technical Description** | Excludes: `reentrancy-eth`, `reentrancy-no-eth`, `arbitrary-send-eth`, `arbitrary-send-erc20`, `unchecked-low-level-calls`, `delegatecall`, `tx-origin`, `self-destruct`. These are critical for financial contracts. |
| **Remediation** | Remove critical detectors from exclude. Fix findings or justify with `// slither-disable`. |
| **Status** | Open |

### FIND-033: Duplicate IDRCToken.sol in contracts/ and contracts/token/
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | contracts/ |
| **Location** | contracts/IDRCToken.sol, contracts/token/IDRCToken.sol |
| **Technical Description** | Two copies of IDRCToken.sol. Risk of divergence. `contracts/IDRCToken.sol` not in import graph (imports use `contracts/token/IDRCToken.sol`). |
| **Remediation** | Remove duplicate. Single source of truth. |
| **Status** | Open |

### FIND-034: Hardcoded Chain IDs in Deployment Script
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | script/DeployIDRC.s.sol |
| **Location** | Line 28-34 |
| **Technical Description** | Chain IDs hardcoded as constants. Not configurable via env. |
| **Remediation** | Use `vm.envUint` for chain IDs. |
| **Status** | Open |

### FIND-035: Inconsistent Naming (IDRC vs IDRCToken)
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | Throughout codebase |
| **Technical Description** | Token called "IDRC" in README, "IDRCToken" in code, "IDR Coin" in name. Contract name `IDRCToken` but symbol `IDRC`. |
| **Remediation** | Standardize: Contract = IDRCToken, Symbol = IDRC, Name = "IDR Coin". |
| **Status** | Open |

### FIND-036: README Overclaims Production Readiness
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | README.md |
| **Location** | Line 3-4, 172-178, 316-324 |
| **Technical Description** | Claims "Production-ready", "321 passing", "100% coverage", "Audits planned" (none done). Misleading for investors/regulators. |
| **Remediation** | Update to reflect actual status: "Development/Staging", note mock services, remove audit claims. |
| **Status** | Open |

### FIND-037: No API Reference Documentation
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | docs/ |
| **Location** | docs/ (only DR_RUNBOOKS.md) |
| **Technical Description** | No OpenAPI/Swagger docs published. `/docs` disabled in production. No API reference for integrators. |
| **Remediation** | Enable OpenAPI in staging. Generate reference docs. |
| **Status** | Open |

### FIND-038: No Threat Model Document
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | docs/ |
| **Location** | docs/ |
| **Technical Description** | No `THREAT_MODEL.md`. Security.md only has contacts. |
| **Remediation** | Create threat model: assets, actors, attack trees, mitigations. |
| **Status** | Open |

### FIND-039: No Financial Model Documentation
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | docs/ |
| **Location** | docs/ |
| **Technical Description** | No `FINANCIAL_MODEL.md`. Reserve policy, issuance/redemption flows, fee structure undocumented. |
| **Remediation** | Document financial model: peg mechanism, reserve composition, fees, slippage. |
| **Status** | Open |

### FIND-040: No Database Backup/Recovery Testing
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | docker/, k8s/, docs/ |
| **Technical Description** | PostgreSQL in docker-compose but no backup strategy, no PITR config, no restore testing documented. |
| **Remediation** | Add backup sidecar. Document recovery procedure. Test quarterly. |
| **Status** | Open |

### FIND-041: No SBOM Generation in CI
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | .github/workflows/ |
| **Location** | ci.yml, security.yml |
| **Technical Description** | No Software Bill of Materials generation. Required for supply chain security. |
| **Remediation** | Add `syft` or `cyclonedx` to CI. Upload SBOM as artifact. |
| **Status** | Open |

### FIND-042: No Staging Environment Deployment Gate
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | .github/workflows/deploy.yml |
| **Location** | deploy.yml |
| **Technical Description** | Deploy workflow exists but no staging gate. No automatic deploy to staging on merge to develop. |
| **Remediation** | Add staging deploy job. Require staging health checks before prod. |
| **Status** | Open |

### FIND-043: No Production Deployment Approval Workflow
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | .github/workflows/deploy.yml |
| **Location** | deploy.yml |
| **Technical Description** | Production deploy requires manual trigger but no approval gate (environment protection rules). |
| **Remediation** | Configure GitHub Environment protection: required reviewers, wait timer. |
| **Status** | Open |

### FIND-044: No PII Encryption at Rest in KYC Schema
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | kyc_aml_service.py (DATABASE_SCHEMA) |
| **Location** | Line 883-969 |
| **Technical Description** | KYC schema stores email, documents, extracted_data as plaintext. No encryption. Violates UU PDP (Indonesian Data Protection Law). |
| **Remediation** | Encrypt PII columns. Use `pgcrypto` or application-layer encryption. |
| **Status** | Open |

### FIND-045: No Secrets Rotation Procedure
| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Component** | docs/, docker/, k8s/ |
| **Technical Description** | No documented procedure for rotating: JWT secret, DB passwords, oracle key, relayer key, multisig owners. |
| **Remediation** | Create secrets rotation runbook. Automate where possible. |
| **Status** | Open |

---

## LOW FINDINGS (10)

### FIND-046: Missing NatSpec on Public Functions
| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Component** | contracts/ |
| **Location** | Various |
| **Technical Description** | Some public/external functions lack NatSpec documentation. |
| **Remediation** | Add NatSpec to all public API. |
| **Status** | Open |

### FIND-047: Unused Import in IDRCToken.sol
| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Component** | IDRCToken.sol |
| **Location** | Line 6 (Pausable imported but also from OZ) |
| **Technical Description** | `Pausable` imported from OZ but also available via inheritance chain. |
| **Remediation** | Clean imports. |
| **Status** | Open |

### FIND-048: Magic Numbers in ProofOfReserve
| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Component** | ProofOfReserve.sol |
| **Location** | Line 24 (`_MIN_RESERVE_RATIO = 1e18`) |
| **Technical Description** | 1e18 used directly. Should be named constant with comment. |
| **Remediation** | Already has `MIN_RESERVE_RATIO()` getter. Use consistently. |
| **Status** | Open |

### FIND-049: BridgeVault Nonce Increment Before Event
| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Component** | BridgeVault.sol |
| **Location** | Line 79-80 |
| **Technical Description** | `_nonce++` then `bridgeNonce = _nonce`. Standard but could use `bridgeNonce = ++_nonce` for clarity. |
| **Remediation** | Style fix. |
| **Status** | Open |

### FIND-050: Inconsistent Error Messages
| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Component** | Contracts |
| **Location** | Various |
| **Technical Description** | Mix of custom errors and string reverts. Some custom errors have parameters, others don't. |
| **Remediation** | Standardize on custom errors with parameters. |
| **Status** | Open |

### FIND-051: Python Type Hints Missing in Some Services
| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Component** | services/api/services/ |
| **Location** | Various |
| **Technical Description** | Some function signatures lack return type hints. MyPy strict mode may fail. |
| **Remediation** | Add full type annotations. Run mypy in CI. |
| **Status** | Open |

### FIND-052: Docker Compose Uses Default Redis Config
| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Component** | docker/docker-compose.yml |
| **Location** | Line 26-40 |
| **Technical Description** | Redis configured without password, no TLS. OK for dev, not prod. |
| **Remediation** | Add Redis password via env. Enable TLS for prod. |
| **Status** | Open |

### FIND-053: K8s Resource Limits Missing in Dev Overlay
| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Component** | k8s/overlays/dev/kustomization.yaml |
| **Location** | File |
| **Technical Description** | Dev overlay lacks resource limits/requests. Can cause OOM on shared clusters. |
| **Remediation** | Add default resources in base, override in overlays. |
| **Status** | Open |

### FIND-054: No Health Check for Bridge/Oracle Services
| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Component** | docker/docker-compose.yml |
| **Location** | Line 78-117 (oracle, bridge services) |
| **Technical Description** | API has healthcheck but oracle and bridge services don't. |
| **Remediation** | Add healthcheck endpoints to services. Configure in compose. |
| **Status** | Open |

### FIND-055: Prometheus Alerts Not Tuned
| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Component** | docker/prometheus/alerts/idrc-alerts.yml |
| **Location** | File |
| **Technical Description** | Generic alerts. No business-specific thresholds (collateralization, oracle staleness, bridge pending). |
| **Remediation** | Add IDRC-specific alert rules with proper severity routing. |
| **Status** | Open |

---

## INFORMATIONAL FINDINGS (8)

### FIND-056: Consider EIP-712 Domain Separator Versioning
| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **Component** | IDRCToken.sol |
| **Location** | Line 117-125 |
| **Technical Description** | Domain separator uses version "1". Plan for future upgrades. |
| **Remediation** | Document versioning strategy. |
| **Status** | Open |

### FIND-057: Consider ERC-20 Permit Batch Operations
| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **Component** | IDRCToken.sol |
| **Location** | N/A |
| **Technical Description** | Gas optimization: batch permits (ERC-2612 doesn't support but ERC-3009 does). |
| **Remediation** | Evaluate for v2. |
| **Status** | Open |

### FIND-058: Consider ERC-4626 for Reserve Vault
| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **Component** | Architecture |
| **Location** | N/A |
| **Technical Description** | Reserve management could use ERC-4626 vault standard for yield-bearing reserves. |
| **Remediation** | Evaluate for v2. |
| **Status** | Open |

### FIND-059: Consider Account Abstraction (ERC-4337)
| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **Component** | Architecture |
| **Location** | N/A |
| **Technical Description** | User operations (mint/burn/bridge) could use account abstraction for gasless UX. |
| **Remediation** | Evaluate for v2. |
| **Status** | Open |

### FIND-060: Consider ZK-Proof Reserve Verification
| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **Component** | Architecture |
| **Location** | N/A |
| **Technical Description** | Zero-knowledge proof of reserve solvency without revealing balances. |
| **Remediation** | Research for v2. |
| **Status** | Open |

### FIND-061: Consider Intent-Based Bridge (ERC-7683)
| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **Component** | Architecture |
| **Location** | N/A |
| **Technical Description** | New standard for cross-chain intents. Better UX, solver competition. |
| **Remediation** | Monitor standardization. |
| **Status** | Open |

### FIND-062: Consider Formal Verification (Certora/Halmos)
| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **Component** | certora/ |
| **Location** | certora/ (empty) |
| **Technical Description** | Certora directory exists but empty. Formal verification would catch logic bugs. |
| **Remediation** | Write Certora specs for critical invariants. |
| **Status** | Open |

### FIND-063: Consider Regulatory Reporting Automation
| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **Component** | Compliance |
| **Location** | N/A |
| **Technical Description** | Automated BI/OJK/PPATK reporting from ledger data. |
| **Remediation** | Design in Phase 9. |
| **Status** | Open |

---

## SUMMARY TABLE

| Severity | Count | % of Total |
|----------|-------|------------|
| Critical | 12 | 19% |
| High | 15 | 24% |
| Medium | 18 | 29% |
| Low | 10 | 16% |
| Informational | 8 | 13% |
| **Total** | **63** | **100%** |

---

## REMEDIATION PRIORITY ORDER

1. **Immediate (Block Mainnet):** FIND-001, FIND-002, FIND-003, FIND-004, FIND-005, FIND-006, FIND-007, FIND-008, FIND-009, FIND-010, FIND-011, FIND-012
2. **Pre-Launch (High):** FIND-013 through FIND-027
3. **Post-Launch (Medium):** FIND-028 through FIND-045
4. **Technical Debt (Low):** FIND-046 through FIND-055
5. **Future (Informational):** FIND-056 through FIND-063

---

**END OF SECURITY_FINDINGS.md**