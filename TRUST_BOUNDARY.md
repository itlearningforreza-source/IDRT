# TRUST_BOUNDARY.md
# IDRC Trust Boundaries
**Version:** 2.0
**Date:** 2026-11-18
**Phase:** 1 - System Architecture Reconstruction
**Purpose:** Explicitly document every trust assumption and boundary in the system

---

## 1. TRUST BOUNDARY DEFINITION

A **Trust Boundary** is a logical separation where:
- Data crosses from one trust domain to another
- Different security policies apply on each side
- Validation/verification is required at the boundary
- Compromise on one side should not automatically compromise the other

Each boundary has:
- **Boundary ID**: Unique identifier
- **Source Domain**: Where data originates
- **Destination Domain**: Where data is consumed
- **Trust Assumption**: What we trust about the source
- **Verification Mechanism**: How we verify before trusting
- **Failure Mode**: What happens if verification fails

---

## 2. TRUST BOUNDARY CATALOG

### TB-01: User ↔ API Gateway
| Field | Value |
|-------|-------|
| **Source** | External User (Untrusted) |
| **Destination** | API Gateway (Semi-Trusted) |
| **Data Flow** | HTTPS requests (mint, burn, bridge, KYC, queries) |
| **Trust Assumption** | User possesses valid credentials (JWT/API Key) |
| **Verification** | 1. TLS 1.3 termination<br>2. JWT signature + expiry + claims<br>3. API Key hash comparison<br>4. Rate limit check<br>5. Input schema validation (Pydantic) |
| **Failure Mode** | 401/403/429 response; Audit log entry; Correlation ID tracked |
| **Residual Risk** | Credential theft → impersonation (mitigated: short JWT, MFA for privileged) |

### TB-02: API Gateway ↔ Domain Services (Internal)
| Field | Value |
|-------|-------|
| **Source** | API Gateway (Trusted Internal) |
| **Destination** | Domain Services (Trusted Internal) |
| **Data Flow** | Internal gRPC/HTTP calls; Command/Query objects |
| **Trust Assumption** | Gateway has validated auth; caller identity derived from auth context |
| **Verification** | 1. mTLS between services<br>2. Service-to-service JWT (short-lived)<br>3. Caller identity passed via header (not request body)<br>4. Idempotency key validation |
| **Failure Mode** | 500 error; Circuit breaker; Alert; Request rejected |
| **Residual Risk** | Service mesh compromise → lateral movement (mitigated: zero trust network) |

### TB-03: Domain Services ↔ Database
| Field | Value |
|-------|-------|
| **Source** | Domain Services (Trusted) |
| **Destination** | PostgreSQL (Trusted Infrastructure) |
| **Data Flow** | SQL queries via SQLAlchemy asyncpg; Parameterized statements |
| **Trust Assumption** | Service has valid DB credentials; Network allows connection |
| **Verification** | 1. Parameterized queries (no SQL injection)<br>2. Read/write role separation<br>3. Row-level security for PII<br>4. Connection pooling with limits<br>5. Audit trigger on sensitive tables |
| **Failure Mode** | Transaction rollback; Alert; Circuit breaker; Dead letter queue |
| **Residual Risk** | DB credential leak → data access (mitigated: Vault, rotation, IAM) |

### TB-04: Domain Services ↔ Blockchain Adapter
| Field | Value |
|-------|-------|
| **Source** | Domain Services (Trusted) |
| **Destination** | Blockchain Adapter (Trusted Internal) |
| **Data Flow** | Contract calls (read/write); Event subscriptions; Transaction building |
| **Trust Assumption** | Adapter correctly encodes/decodes; RPC provider honest |
| **Verification** | 1. Multi-RPC provider consensus (reads)<br>2. Simulation before write (eth_call)<br>3. Gas estimation with bounds<br>4. Nonce management with gap detection<br>5. Receipt verification (status=1)<br>6. Confirmation wait (configurable per chain) |
| **Failure Mode** | Retry with backoff; Alert; Manual intervention queue; Idempotency key prevents duplicate |
| **Residual Risk** | RPC provider malicious → wrong data (mitigated: multi-RPC, light client verification for critical reads) |

### TB-05: Blockchain Adapter ↔ Smart Contracts (On-Chain)
| Field | Value |
|-------|-------|
| **Source** | Blockchain Adapter (External) |
| **Destination** | Smart Contracts (Immutable Code) |
| **Data Flow** | Signed transactions; Event logs; State reads |
| **Trust Assumption** | Contract code = verified bytecode; EVM executes correctly |
| **Verification** | 1. Contract verification on explorer (source match)<br>2. Formal verification proofs<br>3. Upgrade timelock (48h)<br>4. Storage layout compatibility check<br>5. Emergency pause via multisig<br>6. Event indexing for off-chain reconciliation |
| **Failure Mode** | Transaction revert; Upgrade cancellation; Emergency pause; State reconstruction from events |
| **Residual Risk** | Undiscovered contract bug → loss (mitigated: audits, formal verification, bug bounty) |

### TB-06: Oracle Relayer ↔ ProofOfReserve Contract
| Field | Value |
|-------|-------|
| **Source** | Oracle Relayer (External - Semi-Trusted) |
| **Destination** | ProofOfReserve Contract (Critical) |
| **Data Flow** | updateFiatBalance(balance) transactions |
| **Trust Assumption** | Oracle submits accurate, timely, signed bank attestations |
| **Verification** | 1. ORACLE_ROLE required (threshold signature in v2)<br>2. Attestation verification: sig + cert + freshness<br>3. Balance > 0 check<br>4. Staleness monitor (alert if > 1h)<br>5. Circuit breaker: stale → pause minting<br>6. Multi-oracle threshold (v2: 3-of-5) |
| **Failure Mode** | Revert transaction; Alert P1; Manual review; Emergency pause |
| **Residual Risk** | Oracle collusion → fake balance (mitigated: threshold, staking/slashing, legal contracts) |

### TB-07: Bridge Relayer ↔ Bridge Contracts
| Field | Value |
|-------|-------|
| **Source** | Bridge Relayer (External - Semi-Trusted) |
| **Destination** | BridgeVault / BridgeRelayer Contracts (Critical) |
| **Data Flow** | lock() on source; relay() on destination; release() on source |
| **Trust Assumption** | Relayer correctly processes events; No unauthorized minting |
| **Verification (Current - HIGH RISK)** | 1. RELAYER_ROLE / RELAYER_ADMIN_ROLE (single key)<br>2. Nonce deduplication<br>3. Event-based triggering |
| **Verification (Target - v2)** | 1. Decentralized network (LayerZero/Axelar/MPC)<br>2. Light client verification / ZK proofs<br>3. Finality confirmation per chain<br>4. Rate limits per chain<br>5. Circuit breaker on anomaly |
| **Failure Mode** | Revert; Alert P1; Pause bridge; Investigate unauthorized mints |
| **Residual Risk** | Single key compromise = unlimited mint (CRITICAL - must fix pre-mainnet) |

### TB-08: Bank Custodian ↔ Oracle Relayer
| Field | Value |
|-------|-------|
| **Source** | Bank Custodian (External - Trusted via Legal) |
| **Destination** | Oracle Relayer (Trusted Internal) |
| **Data Flow** | BI-FAST/ISO 20022 API; Signed attestations |
| **Trust Assumption** | Bank provides accurate, timely, cryptographically signed balance data |
| **Verification** | 1. mTLS + certificate pinning<br>2. Attestation signature verification (bank cert)<br>3. Timestamp freshness (< 5 min)<br>4. Balance consistency checks<br>5. Legal contract with audit rights<br>6. Regulatory supervision (Bank Indonesia) |
| **Failure Mode** | Alert P1; Fallback to last known good; Manual verification; Legal escalation |
| **Residual Risk** | Bank API compromise / insider (mitigated: multi-bank, threshold oracles, legal liability) |

### TB-09: KYC/AML Providers ↔ Compliance Engine
| Field | Value |
|-------|-------|
| **Source** | KYC/AML Providers (External - Trusted via Contract) |
| **Destination** | Compliance Engine (Trusted Internal) |
| **Data Flow** | eKYC results; Sanctions screening hits; Risk scores |
| **Trust Assumption** | Providers perform accurate screening per regulatory standards |
| **Verification** | 1. API authentication (mTLS + API keys)<br>2. Response schema validation<br>3. Multiple provider consensus (primary + fallback)<br>4. Manual review queue for hits<br>5. Audit trail of all screening decisions<br>6. Provider SLA monitoring |
| **Failure Mode** | Degraded mode: queue for manual review; Alert; Fail closed (reject) |
| **Residual Risk** | Provider false negative (mitigated: multiple providers, periodic re-screening) |

### TB-10: Admin/Operator ↔ Multisig
| Field | Value |
|-------|-------|
| **Source** | Human Operators (External - Trusted via Legal/HR) |
| **Destination** | MultisigWallet Contract (Critical Governance) |
| **Data Flow** | Hardware wallet signatures; Transaction proposals |
| **Trust Assumption** | Signers are authorized, uncompromised, acting in good faith |
| **Verification** | 1. Hardware wallet (Ledger/Trezor) required<br>2. Threshold signatures (2-of-3, 3-of-5)<br>3. Timelock on sensitive ops (48h upgrade, 24h role change)<br>4. Transaction simulation before confirm<br>5. Audit log of all proposals/confirmations/executions<br>6. Legal agreements with signers |
| **Failure Mode** | Insufficient confirmations → transaction expires; Emergency council override |
| **Residual Risk** | Signer collusion / coercion (mitigated: geographic distribution, legal, threshold) |

### TB-11: Indexer ↔ Blockchain
| Field | Value |
|-------|-------|
| **Source** | Blockchain (External - Immutable) |
| **Destination** | Indexer Service (Trusted Internal) |
| **Data Flow** | eth_getLogs; Block headers; Traces |
| **Trust Assumption** | RPC provider returns correct, complete data |
| **Verification** | 1. Multi-RPC consensus<br>2. Block hash verification<br>3. Reorg detection (block hash mismatch)<br>4. Rollback and re-index on reorg<br>5. Gap detection in block sequence |
| **Failure Mode** | Pause indexing; Alert; Manual reorg resolution; Data integrity check |
| **Residual Risk** | RPC censorship / wrong data (mitigated: multiple providers, light client) |

### TB-12: Monitoring ↔ All Services
| Field | Value |
|-------|-------|
| **Source** | All Services (Trusted Internal) |
| **Destination** | Prometheus/Loki/Jaeger (Trusted Infrastructure) |
| **Data Flow** | Metrics (/metrics); Logs (stdout→Promtail); Traces (OTLP) |
| **Trust Assumption** | Services emit accurate telemetry |
| **Verification** | 1. Exemplar sampling for trace-metric correlation<br>2. Log sanitization (no PII/secrets)<br>3. Metric bounds checking (alert on impossible values)<br>4. Synthetic monitoring validates pipeline |
| **Failure Mode** | Alert on pipeline failure; Fallback logging; Graceful degradation |
| **Residual Risk** | Telemetry manipulation to hide attacks (mitigated: immutable audit log separate) |

---

## 3. TRUST BOUNDARY MATRIX

| Boundary | Trust Level | Verification Strength | Criticality | Review Frequency |
|----------|-------------|----------------------|-------------|------------------|
| TB-01: User→API | Low→Medium | Strong (auth + validation) | High | Quarterly |
| TB-02: API→Services | Medium→High | Strong (mTLS + identity) | High | Quarterly |
| TB-03: Services→DB | High→High | Strong (params + RLS) | High | Quarterly |
| TB-04: Services→BC Adapter | High→High | Medium (sim + multi-RPC) | Critical | Monthly |
| TB-05: Adapter→Contracts | External→Immutable | Strong (verify + timelock) | Critical | Per upgrade |
| TB-06: Oracle→Reserve | Medium→Critical | Medium (single key) → Strong (threshold) | **Critical** | Monthly |
| TB-07: Relayer→Bridge | Medium→Critical | **Weak (single key)** → Strong (decentralized) | **Critical** | **Pre-mainnet** |
| TB-08: Bank→Oracle | Legal→Trusted | Strong (mTLS + sigs + legal) | Critical | Quarterly |
| TB-09: KYC→Compliance | Contract→Trusted | Strong (multi-provider) | High | Quarterly |
| TB-10: Human→Multisig | Legal→Critical | Strong (HW wallet + threshold + timelock) | Critical | Quarterly |
| TB-11: Chain→Indexer | Immutable→Trusted | Medium (multi-RPC + reorg) | High | Monthly |
| TB-12: Services→Monitoring | High→High | Medium (sanitization) | Medium | Quarterly |

---

## 4. TRUST ASSUMPTIONS REGISTER

| Assumption ID | Assumption | Boundary | Validation | If False |
|---------------|------------|----------|------------|----------|
| TA-001 | Users protect their credentials | TB-01 | MFA encouragement; Session monitoring | Account takeover → rate limit, alert |
| TA-002 | API Gateway correctly derives identity | TB-02 | Integration tests; Code review | Privilege escalation → audit log detection |
| TA-003 | Services don't have SQL injection | TB-03 | SAST; Code review; Parameterized queries | Data breach → RLS limits exposure |
| TA-004 | RPC providers return honest data | TB-04, TB-11 | Multi-RPC consensus; Light client (future) | Wrong state → reconciliation alert |
| TA-005 | Contract bytecode matches source | TB-05 | Explorer verification; CI check | Malicious upgrade → timelock prevents |
| TA-006 | Oracle submits accurate bank data | TB-06 | Attestation verification; Multi-oracle | Fake reserve → circuit breaker pause |
| TA-007 | Bridge relayer processes correctly | TB-07 | **Single key - INSUFFICIENT** | **Unlimited mint - CRITICAL** |
| TA-008 | Bank provides accurate balances | TB-08 | Legal contract; Audit rights; Multi-bank | Wrong reserve → reconciliation alert |
| TA-009 | KYC providers screen accurately | TB-09 | Multi-provider; Manual review queue | Sanctions miss → compliance violation |
| TA-010 | Multisig signers are honest | TB-10 | Threshold; Timelock; Legal agreements | Governance attack → emergency pause |
| TA-011 | Monitoring pipeline is honest | TB-12 | Separate audit log; Synthetic checks | Blind to attacks → audit log detection |

---

## 5. BOUNDARY EVOLUTION ROADMAP

### Current State (v1.0 - Development)
- TB-06: Single oracle key ❌
- TB-07: Single relayer key ❌ **CRITICAL**
- TB-05: Upgrade timelock in config only ❌
- TB-01: Caller in request body ❌

### Target State (v2.0 - Pre-Mainnet)
- TB-06: 3-of-5 threshold oracle ✅
- TB-07: LayerZero/Axelar integration ✅
- TB-05: TimelockController enforced ✅
- TB-01: Caller from auth context ✅

### Future State (v3.0 - Institutional)
- TB-04: Light client verification for critical reads
- TB-06: ZK-proof reserve attestations
- TB-07: Intent-based bridge (ERC-7683)
- TB-10: MPC multisig with social recovery

---

## 6. VERIFICATION CHECKLIST PER BOUNDARY

Each boundary must pass before mainnet:

- [ ] **TB-01**: Rate limiting; Idempotency; Auth derivation from context; CORS hardened
- [ ] **TB-02**: mTLS; Service identity; No caller in request body; Correlation IDs
- [ ] **TB-03**: Parameterized queries; RLS on PII; Read/write roles; Audit triggers
- [ ] **TB-04**: Multi-RPC; Simulation; Gas bounds; Nonce management; Confirmation waits
- [ ] **TB-05**: Verified contracts; TimelockController; Storage layout check; Emergency pause
- [ ] **TB-06**: Threshold oracle; Attestation verification; Circuit breaker; Staleness monitor
- [ ] **TB-07**: Decentralized bridge; Finality verification; Rate limits; Nonce deduplication
- [ ] **TB-08**: mTLS + pinning; Attestation format; Legal contract; Multi-bank
- [ ] **TB-09**: Multi-provider; Fail closed; Manual review; Audit trail
- [ ] **TB-10**: Hardware wallets; Threshold; Timelock; Simulation; Legal agreements
- [ ] **TB-11**: Reorg handling; Rollback; Gap detection; Multi-RPC
- [ ] **TB-12**: Log sanitization; Exemplars; Synthetic monitoring; Separate audit log

---

**END OF TRUST_BOUNDARY.md**