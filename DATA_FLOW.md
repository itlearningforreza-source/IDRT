# DATA_FLOW.md
# IDRC Data Flow Architecture
**Version:** 2.0
**Date:** 2026-11-18
**Phase:** 1 - System Architecture Reconstruction
**Status:** DRAFT

---

## 1. DATA FLOW PRINCIPLES

| Principle | Implementation |
|-----------|----------------|
| **Explicit Sources** | Every data element tagged with origin (on-chain, oracle, bank, user, computed) |
| **Immutable Events** | Financial events never modified; corrections via reversing entries |
| **Traceability** | Correlation IDs propagate across all services |
| **Consistency** | Single writer per aggregate; event sourcing for critical state |
| **Freshness Labels** | All dashboard/API responses include data age and source |

---

## 2. CORE DATA FLOWS

### 2.1 Deposit → Issuance Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   USER      │     │   BANK      │     │   API       │     │  COMPLIANCE │     │  LEDGER     │     │  BLOCKCHAIN │
│  (Depositor)│     │  (Custodian)│     │  (Gateway)  │     │  (KYC/AML)  │     │  (Service)  │     │  (EVM)      │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │                   │                   │                   │
       │  1. BI-FAST       │                   │                   │                   │                   │
       │  Transfer ───────▶│                   │                   │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │  2. Webhook       │                   │                   │                   │
       │                   │  (ISO 20022) ────▶│                   │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │                   │  3. Create        │                   │                   │
       │                   │                   │  DepositRecord    │                   │                   │
       │                   │                   │  (PENDING)        │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │                   │  4. Screen ───────▶│                   │                   │
       │                   │                   │                   │  5. Result        │                   │
       │                   │                   │                   │  (CLEAR/REVIEW)   │                   │
       │                   │                   │                   │                   │                   │
       │                   │                   │  6. Verify ─────────────────────────▶│                   │
       │                   │                   │  Bank Signature   │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │                   │  7. Update        │                   │                   │
       │                   │                   │  DepositRecord    │                   │                   │
       │                   │                   │  (VERIFIED)       │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │                   │  8. Create ───────────────────────────────────────────▶│
       │                   │                   │  IssuanceRequest  │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │                   │  9. Multisig ─────────────────────────────────────────▶│
       │                   │                   │  Approve          │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │                   │  10. Mint ────────────────────────────────────────────▶│
       │                   │                   │  (tx_hash)        │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │                   │  11. Journal Entry                                                    │
       │                   │                   │  Dr Bank Reserve  │                   │                   │
       │                   │                   │  Cr Customer Liab │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │                   │  12. Event ◀────────────────────────────────────────────│
       │                   │                   │  (Minted)         │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │                   │  13. Reconcile ───┤                   │                   │
       │                   │                   │  Supply=Liability │                   │                   │
       │                   │                   │                   │                   │                   │
       │  14. Notify ◀─────┤                   │                   │                   │                   │
       │  (Success)        │                   │                   │                   │                   │
```

**Data Elements:**
| Step | Data | Source | Destination | Freshness |
|------|------|--------|-------------|-----------|
| 1 | Amount, User ID, Reference | User | Bank | Real-time |
| 2 | Transaction ID, Amount, Timestamp | Bank | API | < 30 sec |
| 3 | DepositRecord (id, user, amount, status, ref) | API | Database | Immediate |
| 4/5 | Screening result, Risk score | Compliance | API | < 5 sec |
| 6 | Bank signed attestation | Bank | API | Real-time |
| 7 | DepositRecord (status=VERIFIED) | API | Database | Immediate |
| 8 | IssuanceRequest (deposit_ref, recipient, amount) | API | Database | Immediate |
| 9 | Multisig tx (threshold sigs) | Multisig | Blockchain | < 5 min |
| 10 | Mint tx_hash, block, gas | Blockchain | API | < 3 min |
| 11 | JournalEntry (balanced, hash_chained) | Ledger | Database | Immediate |
| 12 | Minted event (to, amount, tx_hash) | Blockchain | Indexer → Database | < 10 sec |
| 13 | Reconciliation result | Reconciliation | Database | Daily batch |
| 14 | Notification (email, push, webhook) | API | User | Immediate |

### 2.2 Redemption → Payout Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   USER      │     │   API       │     │  COMPLIANCE │     │  BLOCKCHAIN │     │  LEDGER     │     │   BANK      │
│  (Redeemer) │     │  (Gateway)  │     │  (KYC/AML)  │     │  (EVM)      │     │  (Service)  │     │ (Custodian) │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │                   │                   │                   │
       │  1. Burn Request  │                   │                   │                   │                   │
       │  (amount, addr) ──▶│                   │                   │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │  2. Validate      │                   │                   │                   │
       │                   │  (KYC, limits,    │                   │                   │                   │
       │                   │   sanctions) ────▶│                   │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │  3. Result ◀──────┤                   │                   │                   │
       │                   │  (CLEAR/REVIEW)   │                   │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │  4. User Signs    │                   │                   │                   │
       │                   │  Burn Tx ─────────────────────────────▶│                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │  5. Burn Confirmed◀───────────────────┤                   │                   │
       │                   │  (tx_hash)        │                   │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │  6. Journal Entry                                         │
       │                   │  Dr Customer Liab │                   │                   │                   │
       │                   │  Cr Pending Payout│                   │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │  7. Payout Init ◀─────────────────────────────────────────┤
       │                   │  (BI-FAST, ref)   │                   │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │  8. Bank Confirms │                   │                   │                   │
       │                   │  (webhook) ◀──────┤                   │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │  9. Journal Entry                                         │
       │                   │  Dr Pending Payout│                   │                   │                   │
       │                   │  Cr Bank Reserve  │                   │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │  10. Reconcile ───┤                   │                   │                   │
       │                   │  Burn=Payout      │                   │                   │                   │
       │                   │                   │                   │                   │                   │
       │  11. Notify ◀─────┤                   │                   │                   │                   │
       │  (Complete)       │                   │                   │                   │                   │
```

**Failure Recovery (Step 8 fails):**
```
       │                   │  8a. Payout Fails                   │                   │
       │                   │  (reject, timeout) ─────────────────┤                   │
       │                   │                   │                   │                   │
       │                   │  8b. Refund/Recovery                                         │
       │                   │  Remint tokens to user ───────────▶│                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │  8c. Journal Entry                                         │
       │                   │  Dr Pending Payout│                   │                   │                   │
       │                   │  Cr Customer Liab │                   │                   │                   │
       │                   │                   │                   │                   │                   │
       │                   │  8d. SAR if > threshold │                   │                   │                   │
```

### 2.3 Bridge Transfer Flow (Lock-Mint)

```
SOURCE CHAIN (e.g., Ethereum)          DESTINATION CHAIN (e.g., Polygon)
┌─────────────────────────────┐        ┌─────────────────────────────┐
│                             │        │                             │
│  ┌─────────┐                │        │  ┌─────────┐               │
│  │  USER   │                │        │  │ RELAYER │               │
│  └────┬────┘                │        │  └────┬────┘               │
│       │                     │        │       │                    │
│  1. Lock (burn)            │        │       │                    │
│     └──────────────────────┼───────▶│       │                    │
│       │                    │        │       │                    │
│  2. TokensLocked Event     │        │       │                    │
│     (nonce, sender,        │        │       │                    │
│      recipient, amount,    │        │       │                    │
│      dstChain)             │        │       │                    │
│       │                    │        │       │                    │
│       │         3. Indexer detects event, stores in bridge_events    │
│       │                    │        │       │                    │
│       │                    │        │  4. Wait Finality           │
│       │                    │        │     (Ethereum: 2 epochs)    │
│       │                    │        │       │                    │
│       │                    │        │  5. Verify:                 │
│       │                    │        │     - Merkle proof          │
│       │                    │        │     - Block header          │
│       │                    │        │     - Nonce not used        │
│       │                    │        │       │                    │
│       │                    │        │  6. Relay (mint)            │
│       │                    │        │     └─────────────────────▶│
│       │                    │        │       │                    │
│       │                    │        │  7. MessageRelayed Event    │
│       │                    │        │       │                    │
│       │                    │        │  8. Indexer detects, stores                          │
│       │                    │        │       │                    │
│       │                    │        │  9. Journal Entry (both chains)                      │
│       │                    │        │       │                    │
│       │                    │        │  10. Reconcile: Locked=Minted                      │
│       │                    │        │       │                    │
│       │                    │        │  11. Notify User ◀────────│                    │
│       │                    │        │       │                    │
└─────────────────────────────┘        └─────────────────────────────┘
```

**Cross-Chain Data Consistency:**
| Check | Source | Destination | Frequency |
|-------|--------|-------------|-----------|
| Nonce uniqueness | BridgeEvents (src) | BridgeEvents (dst) | Per transfer |
| Amount match | TokensLocked.amount | MessageRelayed.amount | Per transfer |
| Recipient match | TokensLocked.recipient | MessageRelayed.recipient | Per transfer |
| Total locked | Σ BridgeEvents.locked | Vault.totalLocked() | Daily reconciliation |
| Supply consistency | Σ All chains supply | Expected (issuance - redemption + bridge net) | Daily |

### 2.4 Oracle Update Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  BANK       │     │  ORACLE     │     │  BLOCKCHAIN │     │  INDEXER    │     │  MONITOR    │
│  CUSTODIAN  │     │  RELAYER    │     │  (Reserve)  │     │  (Service)  │     │  (Service)  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │                   │                   │
       │  1. Signed        │                   │                   │                   │
       │  Attestation ────▶│                   │                   │                   │
       │  (balance, ts,    │                   │                   │                   │
       │   cert, sig)      │                   │                   │                   │
       │                   │                   │                   │                   │
       │                   │  2. Verify sig,   │                   │                   │
       │                   │  cert, freshness  │                   │                   │
       │                   │                   │                   │                   │
       │                   │  3. Submit ──────────────────────────▶│                   │
       │                   │  updateFiatBalance│                   │                   │
       │                   │                   │                   │                   │
       │                   │  4. Event ◀───────────────────────────┤                   │
       │                   │  (FiatBalanceUpdated)                │                   │                   │
       │                   │                   │                   │                   │
       │                   │                   │  5. Store Event ─────────────────────────────────────▶│
       │                   │                   │                   │                   │                   │
       │                   │                   │                   │  6. Update Cache│                   │
       │                   │                   │                   │  (latest balance)                   │
       │                   │                   │                   │                   │                   │
       │                   │                   │                   │                   │  7. Check Ratio │
       │                   │                   │                   │                   │  (alert if <1)  │
       │                   │                   │                   │                   │                   │
```

**Oracle Attestation Format:**
```json
{
  "version": "1.0",
  "timestamp": "2026-11-18T10:30:00Z",
  "bank": {
    "id": "BI-FAST-001",
    "name": "Bank Indonesia Custodian",
    "cert_fingerprint": "sha256:..."
  },
  "reserve": {
    "total_idr": "10000000000000000000000000",
    "classification": {
      "customer_liability": "9500000000000000000000000",
      "operational_cash": "300000000000000000000000",
      "fee_revenue": "100000000000000000000000",
      "pending_deposits": "50000000000000000000000",
      "pending_withdrawals": "20000000000000000000000",
      "encumbered": "0"
    }
  },
  "auditor": {
    "id": "KPMG-ID",
    "report_hash": "0x...",
    "report_date": "2026-11-01"
  },
  "signatures": [
    {"oracle": "oracle-1", "sig": "0x..."},
    {"oracle": "oracle-2", "sig": "0x..."},
    {"oracle": "oracle-3", "sig": "0x..."}
  ],
  "threshold": 3,
  "total_oracles": 5
}
```

---

## 3. DATA FRESHNESS & SOURCE LABELING

### 3.1 Freshness Tiers

| Tier | Max Age | Sources | Use Case |
|------|---------|---------|----------|
| **REAL_TIME** | < 15 sec | Blockchain events, API calls | Trading, user actions |
| **NEAR_REAL_TIME** | < 5 min | Indexer, Oracle cache | Dashboard, monitoring |
| **BATCH_DAILY** | 24 hours | Reconciliation, Bank statements | Financial reports, audit |
| **BATCH_MONTHLY** | 30 days | Regulatory reports, Snapshots | Compliance, tax |

### 3.2 API Response Data Labels

Every API response including financial data MUST include:
```json
{
  "data": { ... },
  "meta": {
    "source": "BLOCKCHAIN|ORACLE|BANK|LEDGER|COMPUTED",
    "freshness_tier": "REAL_TIME|NEAR_REAL_TIME|BATCH_DAILY|BATCH_MONTHLY",
    "timestamp": "2026-11-18T10:30:00Z",
    "block_number": 12345678,
    "chain_id": 1,
    "correlation_id": "req-abc123"
  }
}
```

---

## 4. RECONCILIATION DATA FLOWS

### 4.1 Daily Reconciliation (Automated)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DAILY RECONCILIATION JOB (02:00 UTC)                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. FETCH SOURCES                                                           │
│     ├─▶ On-chain: totalSupply() per chain                                   │
│     ├─▶ Ledger: Σ Customer Liability accounts                               │
│     ├─▶ Reserve: ProofOfReserve.fiatBalanceIdr()                            │
│     ├─▶ Bank: Custodian statement (BI-FAST)                                 │
│     ├─▶ Deposits: Σ Verified deposits (24h)                                 │
│     ├─▶ Mints: Σ Minted events (24h)                                        │
│     ├─▶ Redemptions: Σ Burned events (24h)                                  │
│     ├─▶ Payouts: Σ Confirmed payouts (24h)                                  │
│     └─▶ Bridge: Σ Locked vs Σ Minted per chain                              │
│                                                                             │
│  2. COMPARE (with thresholds)                                               │
│     ├─▶ Supply vs Liability: MUST equal (0 tolerance)                       │
│     ├─▶ Reserve vs Bank: ≤ 0.01% tolerance (timing)                         │
│     ├─▶ Deposits vs Mints: 1:1 mapping                                      │
│     ├─▶ Redemptions vs Burns+Payouts: 1:1 mapping                           │
│     ├─▶ Bridge Locked vs Minted: Equal per chain                            │
│     └─▶ Fee Revenue: Calculated vs Ledger                                   │
│                                                                             │
│  3. RECORD                                                                  │
│     ├─▶ Store Reconciliation record per check                               │
│     ├─▶ If OPEN: Alert P2; assign investigator                              │
│     ├─▶ If RESOLVED: Close with notes                                       │
│     └─▶ Hash-chain audit log entry                                          │
│                                                                             │
│  4. EXPORT                                                                  │
│     ├─▶ Daily Balance Sheet (PDF + JSON)                                    │
│     ├─▶ Discrepancy Report (if any)                                         │
│     └─▶ Auditor Package (encrypted)                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Real-Time Discrepancy Detection

| Monitor | Check | Threshold | Action |
|---------|-------|-----------|--------|
| **Supply Monitor** | totalSupply() vs Ledger Liability | ≠ 0 | P1 Alert; Pause minting |
| **Reserve Monitor** | Oracle balance vs Contract balance | > 1% | P1 Alert; Circuit breaker |
| **Bridge Monitor** | Locked events vs Processed nonces | > 100 pending | P2 Alert; Rate limit |
| **Oracle Monitor** | lastOracleUpdate age | > 1 hour | P1 Alert; Pause minting |
| **Payout Monitor** | Pending payouts > 24h | Any | P2 Alert; Escalate |

---

## 5. AUDIT TRAIL DATA FLOW

```
EVENT → AUDIT LOG → HASH CHAIN → BLOCKCHAIN ANCHOR

┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  ACTION     │     │  AUDIT      │     │  HASH       │     │  ANCHOR     │
│  (API/BC)   │────▶│  SERVICE    │────▶│  CHAIN      │────▶│  (Periodic) │
└─────────────┘     └──────┬──────┘     └──────┬──────┘     └─────────────┘
                           │                   │
                           ▼                   ▼
                    ┌─────────────┐     ┌─────────────┐
                    │  DATABASE   │     │  MERKLE     │
                    │  (Immutable)│     │  ROOT       │
                    └─────────────┘     └──────┬──────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │  SMART      │
                                        │  CONTRACT   │
                                        │  (Anchor)   │
                                        └─────────────┘

HASH CHAIN:
log_n.hash = SHA256(log_{n-1}.hash || log_n.payload || log_n.timestamp)

ANCHOR (every 1000 logs or 1 hour):
AnchorContract.storeRoot(merkleRoot, blockNumber)
```

---

## 6. DATA RETENTION & ARCHIVAL

| Data Type | Hot Storage | Warm Storage | Cold Storage | Deletion |
|-----------|-------------|--------------|--------------|----------|
| **Journal Entries** | 2 years | 7 years | 20 years | Never (legal) |
| **Audit Logs** | 1 year | 7 years | 20 years | Never (legal) |
| **Blockchain Events** | 2 years | 7 years | Permanent | Never |
| **Reconciliations** | 2 years | 7 years | 20 years | Never |
| **KYC Profiles** | Active + 2y | 7 years | 20 years | Per PDP UU |
| **Sanctions Screenings** | 2 years | 7 years | 20 years | Never |
| **API Access Logs** | 90 days | 1 year | 3 years | Auto |
| **Metrics/Traces** | 30 days | 1 year | 3 years | Auto |

---

## 7. DATA FLOW VALIDATION RULES

### 7.1 Invariants (Always True)

1. **Conservation of Tokens:** Σ Minted = Σ Burned + Total Supply
2. **Reserve Adequacy:** Fiat Reserve ≥ Token Liability (100%+)
3. **Deposit-Mint Parity:** Verified Deposits = Issued Mints (1:1)
4. **Redemption Parity:** Completed Redemptions = Burns + Payouts (1:1)
5. **Bridge Balance:** Σ Source Locked = Σ Destination Minted (per chain pair)
6. **Ledger Balance:** Σ Debits = Σ Credits (per journal entry)
7. **Audit Chain Integrity:** Hash chain unbroken from genesis

### 7.2 Validation Points

| Point | Validation | On Failure |
|-------|------------|------------|
| **API Input** | Schema + Business rules | 400 + Audit log |
| **Blockchain Write** | Simulation + Gas estimate | Reject + Alert |
| **Oracle Attestation** | Sig + Cert + Freshness | Reject + Alert |
| **Journal Post** | Debits = Credits | Reject + Alert |
| **Reconciliation** | All checks pass | Alert + Investigate |
| **Anchor Write** | Merkle root stored | Retry + Alert |

---

**END OF DATA_FLOW.md**