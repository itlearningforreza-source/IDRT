# SYSTEM_ARCHITECTURE.md
# IDRC System Architecture
**Version:** 2.0 (Post-Forensics Redesign)
**Date:** 2026-11-18
**Phase:** 1 - System Architecture Reconstruction
**Status:** DRAFT - For Review
**Supersedes:** README.md architecture section

---

## 1. ARCHITECTURAL PRINCIPLES

| Principle | Application |
|-----------|-------------|
| **Security First** | No feature without threat model; defense in depth; least privilege |
| **Financial Correctness** | Double-entry ledger; integer arithmetic; reconciliation; immutable audit trail |
| **Explicit Trust Boundaries** | Document every trust assumption; minimize trusted components |
| **Separation of Concerns** | Domain-driven design with clear boundaries; no circular dependencies |
| **Fail-Safe Defaults** | Pause on anomaly; reject on ambiguity; explicit recovery procedures |
| **Auditability** | Every financial event traceable; hash-chained logs; regulatory export |
| **Upgrade Safety** | Timelocked upgrades; storage layout validation; emergency cancellation |
| **Operational Simplicity** | Modular monolith first; extract services only when measured need exists |

---

## 2. LOGICAL DOMAINS (Bounded Contexts)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              IDRC ECOSYSTEM v2.0                                    │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         APPLICATION LAYER (Use Cases)                       │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │   │
│  │  │  Issuance    │ │ Redemption   │ │  Bridge      │ │ Compliance   │       │   │
│  │  │  Engine      │ │  Engine      │ │  Engine      │ │  Engine      │       │   │
│  │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘       │   │
│  └─────────┼────────────────┼────────────────┼────────────────┼──────────────┘   │
│            │                │                │                │                  │
│  ┌─────────┴────────────────┴────────────────┴────────────────┴──────────────┐   │
│  │                        DOMAIN SERVICES LAYER                               │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │   │
│  │  │   Token      │ │  Reserve     │ │   Ledger     │ │ Governance   │      │   │
│  │  │  Protocol    │ │ Management   │ │  Service     │ │  Service     │      │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘      │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│            │                │                │                │                  │
│  ┌─────────┴────────────────┴────────────────┴────────────────┴──────────────┐   │
│  │                      INFRASTRUCTURE ADAPTERS                               │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │   │
│  │  │ Blockchain   │ │   Oracle     │ │  Database    │ │  Message     │      │   │
│  │  │  Adapter     │ │  Adapter     │ │ (PostgreSQL) │ │  Queue       │      │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘      │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│            │                │                │                │                  │
│  ┌─────────┴────────────────┴────────────────┴────────────────┴──────────────┐   │
│  │                      EXTERNAL SYSTEMS                                      │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │   │
│  │  │ Ethereum │ │ Polygon  │ │  Bank    │ │  KYC/    │ │ Sanctions│        │   │
│  │  │  L1/L2   │ │  L1/L2   │ │ Custodian│ │  AML     │ │ Screen   │        │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘        │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Domain Definitions

| Domain | Responsibility | Key Invariants |
|--------|---------------|----------------|
| **A. Token Protocol** | ERC-20 + Permit + Access Control + Pausable + Blacklist + Upgradeable | Supply = Σ balances; Only minter mints; Paused blocks transfers |
| **B. Reserve Management** | Oracle attestations; Audit proofs; Collateralization checks; Reserve classification | Reserve ≥ Liability; Verified reserve tracked separately; Staleness detection |
| **C. Issuance Engine** | Deposit verification → Approval → Minting workflow | No mint without verified deposit + multisig approval |
| **D. Redemption Engine** | Burn → Payout → Reconciliation workflow | No complete without bank payout confirmation |
| **E. Financial Ledger** | Double-entry accounting; Journal entries; Reconciliation; Snapshots | Σ Debits = Σ Credits; Immutable posted entries; Daily reconciliation |
| **F. Blockchain Integration** | Contract interactions; Event indexing; Transaction management; Reorg handling | Finality waits; Nonce management; Gas bounds; Idempotency |
| **G. Oracle & Attestation** | Multi-source fiat data; Signed attestations; Verification; Conflict detection | Threshold signatures; Freshness SLA; Source authentication |
| **H. Governance & Admin** | Multisig operations; Role management; Upgrade coordination; Emergency procedures | Timelocked sensitive ops; Role separation; Audit trail |
| **I. Bridge Infrastructure** | Cross-chain messaging; Lock/mint or burn/release; Verification; Rate limits | Nonce deduplication; Finality verification; Circuit breakers |
| **J. Compliance** | KYC/AML; Sanctions screening; Transaction monitoring; SAR; Regulatory reporting | Tiered KYC; Real-time screening; Audit trail; Data protection |
| **K. Monitoring & Observability** | Metrics; Logs; Traces; Alerts; Dashboards; Synthetic monitoring | SLI/SLO defined; P1 alert < 5min; Trace coverage > 95% |
| **L. API Gateway** | AuthN/AuthZ; Rate limiting; Idempotency; Versioning; Request correlation | Zero trust; Per-endpoint limits; OpenAPI published |
| **M. User Dashboard** | Read-only views; Real-time data; Historical analysis; Export | Data source labeling; Stale indicators; Access control |
| **N. Reporting & Audit** | Financial statements; Regulatory reports; Auditor exports; Compliance proofs | BI/OJK/PPATK formats; Hash-chained audit trail; Point-in-time |

---

## 3. DOMAIN BOUNDARIES & INTERFACES

### 3.1 Explicit Boundaries

| Boundary | Enforcement Mechanism |
|----------|----------------------|
| **On-Chain State ↔ Off-Chain Financial State** | Ledger Service owns off-chain truth; Blockchain Adapter reads on-chain; Reconciliation Engine compares daily |
| **External Bank Data ↔ Reserve Management** | Oracle Adapter fetches; Verifier validates signatures; Reserve Service stores attested values only |
| **Oracle Attestations ↔ Issuance/Redemption** | Issuance/Redemption Engines query Reserve Service for collateralization status; circuit breaker on stale |
| **User Identity ↔ Internal Privileges** | Auth Service derives roles from JWT/API Key; API Gateway enforces; no caller in request body |
| **Internal Admin Privileges ↔ Financial Operations** | Multisig owns all sensitive roles; TimelockController enforces delays; Emergency council for pause |
| **Financial Accounting Records ↔ Blockchain Events** | Indexer writes events to ledger; Reconciliation matches; Discrepancy → Alert + Manual review |

### 3.2 Domain Communication Patterns

| Pattern | Use Case | Implementation |
|---------|----------|----------------|
| **Synchronous Query** | Dashboard data, balance checks | REST/gRPC with circuit breaker |
| **Async Command** | Mint, Burn, Bridge, Payout | Message queue (Redis Streams/Kafka) + idempotency |
| **Event Notification** | Blockchain events, Oracle updates | Webhook + WebSocket (authenticated) |
| **Batch Reconciliation** | Daily closing, Audit exports | Scheduled jobs with report output |

---

## 4. DATA MODEL (Core Entities)

### 4.1 On-Chain (Solidity)

```solidity
// Token Protocol
contract IDRCToken {
    // ERC-20 + Permit + Roles + Pause + Blacklist + Upgradeable
    // State: balances, allowances, nonces, roles, supplyCap, paused, blacklist
}

// Reserve Management
contract ProofOfReserve {
    // Oracle: fiatBalanceIdr, lastOracleUpdate, oracleAddress
    // Audits: AuditReport[] (seq, proofHash, reportedFiat, submittedBy, timestamp)
    // Verification: reserveRatio(), isFullyCollateralised()
}

// Bridge
contract BridgeVault {
    // Lock: burn on source, emit TokensLocked(nonce, sender, recipient, amount, dstChain)
    // Release: mint on source (reverse), emit TokensReleased
    // State: _nonce, _lockedAmounts, _processedNonces, _totalLocked
}

contract BridgeRelayer {
    // Relay: mint on destination, emit MessageRelayed
    // State: _processedMessages[srcChain][nonce]
}

// Governance
contract MultisigWallet {
    // M-of-N with timelock
    // State: _owners[], _threshold, _timelock, _transactions[], _confirmations
}

contract ProxyAdmin {
    // Owns UUPSProxy; managed by Multisig
}
```

### 4.2 Off-Chain (PostgreSQL)

```sql
-- Financial Ledger (Core)
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) UNIQUE NOT NULL,  -- '1010', '2010', '3010', '4010', '5010'
    name VARCHAR(100) NOT NULL,
    type account_type NOT NULL,  -- ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE
    currency CHAR(3) NOT NULL DEFAULT 'IDR',
    parent_id UUID REFERENCES accounts(id),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE journal_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_number BIGSERIAL UNIQUE NOT NULL,
    entry_date DATE NOT NULL,
    description TEXT NOT NULL,
    reference_type VARCHAR(50),  -- 'MINT', 'BURN', 'BRIDGE_LOCK', 'BRIDGE_RELEASE', 'FEE', 'PAYOUT', 'DEPOSIT'
    reference_id VARCHAR(100),   -- tx_hash, bridge_nonce, deposit_id, etc.
    status entry_status DEFAULT 'DRAFT',  -- DRAFT, POSTED, REVERSED
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    posted_at TIMESTAMPTZ,
    posted_by UUID REFERENCES users(id),
    reversed_at TIMESTAMPTZ,
    reversed_by UUID REFERENCES users(id),
    reversal_reason TEXT,
    prev_hash CHAR(64),  -- Hash of previous posted entry for chain integrity
    CONSTRAINT valid_status_transition CHECK (
        (status = 'DRAFT' AND posted_at IS NULL) OR
        (status = 'POSTED' AND posted_at IS NOT NULL) OR
        (status = 'REVERSED' AND reversed_at IS NOT NULL)
    )
);

CREATE TABLE journal_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_entry_id UUID NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES accounts(id),
    debit NUMERIC(78, 0) NOT NULL DEFAULT 0,  -- 18 decimals for IDR wei
    credit NUMERIC(78, 0) NOT NULL DEFAULT 0,
    description TEXT,
    CONSTRAINT one_sided CHECK (debit = 0 OR credit = 0),
    CONSTRAINT non_negative CHECK (debit >= 0 AND credit >= 0)
);

-- Trigger: Enforce balanced entries on POST
CREATE OR REPLACE FUNCTION enforce_balanced_entry()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'POSTED' THEN
        IF (SELECT SUM(debit) FROM journal_lines WHERE journal_entry_id = NEW.id) !=
           (SELECT SUM(credit) FROM journal_lines WHERE journal_entry_id = NEW.id) THEN
            RAISE EXCEPTION 'Unbalanced journal entry: debits != credits';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Indexer Events (Immutable Append-Only)
CREATE TABLE token_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    tx_hash CHAR(66) NOT NULL,
    block_number BIGINT NOT NULL,
    log_index INT NOT NULL,
    chain_id INT NOT NULL,
    from_address CHAR(42),
    to_address CHAR(42),
    amount NUMERIC(78, 0),
    caller CHAR(42),
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tx_hash, log_index, chain_id)
);

CREATE TABLE reserve_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    tx_hash CHAR(66) NOT NULL,
    block_number BIGINT NOT NULL,
    chain_id INT NOT NULL,
    fiat_balance NUMERIC(78, 0),
    proof_hash CHAR(66),
    submitted_by CHAR(42),
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE bridge_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,  -- TokensLocked, TokensReleased, MessageRelayed
    tx_hash CHAR(66) NOT NULL,
    block_number BIGINT NOT NULL,
    chain_id INT NOT NULL,
    bridge_nonce BIGINT NOT NULL,
    src_chain INT,
    dst_chain INT,
    sender CHAR(42),
    recipient CHAR(42),
    amount NUMERIC(78, 0) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit Log (Hash-Chained)
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(100),
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    prev_hash CHAR(64),  -- Hash of previous log entry
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Reconciliation
CREATE TABLE reconciliations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reconciliation_date DATE NOT NULL,
    type VARCHAR(50) NOT NULL,  -- 'DAILY_SUPPLY', 'DAILY_RESERVE', 'DEPOSIT_MINT', 'REDEMPTION_PAYOUT'
    expected_value NUMERIC(78, 0) NOT NULL,
    actual_value NUMERIC(78, 0) NOT NULL,
    difference NUMERIC(78, 0) GENERATED ALWAYS AS (actual_value - expected_value) STORED,
    status VARCHAR(20) DEFAULT 'OPEN',  -- OPEN, INVESTIGATING, RESOLVED, FALSE_POSITIVE
    resolved_at TIMESTAMPTZ,
    resolved_by UUID REFERENCES users(id),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (reconciliation_date, type)
);

-- Compliance
CREATE TABLE kyc_profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    tier kyc_tier NOT NULL DEFAULT 'TIER_0',
    status kyc_status NOT NULL DEFAULT 'PENDING',
    risk_level risk_level NOT NULL DEFAULT 'LOW',
    kyc_expiry TIMESTAMPTZ,
    verified_at TIMESTAMPTZ,
    verified_by UUID REFERENCES users(id),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE sanctions_screening (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    screening_type VARCHAR(50) NOT NULL,  -- 'ONBOARDING', 'TRANSACTION', 'PERIODIC'
    provider VARCHAR(50) NOT NULL,  -- 'CHAINALYSIS', 'TRM', 'COMPLYADVANTAGE'
    result VARCHAR(20) NOT NULL,  -- 'CLEAR', 'HIT', 'REVIEW'
    match_details JSONB,
    screened_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 5. STATE MACHINES

### 5.1 Issuance State Machine

```
ISSUANCE LIFECYCLE:

┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐     ┌──────────┐     ┌────────┐
│  REQUESTED  │────▶│  DEPOSIT_PENDING │────▶│  DEPOSIT_VERIFIED   │────▶│ APPROVED │────▶│ MINTED │
└─────────────┘     └──────────────────┘     └─────────────────────┘     └──────────┘     └────────┘
       │                    │                        │                    │              │
       ▼                    ▼                        ▼                    ▼              ▼
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐     ┌──────────┐
│   EXPIRED   │     │    REJECTED      │     │      REJECTED       │     │  FAILED  │
│  (timeout)  │     │ (compliance fail)│     │  (bank reject)      │     │ (mint err)│
└─────────────┘     └──────────────────┘     └─────────────────────┘     └──────────┘

TRANSITIONS:
1. REQUESTED → DEPOSIT_PENDING: User initiates deposit via API; deposit record created
2. DEPOSIT_PENDING → DEPOSIT_VERIFIED: Bank webhook confirms funds received
3. DEPOSIT_PENDING → REJECTED: Compliance screening fails (sanctions, KYC)
4. DEPOSIT_PENDING → EXPIRED: No bank confirmation within 24h
5. DEPOSIT_VERIFIED → APPROVED: Multisig approves issuance (threshold signatures)
6. DEPOSIT_VERIFIED → REJECTED: Bank later rejects/reverses deposit
7. APPROVED → MINTED: Blockchain mint transaction confirmed
8. APPROVED → FAILED: Mint transaction reverts (gas, supply cap, pause)
9. FAILED → APPROVED: Retry after error resolution (idempotent)
```

### 5.2 Redemption State Machine

```
REDEMPTION LIFECYCLE:

┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐     ┌─────────────┐
│  REQUESTED  │────▶│  VALIDATED   │────▶│  BURN_PENDING   │────▶│  BURN_CONFIRMED  │────▶│  FIAT_PAYOUT_PENDING │────▶│  COMPLETED  │
└─────────────┘     └──────────────┘     └─────────────────┘     └──────────────────┘     └─────────────────────┘     └─────────────┘
       │                │                   │                      │                        │                        │
       ▼                ▼                   ▼                      ▼                        ▼                        ▼
┌─────────────┐  ┌──────────────┐   ┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   EXPIRED   │  │   REJECTED   │   │     REJECTED    │    │      FAILED      │    │      REFUND/RECOVERY│
│  (timeout)  │  │ (limits/KYC) │   │  (burn revert)  │    │  (payout fail)   │    │   (reimburse tokens)│
└─────────────┘  └──────────────┘   └─────────────────┘    └──────────────────┘    └─────────────────────┘

TRANSITIONS:
1. REQUESTED → VALIDATED: KYC tier check, daily/monthly limits, sanctions screen
2. REQUESTED → REJECTED: KYC expired, limit exceeded, sanctions hit
3. REQUESTED → EXPIRED: No action within 1h
4. VALIDATED → BURN_PENDING: User signs burn tx OR multisig approves issuerBurn
5. BURN_PENDING → BURN_CONFIRMED: Burn transaction confirmed on-chain
6. BURN_PENDING → REJECTED: Burn reverts (pause, blacklist, balance)
7. BURN_CONFIRMED → FIAT_PAYOUT_PENDING: Bank payout initiated (BI-FAST)
8. FIAT_PAYOUT_PENDING → COMPLETED: Bank confirms credit to user account
9. FIAT_PAYOUT_PENDING → REFUND/RECOVERY: Payout fails (wrong account, bank reject) → Tokens re-minted to user
10. Any terminal state → Manual review for exception handling
```

### 5.3 Bridge State Machine

```
BRIDGE TRANSFER (Lock-Mint Model):

SOURCE CHAIN                    DESTINATION CHAIN
┌─────────────────┐             ┌─────────────────┐
│   USER LOCKS    │             │                 │
│   (burn tokens) │────Event──▶ │  RELAYER        │
│                 │             │  VERIFIES       │
│  TokensLocked   │             │  (finality,     │
│  (nonce, amt)   │             │   proof)        │
└─────────────────┘             │                 │
                                │  RELAY          │
                                │  (mint tokens)  │
                                │                 │
                                │  MessageRelayed │
                                │  (nonce, amt)   │
                                └─────────────────┘

NONCE LIFECYCLE:
PENDING → PROCESSING → CONFIRMED/FAILED
- PENDING: Event detected, waiting for finality
- PROCESSING: Finality reached, relay tx submitted
- CONFIRMED: Relay tx confirmed, nonce marked processed
- FAILED: Relay reverted, retry with backoff (max 3), then alert
```

---

## 6. TRUST ASSUMPTIONS

| Component | Trust Assumption | Mitigation |
|-----------|-----------------|------------|
| **Multisig Signers** | Honest majority (threshold) | 2-of-3 or 3-of-5; known entities; legal agreements |
| **Oracle Network** | Threshold of oracles honest | 3-of-5 threshold; signed attestations; staking/slashing |
| **Bank Custodian** | Regulated entity; BI-supervised | Legal contract; audit rights; segregation |
| **Bridge Relayers** | Decentralized network honest | LayerZero/Axelar security model; light client verification |
| **Smart Contracts** | Code = deployed bytecode | Formal verification; audits; upgrade timelock |
| **Indexer** | RPC provider honest | Multiple RPCs; consensus on events |
| **KYC/AML Providers** | Accurate screening | Multiple providers; fallback; manual review |

---

## 7. FAILURE DEPENDENCIES

```
FAILURE CASCADING:

Oracle Failure (stale > 1h)
    │
    ├─▶ Circuit Breaker: Auto-pause minting (Issuance Engine)
    ├─▶ Alert: P1 to security + ops
    └─▶ Manual: Multisig can override with timelock

Bridge Relayer Compromise
    │
    ├─▶ Circuit Breaker: Auto-pause bridge (Bridge Engine)
    ├─▶ Rate Limit: Max mint rate per chain
    └─▶ Recovery: Multisig rotates relayer; investigates unauthorized mints

Multisig Key Compromise (1 of N)
    │
    ├─▶ No immediate impact (threshold not reached)
    ├─▶ Alert: P1 to security
    └─▶ Recovery: Multisig replaces compromised owner

Database Corruption
    │
    ├─▶ Read Replica: Promote for reads
    ├─▶ PITR: Point-in-time recovery
    └─▶ Reconciliation: Rebuild ledger from blockchain events

Smart Contract Bug (Critical)
    │
    ├─▶ Emergency Pause: Multisig pauses token + bridge
    ├─▶ Upgrade: Timelocked fix deployment (48h)
    └─▶ Post-Mortem: State reconstruction from events
```

---

## 8. DEPLOYMENT ARCHITECTURE

### 8.1 Environments

| Environment | Purpose | Chain | Data | Access |
|-------------|---------|-------|------|--------|
| **Local** | Development | Anvil | SQLite/PostgreSQL | Team |
| **Staging** | Integration Test | Sepolia/Amoy | PostgreSQL (shared) | Team + QA |
| **Production** | Mainnet | Ethereum/Polygon/etc. | PostgreSQL (HA) | Restricted |

### 8.2 Infrastructure Components

```
PRODUCTION INFRASTRUCTURE:

┌─────────────────────────────────────────────────────────────────┐
│                      AWS / GCP / ON-PREM                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  API (x3+)   │  │  Indexer     │  │  Oracle      │          │
│  │  (K8s Deploy)│  │  (K8s Deploy)│  │  Relayer     │          │
│  │  Gunicorn    │  │  + Workers   │  │  (K8s Deploy)│          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│  ┌──────┴─────────────────┴─────────────────┴───────┐          │
│  │              PostgreSQL Primary (HA)              │          │
│  │         ┌─────────┐  ┌─────────┐  ┌─────────┐     │          │
│  │         │ Primary │  │ Replica │  │ Replica │     │          │
│  │         └─────────┘  └─────────┘  └─────────┘     │          │
│  │         (PITR)   (Read)      (Read/Analytics)     │          │
│  └────────────────────────────────────────────────────┘          │
│         │                 │                 │                   │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐          │
│  │   Redis      │  │  Prometheus  │  │   Loki       │          │
│  │  (Cluster)   │  │  + Alertmgr  │  │  + Promtail  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         │                 │                 │                   │
│  ┌──────┴─────────────────┴─────────────────┴───────┐          │
│  │              Grafana Dashboards                   │          │
│  └────────────────────────────────────────────────────┘          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 9. SECURITY ARCHITECTURE

### 9.1 Defense in Depth

| Layer | Controls |
|-------|----------|
| **Network** | VPC; Security Groups; WAF; DDoS protection; Private subnets |
| **Application** | JWT + API Key auth; RBAC; Rate limiting; Idempotency; Input validation; CSP |
| **Data** | Encryption at rest (AES-256); Encryption in transit (TLS 1.3); PII encryption; Key rotation |
| **Blockchain** | Multisig governance; Timelocked upgrades; Pausable; Blacklist; Circuit breakers |
| **Operations** | Audit logging (hash-chained); SIEM; Incident response; DR testing; Secrets management |

### 9.2 Key Management

| Key Type | Storage | Rotation | Access |
|----------|---------|----------|--------|
| **Multisig Owners** | Hardware wallets (Ledger/Trezor) | Annual | Signers only |
| **Oracle Keys** | HSM (AWS KMS / HashiCorp Vault) | 90 days | Oracle service (automated) |
| **Bridge Relayer** | MPC / Threshold sigs | Per network policy | Relayer network |
| **API JWT Secret** | Vault | 30 days | API service (automated) |
| **Database** | Vault / Cloud KMS | 90 days | Infra team |
| **TLS Certs** | ACME (Let's Encrypt) | 90 days | Automated |

---

## 10. ADR INDEX

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| ADR-001 | Use OpenZeppelin AccessControl vs Custom | **Accepted** | 2026-11-18 |
| ADR-002 | Double-Entry Ledger Implementation | **Accepted** | 2026-11-18 |
| ADR-003 | Bridge Architecture: Lock-Mint via LayerZero | **Proposed** | 2026-11-18 |
| ADR-004 | Oracle: Multi-Source Threshold Signatures | **Proposed** | 2026-11-18 |
| ADR-005 | Upgrade Governance: TimelockController + Role Separation | **Accepted** | 2026-11-18 |
| ADR-006 | Financial Precision: Integer (Wei) Internal, Decimal Display | **Accepted** | 2026-11-18 |
| ADR-007 | Compliance: Build vs Buy KYC/AML | **Proposed** | 2026-11-18 |
| ADR-008 | Database: Migrations, Partitioning, Read Replicas | **Accepted** | 2026-11-18 |

---

**END OF SYSTEM_ARCHITECTURE.md**