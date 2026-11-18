# ARCHITECTURE_ASSESSMENT.md
# IDRT System Architecture Assessment
**Date:** 2026-11-18
**Phase:** 0 - Repository Forensics
**Status:** ASSESSMENT COMPLETE - MAJOR REDESIGN REQUIRED

---

## 1. CURRENT ARCHITECTURE OVERVIEW

### 1.1 High-Level Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           IDRC ECOSYSTEM (CURRENT)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐  │
│  │   IDRCToken  │◄───│  UUPS Proxy  │◄───│ ProxyAdmin   │◄───│ Multisig │  │
│  │  (Core ERC20)│    │  (Upgrade)   │    │  (Owner)     │    │  (Gov)   │  │
│  └──────┬───────┘    └──────────────┘    └──────────────┘    └──────────┘  │
│         │                                                                   │
│         ▼                                                                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐  │
│  │ProofOfReserve│    │ BridgeVault  │    │BridgeRelayer │    │AccessCtrl│  │
│  │ (Oracle+Audit)│    │ (Lock/Mint)  │    │  (Relay)     │    │ (Custom) │  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘    └──────────┘  │
│         │                   │                   │                           │
│         ▼                   ▼                   ▼                           │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    Cross-Chain Networks                              │  │
│  │  Ethereum │ Polygon │ Arbitrum │ Optimism │ Base │ BSC │ ...        │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐  │
│  │   FastAPI    │    │   Indexer    │    │   Oracle     │    │  Bridge  │  │
│  │   Backend    │    │   Service    │    │  Relayer     │    │  Relayer │  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘    └──────────┘  │
│         │                   │                   │                           │
│         ▼                   ▼                   ▼                           │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │              PostgreSQL + Redis + Prometheus/Grafana                 │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Domain Boundaries (Current)

| Domain | On-Chain | Off-Chain | Status |
|--------|----------|-----------|--------|
| Token Protocol | IDRCToken, UUPSProxy | TokenService | ✅ Defined |
| Reserve Management | ProofOfReserve | ReserveService, OracleRelayer | ⚠️ Mock oracle |
| Issuance Engine | mint/issuerBurn | API /mint, /burn | ⚠️ No state machine |
| Redemption Engine | burn/issuerBurn | API /burn, /user-burn | ⚠️ No state machine |
| Financial Ledger | ❌ **MISSING** | ❌ **MISSING** | ❌ **CRITICAL GAP** |
| Blockchain Integration | Contracts | BlockchainManager, Web3.py | ✅ Basic |
| Oracle & Attestation | ProofOfReserve | OracleRelayer (mock) | ❌ Mock |
| Governance | MultisigWallet, ProxyAdmin | MultisigService | ✅ Basic |
| Bridge Infrastructure | BridgeVault, BridgeRelayer | BridgeService, BridgeRelayer | ⚠️ Centralized |
| Compliance | ❌ **MISSING** | KYCAMLService (mock) | ❌ Mock |
| Monitoring | Events | MonitorService, Indexer | ✅ Basic |
| API Gateway | N/A | FastAPI + Nginx | ✅ Complete |
| User Dashboard | N/A | Static files mount | ❌ Not built |

---

## 2. ARCHITECTURAL DEFICIENCIES

### 2.1 Critical: Missing Financial Ledger Domain

**Current State:** No double-entry ledger exists. Financial state tracked only via:
- On-chain `totalSupply()`
- Off-chain `fiatBalanceIdr()` in ProofOfReserve
- API token events (indexed)

**Required:** Complete double-entry ledger with:
- Chart of accounts (Customer Liabilities, Fiat Reserves, Operational Cash, Fees, Suspense, Encumbered)
- Journal entries for every financial event
- Immutable posted records with reversal entries
- Reconciliation between on-chain supply, off-chain liability ledger, bank statements

### 2.2 Critical: Trust Boundary Violations

| Boundary | Current Implementation | Violation |
|----------|------------------------|-----------|
| On-chain ↔ Off-chain Financial State | API trusts `caller` from request body | Caller identity not derived from auth |
| Oracle ↔ Reserve | Single oracle key, no attestation | No cryptographic proof of bank balance |
| Bridge Source ↔ Destination | Relayer trusts events blindly | No message verification, no finality |
| Admin ↔ Operations | Multisig holds ALL roles | No separation of duties |
| Compliance ↔ Transactions | Mock KYC/AML | No real screening |

### 2.3 High: Centralized Bridge Architecture

**Current:** Single relayer with `RELAYER_ADMIN_ROLE` controls all cross-chain minting.

**Required:** 
- Decentralized bridge (LayerZero, Axelar, Wormhole, or custom MPC)
- Light client verification or ZK proofs
- Finality handling per chain
- Rate limits and circuit breakers

### 2.4 High: Custom AccessControl vs OpenZeppelin

**Current:** 123-line custom reimplementation of OZ AccessControl.

**Risk:** 
- Unaudited code in critical path
- Missing `getRoleMember`, `getRoleMemberCount`
- No `AccessControlDefaultAdminRules` protection
- Diverges from OZ with each version

**Remediation:** Migrate to `@openzeppelin/contracts/access/AccessControl.sol`

### 2.5 High: No Issuance/Redemption State Machines

**Current:** Direct `mint`/`burn` calls with role checks only.

**Required State Machines:**

```
ISSUANCE: REQUESTED → DEPOSIT_PENDING → DEPOSIT_VERIFIED → APPROVED → MINTED
                    ↓              ↓                   ↓          ↓
                 REJECTED      EXPIRED            REJECTED   FAILED

REDEMPTION: REQUESTED → VALIDATED → BURN_PENDING → BURN_CONFIRMED → FIAT_PAYOUT_PENDING → COMPLETED
                    ↓           ↓            ↓              ↓                  ↓
                 REJECTED    EXPIRED      REJECTED        FAILED             REFUND/RECOVERY
```

---

## 3. DATA FLOW ANALYSIS

### 3.1 Current Data Flows

| Flow | Source | Destination | Validation | Gap |
|------|--------|-------------|------------|-----|
| Mint | API /mint (MINTER_ROLE) | IDRCToken.mint | Role only | No deposit verification |
| Burn | API /burn (BURNER_ROLE) | IDRCToken.issuerBurn | Role only | No payout confirmation |
| User Burn | API /user-burn | IDRCToken.burn | Caller=from | No redemption workflow |
| Oracle Update | OracleRelayer (mock) | ProofOfReserve.updateFiatBalance | Oracle role | **Mock data** |
| Audit Proof | API /audit-proof (AUDITOR_ROLE) | ProofOfReserve.submitAuditProof | Role only | Hash only, no verification |
| Bridge Lock | BridgeRelayer (RELAYER_ROLE) | BridgeVault.lock | Role only | Burns tokens |
| Bridge Relay | BridgeRelayer (RELAYER_ADMIN) | BridgeRelayer.relay | Role only | **No verification** |
| Bridge Release | BridgeRelayer (RELAYER_ROLE) | BridgeVault.release | Role only | Mints tokens |

### 3.2 Required Data Flows (Institutional Grade)

```
DEPOSIT FLOW:
User → Bank (BI-FAST) → Bank Webhook → Compliance Check → 
Deposit Record Created → Issuance Request → Multisig Approval → 
Mint IDRC → Ledger Entry (Dr Bank / Cr Customer Liability) → 
Notification → Reconciliation

REDEMPTION FLOW:
User → API /redeem → Compliance Check → Redemption Request →
Multisig Approval → Burn IDRC → Ledger Entry (Dr Customer Liability / Cr Bank) →
Bank Payout (BI-FAST) → Payout Confirmation → Ledger Entry (Dr Bank / Cr Operational) →
Reconciliation

BRIDGE FLOW (Lock-Mint):
Source: User → BridgeVault.lock (burn) → Event → Relayer Network → 
Verify (Light Client/ZK) → Destination: BridgeRelayer.relay (mint) → 
Reconciliation (Locked = Minted across chains)

BRIDGE FLOW (Burn-Release):
Source: User → BridgeVault.lock (burn) → Event → Relayer Network →
Verify → Destination: BridgeVault.release (mint) → Reconciliation
```

---

## 4. COMPONENT COUPLING ANALYSIS

### 4.1 Current Coupling (High = Bad)

| Component A | Component B | Coupling | Issue |
|-------------|-------------|----------|-------|
| IDRCToken | AccessControl | **High** | Inherits custom impl |
| IDRCToken | UUPSUpgradeable | Medium | Standard OZ |
| ProofOfReserve | IDRCToken | **High** | Direct supply coupling |
| BridgeVault | IDRCToken | **High** | Direct burn/mint calls |
| BridgeRelayer | BridgeVault | Medium | Event-based |
| API Services | BlockchainManager | **High** | Direct contract calls |
| OracleRelayer | ProofOfReserve | **High** | Single key, direct write |
| KYCAMLService | API | Low | Not integrated |

### 4.2 Required Decoupling

1. **Token ↔ Reserve:** Reserve should not depend on token supply directly. Use oracle/supply feed.
2. **Bridge ↔ Token:** Bridge should use interface, not concrete `IDRCToken`.
3. **API ↔ Blockchain:** Introduce adapter pattern for testability.
4. **Oracle ↔ Reserve:** Oracle should submit signed attestations, not raw balances.

---

## 5. SCALABILITY & PERFORMANCE ASSESSMENT

| Component | Current Capacity | Bottleneck | Scaling Path |
|-----------|------------------|------------|--------------|
| IDRCToken | ~100 TPS (Ethereum) | L1 gas | L2 deployment |
| ProofOfReserve | Single oracle | Centralized | Multi-oracle, threshold |
| Bridge | Single relayer | Centralized | Decentralized network |
| API | 4 gunicorn workers | Sync DB calls | Async, connection pooling |
| Indexer | Polling 10s intervals | RPC rate limits | WebSocket, parallel chains |
| Database | Single PostgreSQL | Write throughput | Read replicas, partitioning |

---

## 6. UPGRADEABILITY & GOVERNANCE

### 6.1 Current Upgrade Path

```
Multisig (2-of-3) → ProxyAdmin → UUPSProxy → New Implementation
```

**Issues:**
- No timelock on upgrades (48h in config, not enforced in code)
- Multisig holds UPGRADER_ROLE AND DEFAULT_ADMIN_ROLE - no separation
- No emergency cancellation mechanism
- `_authorizeUpgrade` only checks code exists, not storage compatibility

### 6.2 Required Governance Framework

- TimelockController for all sensitive operations
- Role separation: Admin ≠ Upgrader ≠ Minter ≠ Pauser
- Emergency pause with multisig + security council
- Upgrade validation: storage layout check, test suite pass

---

## 7. MONITORING & OBSERVABILITY GAPS

| Capability | Current | Required |
|------------|---------|----------|
| Metrics | Prometheus (basic) | Business + technical SLIs |
| Logs | Loki + structured | Audit trail with hash chaining |
| Traces | ❌ None | Distributed tracing (Jaeger) |
| Alerts | MonitorService (stubbed) | P1/P2/P3 with runbooks |
| Dashboards | Grafana (3 boards) | Full operational visibility |
| Synthetic Monitoring | ❌ None | API health, bridge health, oracle freshness |

---

## 8. DISASTER RECOVERY READINESS

| Scenario | Current Capability | Gap |
|----------|-------------------|-----|
| Private Key Compromise | Multisig rotation | No documented procedure |
| Oracle Failure | Pause reserve updates | No circuit breaker |
| Bridge Compromise | Pause bridge | No fund recovery |
| Database Corruption | PostgreSQL PITR | No tested restore |
| Smart Contract Bug | UUPS upgrade | 48h timelock not enforced |
| Regulatory Action | Blacklist function | No legal hold process |

---

## 9. RECOMMENDED TARGET ARCHITECTURE

### 9.1 Logical Domains (Clean Architecture)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         IDRC TARGET ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        APPLICATION LAYER                            │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐  │   │
│  │  │  Issuance   │ │ Redemption  │ │  Bridge     │ │ Compliance  │  │   │
│  │  │  Engine     │ │  Engine     │ │  Engine     │ │  Engine     │  │   │
│  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘  │   │
│  └─────────┼───────────────┼───────────────┼───────────────┼─────────┘   │
│            │               │               │               │             │
│  ┌─────────┴───────────────┴───────────────┴───────────────┴─────────┐   │
│  │                        DOMAIN SERVICES LAYER                       │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐  │   │
│  │  │   Token     │ │  Reserve    │ │  Ledger     │ │ Governance  │  │   │
│  │  │  Protocol   │ │ Management  │ │  Service    │ │  Service    │  │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│            │               │               │               │             │
│  ┌─────────┴───────────────┴───────────────┴───────────────┴─────────┐   │
│  │                      INFRASTRUCTURE LAYER                          │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐  │   │
│  │  │ Blockchain  │ │   Oracle    │ │  Database   │ │  Message    │  │   │
│  │  │  Adapter    │ │  Adapter    │ │  (PostgreSQL)│ │  Queue      │  │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Key Architectural Decisions (ADRs Needed)

| ADR | Decision | Status |
|-----|----------|--------|
| ADR-001 | Use OpenZeppelin AccessControl vs custom | **REQUIRED** |
| ADR-002 | Double-entry ledger implementation | **REQUIRED** |
| ADR-003 | Bridge architecture: lock-mint vs burn-release vs native | **REQUIRED** |
| ADR-004 | Oracle: single vs multi vs threshold vs ZK | **REQUIRED** |
| ADR-005 | Upgrade governance: timelock + role separation | **REQUIRED** |
| ADR-006 | Financial precision: integer (wei) vs fixed-point decimal | **REQUIRED** |
| ADR-007 | Compliance integration: sync vs async, build vs buy | **REQUIRED** |
| ADR-008 | Database: migrations, partitioning, read replicas | **REQUIRED** |

---

## 10. ARCHITECTURE SCORECARD

| Dimension | Score (1-5) | Notes |
|-----------|-------------|-------|
| Separation of Concerns | 2 | Domains bleed into each other |
| Trust Minimization | 1 | Centralized oracle, bridge, admin |
| Financial Integrity | 1 | No ledger, no reconciliation |
| Upgrade Safety | 2 | UUPS but no timelock enforcement |
| Observability | 2 | Basic metrics, no tracing |
| Disaster Recovery | 1 | No tested procedures |
| Compliance Readiness | 1 | Mock services only |
| Scalability | 2 | L1 only, no L2 strategy |
| **OVERALL** | **1.5** | **Not production ready** |

---

## 11. IMMEDIATE ARCHITECTURAL REMEDIATIONS

### Phase 1 (Critical - Block Mainnet)
1. Replace custom AccessControl with OpenZeppelin
2. Implement double-entry financial ledger
3. Add issuance/redemption state machines
4. Remove mock oracle - define oracle interface
5. Add rate limiting + idempotency to API
6. Fix bridge: add message verification or use proven bridge
7. Enforce timelocks in code (not just config)
8. Separate multisig roles (admin ≠ upgrader ≠ minter)

### Phase 2 (High - Pre-Launch)
1. Implement compliance integration (real KYC/AML)
2. Add distributed tracing
3. Build disaster recovery runbooks + test them
4. Add circuit breakers for oracle/bridge
5. Implement database migrations (alembic)
6. Add financial reconciliation jobs

### Phase 3 (Medium - Post-Launch)
1. Migrate to L2 for scalability
2. Decentralize bridge (LayerZero/Axelar)
3. Add ZK-proof reserve verification
4. Implement advanced monitoring (anomaly detection)

---

**END OF ARCHITECTURE_ASSESSMENT.md**