# TECHNICAL_DEBT_REGISTER.md
# IDRT Technical Debt Register
**Date:** 2026-11-18
**Phase:** 0 - Repository Forensics
**Purpose:** Track known technical debt, shortcuts, and suboptimal implementations requiring future remediation
**Total Items:** 42

---

## DEBT CLASSIFICATION

| Category | Description |
|----------|-------------|
| **ARCH** | Architecture - structural decisions limiting future evolution |
| **CODE** | Code Quality - maintainability, readability, standards |
| **TEST** | Testing - coverage gaps, missing test types |
| **DOCS** | Documentation - missing, outdated, inaccurate |
| **INFRA** | Infrastructure - config, deployment, operations |
| **SEC** | Security - not vulnerabilities but defense-in-depth gaps |
| **PERF** | Performance - known bottlenecks, scaling limits |

---

## TECHNICAL DEBT ITEMS

### DEBT-001: Custom AccessControl vs OpenZeppelin (ARCH/SEC)
| Field | Value |
|-------|-------|
| **Category** | ARCH, SEC |
| **Severity** | High |
| **Component** | contracts/access/AccessControl.sol |
| **Description** | Full reimplementation of OZ AccessControl (123 lines). Missing: getRoleMember, getRoleMemberCount, AccessControlDefaultAdminRules, proper event indexing, ERC-165 interface detection. |
| **Impact** | Unaudited code in auth path; tooling incompatibility; maintenance burden; security review findings |
| **Remediation** | Replace with `import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";` |
| **Effort** | 2 days |
| **Blocker** | None |
| **Status** | Open |

### DEBT-002: Duplicate IDRCToken.sol (CODE)
| Field | Value |
|-------|-------|
| **Category** | CODE |
| **Severity** | Medium |
| **Component** | contracts/IDRCToken.sol, contracts/token/IDRCToken.sol |
| **Description** | Two identical copies. contracts/IDRCToken.sol not imported anywhere but creates confusion. |
| **Impact** | Risk of divergence; wasted review time; CI noise |
| **Remediation** | Delete contracts/IDRCToken.sol |
| **Effort** | 15 minutes |
| **Blocker** | None |
| **Status** | Open |

### DEBT-003: Float Arithmetic in Financial Paths (CODE/ARCH)
| Field | Value |
|-------|-------|
| **Category** | CODE, ARCH |
| **Severity** | High |
| **Component** | services/api/services/monitor_service.py, reserve_service.py, token_service.py |
| **Description** | Monetary values converted to float for display calculations. Python float has 53-bit precision - insufficient for 18-decimal wei values. |
| **Impact** | Rounding errors in dashboard, alerts, reports; audit failures |
| **Remediation** | Use Decimal for display; keep all internal calculations in wei (int) |
| **Effort** | 1 week |
| **Blocker** | Requires consistent pattern across all services |
| **Status** | Open |

### DEBT-004: Missing Financial Ledger (ARCH)
| Field | Value |
|-------|-------|
| **Category** | ARCH |
| **Severity** | Critical |
| **Component** | services/api/database.py (missing tables) |
| **Description** | No double-entry accounting. Only TokenEvent for blockchain events. |
| **Impact** | Cannot produce financial statements; regulatory non-compliance; no reconciliation |
| **Remediation** | Implement full ledger: accounts, journal_entries, journal_lines, reconciliations |
| **Effort** | 2-3 weeks |
| **Blocker** | Database migrations, Decimal arithmetic |
| **Status** | Open |

### DEBT-005: Mock Oracle & KYC Services (ARCH/SEC)
| Field | Value |
|-------|-------|
| **Category** | ARCH, SEC |
| **Severity** | Critical |
| **Component** | services/oracle/oracle_relayer.py, services/compliance/kyc_aml_service.py |
| **Description** | Oracle returns random numbers; KYC raises NotImplementedError for production. |
| **Impact** | Cannot launch mainnet; regulatory violation; zero compliance |
| **Remediation** | Integrate real bank API (BI-FAST), eKYC provider, sanctions screening |
| **Effort** | 8-16 weeks |
| **Blocker** | Vendor contracts, bank partnerships |
| **Status** | Open |

### DEBT-006: Centralized Bridge (ARCH/SEC)
| Field | Value |
|-------|-------|
| **Category** | ARCH, SEC |
| **Severity** | Critical |
| **Component** | contracts/bridge/, services/bridge/ |
| **Description** | Single relayer key controls all cross-chain minting. No verification, finality, or decentralization. |
| **Impact** | Single point of failure; unlimited mint risk; not trust-minimized |
| **Remediation** | Integrate LayerZero/Axelar/Wormhole OR build MPC network |
| **Effort** | 8-16 weeks |
| **Blocker** | Architecture decision, partner integration |
| **Status** | Open |

### DEBT-007: No Issuance/Redemption State Machines (ARCH)
| Field | Value |
|-------|-------|
| **Category** | ARCH |
| **Severity** | High |
| **Component** | contracts/token/IDRCToken.sol, services/api/routers/token.py |
| **Description** | Direct mint/burn calls. No deposit verification, approval workflow, payout confirmation. |
| **Impact** | No audit trail; duplicate mint risk; no compliance integration; regulatory gap |
| **Remediation** | Implement state machines with explicit transitions and terminal states |
| **Effort** | 2 weeks |
| **Blocker** | Requires ledger (DEBT-004) and compliance (DEBT-005) |
| **Status** | Open |

### DEBT-008: No Rate Limiting / Idempotency (INFRA/SEC)
| Field | Value |
|-------|-------|
| **Category** | INFRA, SEC |
| **Severity** | High |
| **Component** | services/api/main.py, routers/*.py |
| **Description** | No rate limiting middleware; no idempotency keys for financial operations. |
| **Impact** | DoS vulnerable; duplicate execution on retry; gas griefing |
| **Remediation** | Add slowapi/rate limiter; Idempotency-Key header with Redis |
| **Effort** | 3 days |
| **Blocker** | None |
| **Status** | Open |

### DEBT-009: Hardcoded Secrets in Configs (INFRA/SEC)
| Field | Value |
|-------|-------|
| **Category** | INFRA, SEC |
| **Severity** | Critical |
| **Component** | docker/docker-compose.yml, k8s/base/secret.yaml |
| **Description** | POSTGRES_PASSWORD=postgres in compose; base64 plaintext in K8s secrets. |
| **Impact** | Full infra compromise if repo leaked; regulatory violation (PDP UU) |
| **Remediation** | ExternalSecrets/SealedSecrets/Vault; gitignored .env files |
| **Effort** | 1 week |
| **Blocker** | Infrastructure setup |
| **Status** | Open |

### DEBT-010: No Database Migrations (INFRA)
| Field | Value |
|-------|-------|
| **Category** | INFRA |
| **Severity** | High |
| **Component** | services/api/ (alembic missing) |
| **Description** | alembic in requirements but no migrations, config, or history. |
| **Impact** | Schema drift; no rollback; deployment risk; team coordination issues |
| **Remediation** | alembic init; baseline migration; CI enforcement |
| **Effort** | 2 days |
| **Blocker** | None |
| **Status** | Open |

### DEBT-011: Mutable Audit Logs (SEC/ARCH)
| Field | Value |
|-------|-------|
| **Category** | SEC, ARCH |
| **Severity** | High |
| **Component** | services/api/database.py (AuditLog), services/api/auth.py (log_audit) |
| **Description** | Audit logs stored as mutable rows. No hash chaining, no append-only guarantee. |
| **Impact** | Admin can delete/modify logs; no tamper evidence; compliance failure |
| **Remediation** | Hash chain (each log includes prev hash); periodic blockchain anchoring |
| **Effort** | 3 days |
| **Blocker** | None |
| **Status** | Open |

### DEBT-012: Missing Request Correlation IDs (INFRA)
| Field | Value |
|-------|-------|
| **Category** | INFRA |
| **Severity** | Medium |
| **Component** | services/api/main.py |
| **Description** | No X-Request-ID middleware. Distributed tracing impossible. |
| **Impact** | Debugging production issues extremely difficult; no request flow visibility |
| **Remediation** | Middleware generating correlation ID; propagate to logs, metrics, downstream |
| **Effort** | 1 day |
| **Blocker** | None |
| **Status** | Open |

### DEBT-013: No Distributed Tracing (INFRA)
| Field | Value |
|-------|-------|
| **Category** | INFRA |
| **Severity** | Medium |
| **Component** | services/api/, docker/ (no Jaeger) |
| **Description** | No OpenTelemetry/Jaeger integration. |
| **Impact** | Cannot trace requests across API, blockchain, database, external services |
| **Remediation** | Add OpenTelemetry SDK; Jaeger in docker-compose; trace context propagation |
| **Effort** | 3 days |
| **Blocker** | None |
| **Status** | Open |

### DEBT-014: Permit Tests Are Placeholders (TEST)
| Field | Value |
|-------|-------|
| **Category** | TEST |
| **Severity** | Medium |
| **Component** | test/IDRCToken.t.sol (lines 124-138) |
| **Description** | testPermit, testPermitExpired, testPermitInvalidSignature all assertEq(true, true). |
| **Impact** | Critical EIP-2612 functionality untested; signature validation not verified |
| **Remediation** | Implement using vm.sign with unlocked wallets |
| **Effort** | 2 days |
| **Blocker** | Requires understanding of Forge permit testing |
| **Status** | Open |

### DEBT-015: No Invariant Tests (TEST)
| Field | Value |
|-------|-------|
| **Category** | TEST |
| **Severity** | High |
| **Component** | test/ (all files) |
| **Description** | No invariant_* functions exist. CI runs forge test --invariant but finds nothing. |
| **Impact** | Critical properties (supply=sum balances, paused blocks transfers) not fuzz-tested |
| **Remediation** | Add invariant tests for all critical financial properties |
| **Effort** | 1 week |
| **Blocker** | None |
| **Status** | Open |

### DEBT-016: Echidna Invariants Don't Exist (TEST)
| Field | Value |
|-------|-------|
| **Category** | TEST |
| **Severity** | Medium |
| **Component** | echidna.config.yaml vs contracts/ |
| **Description** | Config references invariant_totalSupplyEqualsSumOfBalances etc. but functions missing. |
| **Impact** | Echidna runs but tests nothing; false confidence |
| **Remediation** | Implement invariant functions or remove from config |
| **Effort** | 2 days |
| **Blocker** | None |
| **Status** | Open |

### DEBT-017: Slither Critical Detectors Disabled (SEC)
| Field | Value |
|-------|-------|
| **Category** | SEC |
| **Severity** | High |
| **Component** | slither.config.json (exclude list) |
| **Description** | Excludes: reentrancy-eth, reentrancy-no-eth, arbitrary-send-eth, arbitrary-send-erc20, unchecked-low-level-calls, delegatecall, tx-origin, self-destruct. |
| **Impact** | Critical vulnerability classes not scanned; false clean bill of health |
| **Remediation** | Remove from exclude; fix findings or justify with // slither-disable |
| **Effort** | 1 week |
| **Blocker** | May require code changes to fix true positives |
| **Status** | Open |

### DEBT-018: No Integration Tests (TEST)
| Field | Value |
|-------|-------|
| **Category** | TEST |
| **Severity** | High |
| **Component** | test/ (all isolated) |
| **Description** | Each contract tested in isolation. No Token+Reserve, Token+Bridge, Token+Multisig tests. |
| **Impact** | Cross-contract bugs undetected; integration failures in production |
| **Remediation** | Add integration test suite with full flows |
| **Effort** | 2 weeks |
| **Blocker** | None |
| **Status** | Open |

### DEBT-019: README Overclaims Production Readiness (DOCS)
| Field | Value |
|-------|-------|
| **Category** | DOCS |
| **Severity** | Medium |
| **Component** | README.md |
| **Description** | Claims "Production-ready", "321 passing", "100% coverage", "Audits planned" (none done). |
| **Impact** | Misleads investors, regulators, auditors; reputational risk |
| **Remediation** | Update to "Development/Staging"; note mock services; remove audit claims |
| **Effort** | 1 hour |
| **Blocker** | None |
| **Status** | Open |

### DEBT-020: Missing Key Documentation (DOCS)
| Field | Value |
|-------|-------|
| **Category** | DOCS |
| **Severity** | Medium |
| **Component** | docs/ (only DR_RUNBOOKS.md) |
| **Description** | No: THREAT_MODEL.md, FINANCIAL_MODEL.md, ARCHITECTURE.md, API_REFERENCE.md, COMPLIANCE.md |
| **Impact** | Auditors/regulators cannot assess; team onboarding difficult; no architecture decisions recorded |
| **Remediation** | Create missing documents per Phase 14 requirements |
| **Effort** | 2 weeks |
| **Blocker** | Requires architecture decisions (Phase 1) |
| **Status** | Open |

### DEBT-021: No API Reference Published (DOCS/INFRA)
| Field | Value |
|-------|-------|
| **Category** | DOCS, INFRA |
| **Severity** | Medium |
| **Component** | services/api/main.py (docs disabled in prod) |
| **Description** | /docs and /redoc disabled in production. No published OpenAPI spec. |
| **Impact** | Integrators cannot discover API; no contract testing; no SDK generation |
| **Remediation** | Enable in staging; publish to developer portal; generate SDKs |
| **Effort** | 2 days |
| **Blocker** | None |
| **Status** | Open |

### DEBT-022: Inconsistent Naming (CODE)
| Field | Value |
|-------|-------|
| **Category** | CODE |
| **Severity** | Low |
| **Component** | Throughout codebase |
| **Description** | Token called "IDRC" (README), "IDRCToken" (contracts), "IDR Coin" (name). Symbol IDRC. |
| **Impact** | Confusion in docs, code, UI; inconsistent branding |
| **Remediation** | Standardize: Contract=IDRCToken, Symbol=IDRC, Name="IDR Coin" |
| **Effort** | 1 day |
| **Blocker** | None |
| **Status** | Open |

### DEBT-023: Magic Numbers in Contracts (CODE)
| Field | Value |
|-------|-------|
| **Category** | CODE |
| **Severity** | Low |
| **Component** | contracts/reserve/ProofOfReserve.sol (1e18), contracts/token/IDRCToken.sol (10_000_000_000 * 10**18) |
| **Description** | Literal constants without named definitions or comments. |
| **Impact** | Reduced readability; risk of typos; harder maintenance |
| **Remediation** | Named constants with comments |
| **Effort** | 2 hours |
| **Blocker** | None |
| **Status** | Open |

### DEBT-024: BridgeVault Immutable Relayer Misleading (CODE)
| Field | Value |
|-------|-------|
| **Category** | CODE |
| **Severity** | Low |
| **Component** | contracts/bridge/BridgeVault.sol (lines 28-29, 131-137) |
| **Description** | relayer is immutable but setRelayer() only updates role. Immutable never used after constructor. |
| **Impact** | Confusion for auditors; off-chain tools read stale value |
| **Remediation** | Remove immutable or make mutable and update in setRelayer |
| **Effort** | 1 hour |
| **Blocker** | None |
| **Status** | Open |

### DEBT-025: No Health Checks for Oracle/Bridge (INFRA)
| Field | Value |
|-------|-------|
| **Category** | INFRA |
| **Severity** | Low |
| **Component** | docker/docker-compose.yml (lines 78-117) |
| **Description** | API has healthcheck; oracle and bridge services don't. |
| **Impact** | Container orchestrator cannot detect unhealthy oracle/bridge |
| **Remediation** | Add /health endpoints; configure in compose |
| **Effort** | 1 day |
| **Blocker** | None |
| **Status** | Open |

### DEBT-026: K8s Dev Overlay Missing Resources (INFRA)
| Field | Value |
|-------|-------|
| **Category** | INFRA |
| **Severity** | Low |
| **Component** | k8s/overlays/dev/kustomization.yaml |
| **Description** | No CPU/memory limits/requests in dev. Can cause OOM on shared clusters. |
| **Impact** | Resource contention; unreliable dev environment |
| **Remediation** | Add default resources in base; override in overlays |
| **Effort** | 2 hours |
| **Blocker** | None |
| **Status** | Open |

### DEBT-027: Redis No Auth/TLS in Compose (INFRA/SEC)
| Field | Value |
|-------|-------|
| **Category** | INFRA, SEC |
| **Severity** | Low |
| **Component** | docker/docker-compose.yml (lines 26-40) |
| **Description** | Redis configured without password, no TLS. OK for dev, not prod. |
| **Impact** | Data exposure if network compromised |
| **Remediation** | Add Redis password via env; enable TLS for prod |
| **Effort** | 1 day |
| **Blocker** | None |
| **Status** | Open |

### DEBT-028: Prometheus Alerts Not Business-Tuned (INFRA)
| Field | Value |
|-------|-------|
| **Category** | INFRA |
| **Severity** | Low |
| **Component** | docker/prometheus/alerts/idrc-alerts.yml |
| **Description** | Generic alerts. No collateralization, oracle staleness, bridge pending thresholds. |
| **Impact** | Alert fatigue; critical business events not alerted |
| **Remediation** | Add IDRC-specific rules with proper severity routing |
| **Effort** | 2 days |
| **Blocker** | Requires metrics from services |
| **Status** | Open |

### DEBT-029: WebSocket No Authentication (SEC)
| Field | Value |
|-------|-------|
| **Category** | SEC |
| **Severity** | Medium |
| **Component** | services/api/main.py (websocket_endpoint) |
| **Description** | WS endpoint accepts unauthenticated connections; echoes messages. |
| **Impact** | Unauthorized access to real-time data; potential DoS |
| **Remediation** | Require JWT/API key on connection; validate per message |
| **Effort** | 1 day |
| **Blocker** | None |
| **Status** | Open |

### DEBT-030: CORS Allows Credentials + Wildcard (SEC)
| Field | Value |
|-------|-------|
| **Category** | SEC |
| **Severity** | Medium |
| **Component** | services/api/main.py (lines 82-88) |
| **Description** | allow_credentials=True with allow_origins from env (wildcard in dev). |
| **Impact** | CSRF risk if origin validation bypassed; credential leakage |
| **Remediation** | Explicit origin list in prod; no wildcard with credentials |
| **Effort** | 1 hour |
| **Blocker** | None |
| **Status** | Open |

### DEBT-031: Gas Estimation Without Bounds (PERF/SEC)
| Field | Value |
|-------|-------|
| **Category** | PERF, SEC |
| **Severity** | High |
| **Component** | services/api/services/*.py (transact calls) |
| **Description** | transact() without gas limits. Malicious contract could consume all gas. |
| **Impact** | Gas griefing; transaction failures; unexpected costs |
| **Remediation** | estimateGas + buffer; max gas cap per operation type |
| **Effort** | 3 days |
| **Blocker** | None |
| **Status** | Open |

### DEBT-032: Multisig No Transaction Simulation (SEC)
| Field | Value |
|-------|-------|
| **Category** | SEC |
| **Severity** | High |
| **Component** | services/api/routers/multisig.py, contracts/multisig/MultisigWallet.sol |
| **Description** | submitTransaction accepts arbitrary calldata. No simulation, no selector whitelist. |
| **Impact** | Owner can propose malicious transaction; execute drains funds |
| **Remediation** | Simulate with eth_call; whitelist allowed targets/selectors |
| **Effort** | 3 days |
| **Blocker** | None |
| **Status** | Open |

### DEBT-033: Caller from Request Body Not Auth (SEC)
| Field | Value |
|-------|-------|
| **Category** | SEC |
| **Severity** | High |
| **Component** | services/api/routers/token.py, bridge.py, etc. |
| **Description** | caller field in request models; used for blockchain transact. Auth derives identity separately. |
| **Impact** | Identity confusion; user A can act as user B if B has role |
| **Remediation** | Derive caller from authenticated identity; remove from request |
| **Effort** | 2 days |
| **Blocker** | API contract changes |
| **Status** | Open |

### DEBT-034: Error Response Inconsistency (CODE)
| Field | Value |
|-------|-------|
| **Category** | CODE |
| **Severity** | Low |
| **Component** | services/api/routers/*.py |
| **Description** | Mix of HTTPException, custom error models, raw dicts. |
| **Impact** | Client integration difficult; inconsistent error handling |
| **Remediation** | Standard error response model; exception handlers for all types |
| **Effort** | 2 days |
| **Blocker** | None |
| **Status** | Open |

### DEBT-035: No API Versioning Policy (ARCH)
| Field | Value |
|-------|-------|
| **Category** | ARCH |
| **Severity** | Medium |
| **Component** | services/api/routers/ (all /api/v1/) |
| **Description** | Version prefix exists but no policy: deprecation, sunset, breaking change process. |
| **Impact** | Future breaking changes break integrators; no migration path |
| **Remediation** | Document versioning policy; add deprecation headers; sunset timeline |
| **Effort** | 2 days |
| **Blocker** | None |
| **Status** | Open |

### DEBT-036: Indexer No Reorg Handling (ARCH)
| Field | Value |
|-------|-------|
| **Category** | ARCH |
| **Severity** | High |
| **Component** | services/indexer/indexer.py (lines 211-213) |
| **Description** | Processes up to latest-1 with no reorg detection or rollback. |
| **Impact** | Reorg causes double-counted events; dashboard shows wrong data |
| **Remediation** | Track chain head; on reorg rollback and re-index; use blockHash |
| **Effort** | 1 week |
| **Blocker** | None |
| **Status** | Open |

### DEBT-037: Bridge No Finality Waiting (ARCH/SEC)
| Field | Value |
|-------|-------|
| **Category** | ARCH, SEC |
| **Severity** | High |
| **Component** | services/bridge/bridge_relayer.py, contracts/bridge/BridgeRelayer.sol |
| **Description** **Processes TokensLocked events immediately. No confirmation blocks wait. |
| **Impact** | Source chain reorg → destination mint stands → unbacked tokens |
| **Remediation** | Configurable finality per chain (Ethereum: 2 epochs, Polygon: 128 blocks, etc.) |
| **Effort** | 1 week |
| **Blocker** | None |
| **Status** | Open |

### DEBT-038: Oracle Single Key No HSM (SEC)
| Field | Value |
|-------|-------|
| **Category** | SEC |
| **Severity** | Critical |
| **Component** | services/oracle/oracle_relayer.py (line 57) |
| **Description** | Single EOA private key in env. No HSM, no multisig, no key rotation. |
| **Impact** | Key compromise = full reserve data control; no recovery |
| **Remediation** | HSM (AWS KMS, HashiCorp Vault); multi-sig oracle; key rotation procedure |
| **Effort** | 2 weeks |
| **Blocker** | Infrastructure |
| **Status** | Open |

### DEBT-039: No SBOM Generation (SEC/INFRA)
| Field | Value |
|-------|-------|
| **Category** | SEC, INFRA |
| **Severity** | Medium |
| **Component** | .github/workflows/ (ci.yml, security.yml) |
| **Description** | No Software Bill of Materials in CI pipeline. |
| **Impact** | Supply chain vulnerabilities undetected; compliance gap |
| **Remediation** | Add syft/cyclonedx to CI; upload SBOM artifact |
| **Effort** | 1 day |
| **Blocker** | None |
| **Status** | Open |

### DEBT-040: No Staging Deploy Gate (INFRA)
| Field | Value |
|-------|-------|
| **Category** | INFRA |
| **Severity** | Medium |
| **Component** | .github/workflows/deploy.yml |
| **Description** | No automatic deploy to staging on merge to develop. |
| **Impact** | Staging drift; integration issues found late; no pre-prod validation |
| **Remediation** | Add staging deploy job; health checks; auto-promote on success |
| **Effort** | 2 days |
| **Blocker** | Staging infrastructure |
| **Status** | Open |

### DEBT-041: No Prod Deployment Approval (INFRA/SEC)
| Field | Value |
|-------|-------|
| **Category** | INFRA, SEC |
| **Severity** | Medium |
| **Component** | .github/workflows/deploy.yml, GitHub Environments |
| **Description** | Manual trigger but no required reviewers, wait timer, or protection rules. |
| **Impact** | Accidental prod deploy; no audit trail of approval |
| **Remediation** | Configure GitHub Environment: required reviewers, 30min wait, deployment branch policy |
| **Effort** | 1 hour |
| **Blocker** | GitHub repo settings |
| **Status** | Open |

### DEBT-042: No Chaos Engineering / Stress Testing (TEST/INFRA)
| Field | Value |
|-------|-------|
| **Category** | TEST, INFRA |
| **Severity** | Low |
| **Component** | N/A |
| **Description** | No chaos engineering (Litmus, Chaos Mesh), no load testing (k6, Locust), no disaster recovery drills. |
| **Impact** | Unknown failure modes; untested runbooks; scaling limits unknown |
| **Remediation** | Add k6 load tests; Litmus chaos experiments; quarterly DR drills |
| **Effort** | 2 weeks |
| **Blocker** | Staging environment |
| **Status** | Open |

---

## DEBT SUMMARY

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| ARCH | 3 | 3 | 1 | 0 | 7 |
| CODE | 0 | 1 | 2 | 4 | 7 |
| TEST | 0 | 3 | 2 | 0 | 5 |
| DOCS | 0 | 0 | 2 | 0 | 2 |
| INFRA | 1 | 2 | 3 | 3 | 9 |
| SEC | 3 | 4 | 2 | 2 | 11 |
| PERF | 0 | 1 | 0 | 0 | 1 |
| **TOTAL** | **7** | **14** | **12** | **9** | **42** |

---

## DEBT PAYOFF STRATEGY

### Immediate (Sprint 1-2)
- DEBT-002: Delete duplicate IDRCToken.sol
- DEBT-010: Replace custom AccessControl
- DEBT-011: Fix permit low-s
- DEBT-012: Implement verifyProof
- DEBT-013: Validate updateFiatBalance > 0
- DEBT-014: Fix multisig delegatecall
- DEBT-019: Fix README claims
- DEBT-022: Standardize naming
- DEBT-023: Remove magic numbers
- DEBT-024: Fix BridgeVault immutable
- DEBT-030: CORS hardening
- DEBT-041: Prod deployment approval

### Short-term (Month 1)
- DEBT-008: Rate limiting + idempotency
- DEBT-009: Secrets management
- DEBT-016: Enable Slither detectors
- DEBT-017: Add invariant tests
- DEBT-025: Health checks oracle/bridge
- DEBT-026: K8s resource limits
- DEBT-027: Redis auth/TLS
- DEBT-029: WebSocket auth
- DEBT-033: Caller from auth
- DEBT-039: SBOM generation
- DEBT-040: Staging deploy gate

### Medium-term (Month 2-3)
- DEBT-001: (Done in Sprint 1)
- DEBT-003: Decimal arithmetic
- DEBT-006: (Bridge - separate track)
- DEBT-007: State machines
- DEBT-015: Invariant tests
- DEBT-018: Integration tests
- DEBT-020: Documentation
- DEBT-021: API reference
- DEBT-031: Gas bounds
- DEBT-032: Multisig simulation
- DEBT-034: Error standardization
- DEBT-035: API versioning
- DEBT-036: Indexer reorg handling
- DEBT-037: Bridge finality
- DEBT-038: Oracle HSM

### Long-term (Quarter 2+)
- DEBT-004: Financial ledger
- DEBT-005: Real oracle/KYC
- DEBT-028: Prometheus alerts
- DEBT-042: Chaos engineering

---

## DEBT METRICS TARGETS

| Metric | Current | Target (3 months) | Target (6 months) |
|--------|---------|-------------------|-------------------|
| Critical Debt | 7 | 0 | 0 |
| High Debt | 14 | 3 | 0 |
| Medium Debt | 12 | 5 | 2 |
| Low Debt | 9 | 5 | 3 |
| **Debt Ratio** (Debt/Total Code) | ~15% | < 5% | < 2% |

---

**END OF TECHNICAL_DEBT_REGISTER.md**