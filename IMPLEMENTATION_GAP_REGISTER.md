# IMPLEMENTATION_GAP_REGISTER.md
# IDRT Implementation Gap Register
**Date:** 2026-11-18
**Phase:** 0 - Repository Forensics
**Purpose:** Track all missing functionality between current state and institutional-grade requirements
**Total Gaps:** 87 (23 Critical, 31 High, 22 Medium, 11 Low)

---

## GAP CLASSIFICATION

| Priority | Definition | SLA |
|----------|------------|-----|
| **P0 - Critical** | Blocks mainnet launch; financial integrity; security | Immediate |
| **P1 - High** | Required for production; major feature incomplete | Pre-launch |
| **P2 - Medium** | Important for operations; compliance; scalability | Post-launch |
| **P3 - Low** | Nice-to-have; technical debt; future enhancement | Ongoing |

---

## P0 - CRITICAL GAPS (23)

### GAP-001: Double-Entry Financial Ledger
| Field | Value |
|-------|-------|
| **Domain** | Financial Ledger |
| **Component** | services/api/database.py, New ledger module |
| **Description** | No double-entry accounting system exists. Required for all financial events. |
| **Required** | Chart of accounts, journal entries, journal lines, balancing constraint, hash chain |
| **Dependencies** | Database migrations, Decimal arithmetic replacement |
| **Effort** | Large (2-3 weeks) |
| **Verification** | Every financial event creates balanced entry; auditor export balances |

### GAP-002: Fixed-Precision Arithmetic Throughout
| Field | Value |
|-------|-------|
| **Domain** | Financial Integrity |
| **Component** | All Python services (monitor, reserve, token, bridge, multisig) |
| **Description** | Float used for monetary calculations. Must use integer (wei) or Decimal. |
| **Required** | Replace all `/ 10**18` with Decimal; internal calculations in wei |
| **Dependencies** | GAP-001 |
| **Effort** | Medium (1 week) |
| **Verification** | No float in financial paths; mypy strict passes |

### GAP-003: Real Oracle Integration (Not Mock)
| Field | Value |
|-------|-------|
| **Domain** | Oracle & Attestation |
| **Component** | services/oracle/oracle_relayer.py, ProofOfReserve.sol |
| **Description** | BankCustodianClient returns random numbers. No BI-FAST/ISO 20022 integration. |
| **Required** | Real bank API integration; signed attestations; multi-oracle threshold; HSM keys |
| **Dependencies** | Bank partnership, PKI infrastructure |
| **Effort** | Large (4-8 weeks + bank integration) |
| **Verification** | Oracle pushes real balance; attestation verifiable on-chain |

### GAP-004: Real KYC/AML Integration (Not Mock)
| Field | Value |
|-------|-------|
| **Domain** | Compliance |
| **Component** | services/compliance/kyc_aml_service.py |
| **Description** | create_kyc_aml_service raises NotImplementedError for production. All providers mock. |
| **Required** | eKYC provider (Onfido/Jumio); sanctions screening (Chainalysis/TRM); PII encryption; SAR automation |
| **Dependencies** | Vendor contracts, UU PDP compliance |
| **Effort** | Large (6-12 weeks + vendor integration) |
| **Verification** | Real KYC flow; sanctions hit detection; SAR generation |

### GAP-005: Decentralized Bridge (Not Single Key)
| Field | Value |
|-------|-------|
| **Domain** | Bridge Infrastructure |
| **Component** | contracts/bridge/, services/bridge/ |
| **Description** | Single relayer key controls all cross-chain minting. No verification, no finality. |
| **Required** | LayerZero/Axelar/Wormhole integration OR custom MPC network; light client verification; finality handling |
| **Dependencies** | Bridge partner integration or MPC development |
| **Effort** | Large (8-16 weeks) |
| **Verification** | No single key can mint; reorg protection; rate limits |

### GAP-006: Issuance State Machine
| Field | Value |
|-------|-------|
| **Domain** | Issuance Engine |
| **Component** | New: contracts/issuance/, services/api/services/issuance_service.py |
| **Description** | Direct mint() call. No deposit verification, no approval workflow, no state tracking. |
| **Required** | REQUESTED→DEPOSIT_PENDING→DEPOSIT_VERIFIED→APPROVED→MINTED with terminal REJECTED/EXPIRED |
| **Dependencies** | GAP-001 (ledger), GAP-004 (compliance) |
| **Effort** | Medium (2 weeks) |
| **Verification** | Cannot mint without verified deposit + multisig approval |

### GAP-007: Redemption State Machine
| Field | Value |
|-------|-------|
| **Domain** | Redemption Engine |
| **Component** | New: contracts/redemption/, services/api/services/redemption_service.py |
| **Description** | Direct burn() call. No payout confirmation, no reconciliation, no timeout handling. |
| **Required** | REQUESTED→VALIDATED→BURN_PENDING→BURN_CONFIRMED→FIAT_PAYOUT_PENDING→COMPLETED with REJECTED/EXPIRED/REFUND |
| **Dependencies** | GAP-001 (ledger), GAP-003 (bank payout), GAP-004 (compliance) |
| **Effort** | Medium (2 weeks) |
| **Verification** | Cannot mark complete without bank payout confirmation |

### GAP-008: Rate Limiting on All API Endpoints
| Field | Value |
|-------|-------|
| **Domain** | API Gateway |
| **Component** | services/api/main.py, New rate_limit middleware |
| **Description** | No rate limiting. Vulnerable to DoS, brute force, gas griefing. |
| **Required** | Per-endpoint limits; Redis-backed distributed limiting; admin bypass; metrics |
| **Dependencies** | Redis (already in docker-compose) |
| **Effort** | Small (3 days) |
| **Verification** | Burst requests return 429; legitimate traffic unaffected |

### GAP-009: Idempotency Keys for Financial Operations
| Field | Value |
|-------|-------|
| **Domain** | API Gateway |
| **Component** | services/api/routers/ (token, bridge, reserve, multisig) |
| **Description** | No idempotency. Retries cause duplicate mint/burn/bridge. |
| **Required** | Idempotency-Key header; Redis storage with TTL; check before processing; return existing result |
| **Dependencies** | Redis |
| **Effort** | Small (3 days) |
| **Verification** | Duplicate requests with same key → single execution |

### GAP-010: Replace Custom AccessControl with OpenZeppelin
| Field | Value |
|-------|-------|
| **Domain** | Token Protocol / Access Control |
| **Component** | contracts/access/AccessControl.sol, contracts/token/IDRCToken.sol |
| **Description** | 123-line custom reimplementation. Missing features, unaudited. |
| **Required** | Import OZ AccessControl; remove custom file; update all inheritances; verify role hierarchy |
| **Dependencies** | None |
| **Effort** | Small (2 days) |
| **Verification** | All role tests pass; Slither clean; OZ compatible |

### GAP-011: Permit Low-S Enforcement
| Field | Value |
|-------|-------|
| **Domain** | Token Protocol |
| **Component** | contracts/token/IDRCToken.sol (permit function) |
| **Description** | EIP-2612 requires low-s. Current implementation accepts high-s signatures. |
| **Required** | Add `require(s <= secp256k1n/2)` check |
| **Dependencies** | None |
| **Effort** | Trivial (1 hour) |
| **Verification** | High-s signatures revert; low-s work |

### GAP-012: VerifyProof Implementation
| Field | Value |
|-------|-------|
| **Domain** | Reserve Management |
| **Component** | contracts/reserve/ProofOfReserve.sol (verifyProof) |
| **Description** | Function returns true without verification. |
| **Required** | `return keccak256(reportData) == _latestProofHash;` |
| **Dependencies** | None |
| **Effort** | Trivial (30 min) |
| **Verification** | Matching data returns true; non-matching returns false |

### GAP-013: updateFiatBalance Zero Validation
| Field | Value |
|-------|-------|
| **Domain** | Reserve Management |
| **Component** | contracts/reserve/ProofOfReserve.sol (updateFiatBalance) |
| **Description** | Accepts zero balance. Should require positive amount. |
| **Required** | `require(newBalanceIdr > 0, "ZeroBalance");` |
| **Dependencies** | None |
| **Effort** | Trivial (30 min) |
| **Verification** | Zero amount reverts |

### GAP-014: Multisig Delegatecall Security
| Field | Value |
|-------|-------|
| **Domain** | Governance |
| **Component** | contracts/multisig/MultisigWallet.sol (executeTransaction) |
| **Description** | Self-delegatecall allows arbitrary code execution in multisig context. |
| **Required** | Remove delegatecall or restrict to safe function whitelist |
| **Dependencies** | None |
| **Effort** | Small (2 days) |
| **Verification** | Malicious calldata reverts; safe operations work |

### GAP-015: Timelock Enforcement on Sensitive Operations
| Field | Value |
|-------|-------|
| **Domain** | Governance |
| **Component** | contracts/token/IDRCToken.sol, contracts/reserve/ProofOfReserve.sol, contracts/bridge/ |
| **Description** | roles.yaml defines timelocks but no code enforces them. |
| **Required** | TimelockController for: upgrades (48h), oracle change (24h), supply cap (24h), role grants (configurable) |
| **Dependencies** | GAP-010 (OZ AccessControl) |
| **Effort** | Medium (1 week) |
| **Verification** | Role changes queued; execute only after delay |

### GAP-016: Secrets Management (No Hardcoded Secrets)
| Field | Value |
|-------|-------|
| **Domain** | DevSecOps |
| **Component** | docker/docker-compose.yml, k8s/base/secret.yaml, .env templates |
| **Description** | Hardcoded passwords in docker-compose; plaintext secrets in K8s. |
| **Required** | ExternalSecrets/SealedSecrets/Vault; gitignored .env files; secret rotation procedure |
| **Dependencies** | Infrastructure setup |
| **Effort** | Medium (1 week) |
| **Verification** | No secrets in git; CI passes with secret scanning |

### GAP-017: Database Migrations (Alembic)
| Field | Value |
|-------|-------|
| **Domain** | Database |
| **Component** | services/api/ (alembic missing) |
| **Description** | alembic in requirements but no migrations, config, or history. |
| **Required** | alembic init; baseline migration; CI enforcement; rollback procedures |
| **Dependencies** | GAP-001 (ledger schema) |
| **Effort** | Small (2 days) |
| **Verification** | Migration up/down works; CI runs migrations |

### GAP-018: Audit Log Integrity (Hash Chain)
| Field | Value |
|-------|-------|
| **Domain** | Monitoring & Observability |
| **Component** | services/api/database.py (AuditLog), services/api/auth.py (log_audit) |
| **Description** | Audit logs mutable. No hash chaining, no append-only guarantee. |
| **Required** | Each log includes hash of previous; periodic blockchain anchoring; tamper detection |
| **Dependencies** | GAP-001 |
| **Effort** | Small (3 days) |
| **Verification** | Tampering detected; hash chain verified |

### GAP-019: Request Correlation IDs
| Field | Value |
|-------|-------|
| **Domain** | API Gateway |
| **Component** | services/api/main.py |
| **Description** | No correlation IDs. Distributed tracing impossible. |
| **Required** | Middleware generates X-Request-ID; propagates to logs, metrics, downstream services |
| **Dependencies** | Structured logging (structlog already used) |
| **Effort** | Small (1 day) |
| **Verification** | Single request traceable across all services |

### GAP-020: Bridge Pause Requires Multisig
| Field | Value |
|-------|-------|
| **Domain** | Bridge Infrastructure |
| **Component** | contracts/bridge/BridgeVault.sol, BridgeRelayer.sol, services/api/routers/bridge.py |
| **Description** | Bridge pause controlled by single RELAYER_ADMIN_ROLE key. |
| **Required** | Grant PAUSER_ROLE to multisig; require multisig for pause/unpause |
| **Dependencies** | GAP-010 |
| **Effort** | Small (1 day) |
| **Verification** | Single key cannot pause; multisig can |

### GAP-021: Circuit Breaker for Oracle/Bridge
| Field | Value |
|-------|-------|
| **Domain** | Monitoring & Observability |
| **Component** | services/api/services/monitor_service.py, OracleRelayer, BridgeRelayer |
| **Description** | Alerts on stale oracle but no auto-pause. Oracle continues after failures. |
| **Required** | Auto-pause minting if oracle stale > threshold; circuit breaker pattern; manual override by multisig |
| **Dependencies** | GAP-001, GAP-015 |
| **Effort** | Medium (1 week) |
| **Verification** | Stale oracle → minting paused; recovery requires multisig |

### GAP-022: Remove Duplicate IDRCToken.sol
| Field | Value |
|-------|-------|
| **Domain** | Code Quality |
| **Component** | contracts/IDRCToken.sol (duplicate) |
| **Description** | Two copies of token contract. Risk of divergence. |
| **Required** | Delete contracts/IDRCToken.sol; verify all imports use contracts/token/IDRCToken.sol |
| **Dependencies** | None |
| **Effort** | Trivial (15 min) |
| **Verification** | Build passes; no duplicate files |

### GAP-023: Financial Reconciliation Engine
| Field | Value |
|-------|-------|
| **Domain** | Financial Ledger |
| **Component** | New: services/api/services/reconciliation_service.py |
| **Description** | No reconciliation between on-chain, off-chain, bank. |
| **Required** | Daily job comparing: supply vs liability, reserve vs bank, deposits vs mints, redemptions vs burns+payouts |
| **Dependencies** | GAP-001, GAP-003, GAP-006, GAP-007 |
| **Effort** | Large (2 weeks) |
| **Verification** | Zero discrepancies in test environment; alerts on mismatch |

---

## P1 - HIGH GAPS (31)

### GAP-024: Fee Accounting System
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Financial Ledger |
| **Description** | No fee parameters, collection, or accounting |

### GAP-025: Supply Cap Governance & Monitoring
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Token Protocol |
| **Description** | Cap exists but no alerts at 80/90/95%, no governance process |

### GAP-026: Blacklist Financial Accounting
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Financial Ledger |
| **Description** | Frozen balances not moved to encumbered reserve account |

### GAP-027: Bridge Accounting (Lock-Mint & Burn-Release)
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Financial Ledger |
| **Description** | Cross-chain transfers not reflected in ledger |

### GAP-028: Historical Financial Snapshots
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Financial Ledger |
| **Description** | No point-in-time balance sheet reconstruction |

### GAP-029: Gas Estimation Bounds on transact()
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Blockchain Integration |
| **Component** | services/api/services/*.py |
| **Description** | transact() without gas limits - griefing risk |

### GAP-030: Multisig Transaction Simulation
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Governance |
| **Component** | services/api/routers/multisig.py |
| **Description** | No simulation before propose; arbitrary calldata accepted |

### GAP-031: Caller Identity from Auth (Not Request Body)
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | API Gateway |
| **Component** | services/api/routers/*.py |
| **Description** | caller parameter in request body - trust issue |

### GAP-032: Input Validation on All Financial Endpoints
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | API Gateway |
| **Description** | Amount bounds, address checksum, chain ID validation |

### GAP-033: Database Backup/Recovery Testing
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | DevSecOps |
| **Description** | No PITR config, no restore testing documented |

### GAP-034: Staging Environment Deployment Gate
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | DevSecOps |
| **Component** | .github/workflows/deploy.yml |
| **Description** | No auto-deploy to staging on merge |

### GAP-035: Production Deployment Approval
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | DevSecOps |
| **Description** | No environment protection rules for prod |

### GAP-036: SBOM Generation
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | DevSecOps |
| **Description** | No Software Bill of Materials in CI |

### GAP-037: PII Encryption at Rest
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Compliance |
| **Component** | kyc_aml_service.py DATABASE_SCHEMA |
| **Description** | Email, documents, extracted_data stored plaintext |

### GAP-038: Secrets Rotation Procedure
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | DevSecOps |
| **Description** | No documented rotation for JWT, DB, oracle, relayer keys |

### GAP-039: Distributed Tracing (Jaeger)
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Observability |
| **Description** | No trace propagation across services |

### GAP-040: Prometheus Alerts Tuning
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Observability |
| **Component** | docker/prometheus/alerts/idrc-alerts.yml |
| **Description** | Generic alerts; no business-specific thresholds |

### GAP-041: Health Checks for Oracle/Bridge Services
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Observability |
| **Component** | docker/docker-compose.yml |
| **Description** | API has healthcheck; oracle/bridge don't |

### GAP-042: K8s Resource Limits
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | DevSecOps |
| **Component** | k8s/overlays/ |
| **Description** | Missing CPU/memory limits/requests |

### GAP-043: Network Policies in K8s
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | DevSecOps |
| **Component** | k8s/base/ |
| **Description** | No network policies restricting pod communication |

### GAP-044: Pod Security Standards
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | DevSecOps |
| **Description** | No PSS enforcement (restricted/baseline) |

### GAP-045: Redis TLS & Auth for Production
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | DevSecOps |
| **Component** | docker/docker-compose.yml |
| **Description** | Redis no password, no TLS in compose |

### GAP-046: Database Connection Pooling
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Database |
| **Component** | services/api/database.py |
| **Description** | Pool size fixed; no monitoring; no read replicas |

### GAP-047: API Versioning Strategy
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | API Gateway |
| **Description** | /api/v1/ prefix but no versioning policy, deprecation process |

### GAP-048: CORS/CSRF Production Hardening
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | API Gateway |
| **Component** | services/api/main.py |
| **Description** | CORS allows credentials + wildcard origin in dev; needs prod config |

### GAP-049: WebSocket Authentication
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | API Gateway |
| **Component** | services/api/main.py (websocket_endpoint) |
| **Description** | WS endpoint accepts unauthenticated connections |

### GAP-050: Error Response Standardization
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | API Gateway |
| **Description** | Inconsistent error formats across routers |

### GAP-051: OpenAPI Documentation Publishing
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Documentation |
| **Description** | /docs disabled in prod; no published reference |

### GAP-052: Integration Test Suite
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Testing |
| **Description** | No tests spanning Token+Reserve, Token+Bridge, Token+Multisig |

### GAP-053: Fuzz Testing Critical Invariants
| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Domain** | Testing |
| **Description** | Echidna config references non-existent invariants |

### GAP-054: Invariant Testing in CI
| Field | Value |
|-------|---|-------|
| **Priority** | P1 |
| **Domain** | Testing |
| **Description** | forge test --invariant runs but no invariant_* functions exist |

---

## P2 - MEDIUM GAPS (22)

### GAP-055: ERC-20 Permit Comprehensive Tests
### GAP-056: Slither Critical Detectors Enabled
### GAP-057: Formal Verification (Certora) Specs
### GAP-058: Disaster Recovery Runbooks (Complete)
### GAP-059: Incident Response Procedures
### GAP-060: Regulatory Reporting Automation
### GAP-061: L2 Deployment Strategy
### GAP-062: Yield-Bearing Reserve (ERC-4626)
### GAP-063: Account Abstraction (ERC-4337) Support
### GAP-064: ZK-Proof Reserve Verification
### GAP-065: Intent-Based Bridge (ERC-7683)
### GAP-066: Advanced Monitoring (Anomaly Detection)
### GAP-067: Multi-Sig Owner Recovery Procedure
### GAP-068: Upgrade Storage Layout Validation
### GAP-069: Chain Reorg Handling in Indexer
### GAP-070: Bridge Rate Limiting
### GAP-071: Oracle Multi-Source Aggregation
### GAP-072: Compliance Rule Engine (Configurable)
### GAP-073: Transaction Screening Real-Time
### GAP-074: Audit Export Package (BI/OJK/PPATK)
### GAP-075: Stress Test Framework
### GAP-076: Chaos Engineering Pipeline

---

## P3 - LOW GAPS (11)

### GAP-077: NatSpec Completeness
### GAP-078: Import Cleanup
### GAP-079: Magic Number Elimination
### GAP-080: Consistent Error Messages
### GAP-081: Python Type Hints Complete
### GAP-082: Docker Compose Production Hardening
### GAP-083: K8s Dev Overlay Resources
### GAP-084: README Accuracy (Production Claims)
### GAP-085: Threat Model Document
### GAP-086: Financial Model Document
### GAP-087: API Reference Documentation

---

## TRACKING METRICS

| Metric | Target | Current |
|--------|--------|---------|
| P0 Gaps Remaining | 0 | 23 |
| P1 Gaps Remaining | 0 | 31 |
| P2 Gaps Remaining | < 5 | 22 |
| P3 Gaps Remaining | < 10 | 11 |
| **Total Gaps** | **0** | **87** |

---

## GAP RESOLUTION WORKFLOW

1. **Identify** → Add to register with ID, priority, domain, description
2. **Design** → Technical specification, dependencies, effort estimate
3. **Implement** → Code + tests + documentation
4. **Verify** → Automated tests pass; manual verification per criteria
5. **Review** → Security review (P0/P1); code review (all)
6. **Close** → Update register; link PR/commit

---

**END OF IMPLEMENTATION_GAP_REGISTER.md**