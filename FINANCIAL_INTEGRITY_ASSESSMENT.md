# FINANCIAL_INTEGRITY_ASSESSMENT.md
# IDRT Financial Integrity Assessment
**Date:** 2026-11-18
**Phase:** 0 - Repository Forensics
**Classification:** CONFIDENTIAL - Financial Engineering Review
**Status:** CRITICAL GAPS IDENTIFIED - NOT FINANCIALLY SOUND

---

## 1. EXECUTIVE SUMMARY

The IDRT system **lacks a proper financial ledger**, **uses floating-point arithmetic in critical paths**, **has no reconciliation mechanisms**, and **cannot demonstrate financial integrity** required for a fiat-collateralized stablecoin. The current implementation tracks token supply on-chain and a single fiat balance off-chain, but has no double-entry accounting, no audit trail of financial events, and no way to prove solvency to regulators or auditors.

**Verdict:** **FAILS** institutional financial integrity requirements. Cannot support billions of IDR in obligations.

---

## 2. CORE FINANCIAL PRINCIPLES VIOLATED

| Principle | Required | Current State | Gap |
|-----------|----------|---------------|-----|
| **Double-Entry Bookkeeping** | Every event → balanced debit/credit | ❌ None | **CRITICAL** |
| **Fixed-Precision Arithmetic** | Integer (wei) or decimal | ⚠️ Mixed (Python float) | **CRITICAL** |
| **Immutable Audit Trail** | Append-only, hash-chained | ❌ Mutable DB rows | **CRITICAL** |
| **Reconciliation** | Daily on-chain vs off-chain vs bank | ❌ None | **CRITICAL** |
| **Chart of Accounts** | Liabilities, Assets, Equity, Revenue | ❌ None | **CRITICAL** |
| **Idempotency** | Duplicate-safe financial ops | ❌ None | **CRITICAL** |
| **Segregation of Funds** | Customer vs Operational vs Encumbered | ❌ Single balance | **CRITICAL** |

---

## 3. DETAILED FINDINGS

### 3.1 Missing Double-Entry Ledger (CRITICAL)

**Finding:** No financial ledger exists in the codebase.

**Evidence:**
- `services/api/database.py` defines: User, APIKey, AuditLog, TokenEvent
- No Account, JournalEntry, JournalLine, Reconciliation tables
- `kyc_aml_service.py` DATABASE_SCHEMA has transactions table but no double-entry structure

**Required Structure:**
```sql
-- Chart of Accounts
CREATE TABLE accounts (
    id UUID PRIMARY KEY,
    code VARCHAR(20) UNIQUE NOT NULL,  -- e.g., '1010', '2010', '3010'
    name VARCHAR(100) NOT NULL,
    type VARCHAR(20) NOT NULL,  -- ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE
    currency VARCHAR(3) NOT NULL DEFAULT 'IDR',
    parent_id UUID REFERENCES accounts(id),
    is_active BOOLEAN DEFAULT true
);

-- Journal Entries (immutable once posted)
CREATE TABLE journal_entries (
    id UUID PRIMARY KEY,
    entry_number BIGSERIAL UNIQUE NOT NULL,
    date DATE NOT NULL,
    description TEXT NOT NULL,
    reference_type VARCHAR(50),  -- 'MINT', 'BURN', 'BRIDGE', 'FEE', 'PAYOUT'
    reference_id VARCHAR(100),   -- tx_hash, bridge_nonce, etc.
    status VARCHAR(20) DEFAULT 'POSTED',  -- DRAFT, POSTED, REVERSED
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    posted_at TIMESTAMP WITH TIME ZONE,
    reversed_by UUID REFERENCES users(id),
    reversed_at TIMESTAMP WITH TIME ZONE,
    reversal_reason TEXT,
    hash_chain VARCHAR(64)  -- hash of previous entry for integrity
);

-- Journal Lines (must balance: SUM(debit) = SUM(credit))
CREATE TABLE journal_lines (
    id UUID PRIMARY KEY,
    journal_entry_id UUID REFERENCES journal_entries(id),
    account_id UUID REFERENCES accounts(id),
    debit NUMERIC(78, 0) DEFAULT 0,  -- 18 decimals for IDR
    credit NUMERIC(78, 0) DEFAULT 0,
    description TEXT,
    CHECK (debit = 0 OR credit = 0),  -- never both
    CHECK (debit >= 0 AND credit >= 0)
);

-- Constraint: Every posted entry must balance
CREATE RULE journal_balance_check AS ON INSERT TO journal_entries
WHERE status = 'POSTED' DO
    SELECT raise_exception('Unbalanced entry')
    FROM journal_lines
    WHERE journal_entry_id = NEW.id
    HAVING SUM(debit) != SUM(credit);
```

**Impact:** Cannot produce financial statements. Cannot prove assets = liabilities. Regulatory non-compliance.

### 3.2 Floating-Point Arithmetic in Financial Calculations (CRITICAL)

**Finding:** Python services use `float` for monetary values.

**Evidence:**
- `monitor_service.py` line 131: `IDRCAmount(fiat_balance / 10**18)` - float division
- `monitor_service.py` line 103: `ratio = (fiat * 10**18) / supply` - float
- `reserve_service.py` line 31: `Decimal(ratio) / 10**18` - converts from float
- `token_service.py` line 24: `IDRCAmount(totalSupply / 10**18)` - float

**Correct Approach:**
```python
# Use integer (wei) for all internal calculations
# Use Decimal for display only
from decimal import Decimal, ROUND_DOWN

def wei_to_idr(wei: int) -> Decimal:
    return Decimal(wei) / Decimal(10**18)

def idr_to_wei(idr: Decimal) -> int:
    return int((idr * Decimal(10**18)).quantize(Decimal('1'), rounding=ROUND_DOWN))

# Reserve ratio as integer basis points (10000 = 100%)
def reserve_ratio_bps(fiat_wei: int, supply_wei: int) -> int:
    if supply_wei == 0:
        return 2**31 - 1  # Max int
    return (fiat_wei * 10000) // supply_wei
```

**Impact:** Rounding errors accumulate. Financial discrepancies. Audit failures.

### 3.3 No Reconciliation Between On-Chain and Off-Chain State (CRITICAL)

**Finding:** No automated reconciliation between:
1. Blockchain `totalSupply()` vs Internal token liability ledger
2. ProofOfReserve `fiatBalanceIdr()` vs Bank statements
3. Deposit records vs Mint events
4. Redemption records vs Burn events + Bank payouts

**Current Monitoring (Insufficient):**
- `monitor_service.py` checks `reserveRatio` and `supplyCap` only
- No daily closing process
- No discrepancy alerts with thresholds
- No historical snapshots for audit

**Required Reconciliation Engine:**
```python
class ReconciliationEngine:
    async def daily_reconciliation(self, date: date) -> ReconciliationReport:
        # 1. On-chain supply
        onchain_supply = await self.blockchain.get_total_supply()
        
        # 2. Internal liability ledger
        ledger_liability = await self.ledger.get_token_liability()
        
        # 3. Bank reserve (from custodian)
        bank_reserve = await self.bank.get_balance(date)
        
        # 4. ProofOfReserve contract
        contract_reserve = await self.reserve_contract.fiat_balance()
        
        # 5. Compare with thresholds
        discrepancies = []
        if onchain_supply != ledger_liability:
            discrepancies.append(Discrepancy(
                type="SUPPLY_MISMATCH",
                severity="CRITICAL",
                expected=ledger_liability,
                actual=onchain_supply,
                diff=abs(onchain_supply - ledger_liability)
            ))
        
        if bank_reserve != contract_reserve:
            discrepancies.append(Discrepancy(
                type="RESERVE_MISMATCH",
                severity="CRITICAL",
                expected=bank_reserve,
                actual=contract_reserve
            ))
        
        return ReconciliationReport(date, discrepancies)
```

### 3.4 No Segregation of Reserve Funds (CRITICAL)

**Finding:** Single `fiatBalanceIdr` in ProofOfReserve mixes all reserve categories.

**Required Classification:**
| Reserve Category | Description | Redeemable |
|------------------|-------------|------------|
| **Customer Liability Reserve** | Backs circulating IDRC 1:1 | Yes |
| **Operational Cash** | Company operating funds | No |
| **Fee Revenue Reserve** | Accumulated fees | No (distributable) |
| **Pending Deposits** | Deposits received, not yet minted | Yes (once minted) |
| **Pending Withdrawals** | Burned, not yet paid out | No (encumbered) |
| **Encumbered Reserve** | Legal holds, sanctions | No |
| **Excess Reserve** | Above 100% collateralization | No (governance) |

**Current:** `fiatBalanceIdr` = single number. Cannot distinguish.

### 3.5 Issuance/Redemption Lack Financial Workflow (CRITICAL)

**Current Flow (Inadequate):**
```
MINT: MINTER_ROLE calls mint() → tokens created → Minted event
BURN: BURNER_ROLE calls issuerBurn() → tokens destroyed → Burned event
```

**Required Financial Workflow:**

**ISSUANCE (Deposit → Mint):**
```
1. DEPOSIT_RECEIVED: Bank webhook → Create DepositRecord (pending)
2. COMPLIANCE_CHECK: KYC/AML screening → Approve/Reject
3. DEPOSIT_VERIFIED: Bank confirmation → Update DepositRecord (verified)
4. ISSUANCE_REQUEST: Create IssuanceRequest (amount, recipient, deposit_ref)
5. MULTISIG_APPROVAL: Threshold signatures → Approve
6. MINT_EXECUTION: Call token.mint() → Get tx_hash
7. LEDGER_ENTRY: Dr Bank Reserve / Cr Customer Liability
8. RECONCILIATION: Verify mint tx on-chain matches request
9. NOTIFICATION: Confirm to user
```

**REDEMPTION (Burn → Payout):**
```
1. REDEMPTION_REQUEST: User calls burn() or API → Create RedemptionRequest
2. COMPLIANCE_CHECK: KYC/AML, sanctions → Approve/Reject
3. VALIDATION: Verify token balance, check limits
4. BURN_EXECUTION: Call token.burn() or issuerBurn() → Get tx_hash
5. LEDGER_ENTRY: Dr Customer Liability / Cr Pending Payout
6. PAYOUT_INITIATION: Bank transfer (BI-FAST) → Get bank_ref
7. PAYOUT_CONFIRMATION: Bank webhook → Confirm received
8. LEDGER_ENTRY: Dr Pending Payout / Cr Bank Reserve
9. RECONCILIATION: Verify burn + payout match
10. COMPLETION: Mark RedemptionRequest complete
```

### 3.6 No Fee Accounting (HIGH)

**Finding:** No fee structure implemented or accounted for.

**Required Fee Types:**
| Fee | Rate | Accounting |
|-----|------|------------|
| Mint Fee | 0.1% (configurable) | Dr Customer / Cr Fee Revenue |
| Burn Fee | 0.1% (configurable) | Dr Customer / Cr Fee Revenue |
| Bridge Fee | 0.2% (configurable) | Dr Customer / Cr Fee Revenue |
| Monthly Maintenance | 0.01% on balance | Dr Customer / Cr Fee Revenue |

**Current:** No fee parameters in contracts. No fee collection in API.

### 3.7 Supply Cap Management Incomplete (HIGH)

**Finding:** `setSupplyCap` exists but no monitoring, no alerts, no governance process.

**Required:**
- Alert at 80%, 90%, 95% utilization
- Governance proposal required for increase
- Automatic mint pause at 100%
- Historical cap change audit trail

### 3.8 Blacklist Financial Impact Not Tracked (HIGH)

**Finding:** Blacklisted addresses' balances frozen but no ledger entry.

**Required:** On blacklist:
1. Move balance to `Encumbered Reserve` account
2. Journal entry: Dr Customer Liability / Cr Encumbered Reserve
3. On unblacklist: Reverse entry
4. Report to compliance/regulators

### 3.9 Bridge Accounting Missing (HIGH)

**Finding:** Bridge lock/burn and mint/release not reflected in financial ledger.

**Required Bridge Accounting:**

**Lock-Mint (Source → Destination):**
```
Source Chain:
1. Dr Customer Liability (Source) / Cr Bridge Locked Reserve
2. Token burned on source

Destination Chain:
3. Dr Bridge Locked Reserve / Cr Customer Liability (Dest)
4. Token minted on destination

Net: Customer liability moved cross-chain. Reserve unchanged.
```

**Burn-Release (Source → Destination):**
```
Source Chain:
1. Dr Customer Liability (Source) / Cr Bridge Locked Reserve
2. Token burned on source

Destination Chain:
3. Dr Bridge Locked Reserve / Cr Customer Liability (Dest)
4. Token minted on destination

Net: Same. Bridge Locked Reserve = sum of all locked across chains.
```

**Reconciliation:** `SUM(Bridge Locked Reserve across chains) == totalLocked()` on each vault.

### 3.10 No Historical Financial Snapshots (MEDIUM)

**Finding:** No point-in-time financial state reconstruction.

**Required:**
- Daily balance sheet snapshots
- Monthly P&L
- Auditor export: all journal entries with hash chain
- Regulatory reporting package (BI, OJK, PPATK)

---

## 4. FINANCIAL INTEGRITY SCORECARD

| Area | Score (1-5) | Critical Issues |
|------|-------------|-----------------|
| Double-Entry Ledger | 1 | **Missing entirely** |
| Arithmetic Precision | 2 | Float used in Python |
| Audit Trail | 1 | Mutable, no hash chain |
| Reconciliation | 1 | **None implemented** |
| Fund Segregation | 1 | Single reserve bucket |
| Issuance Workflow | 1 | Direct mint, no process |
| Redemption Workflow | 1 | Direct burn, no payout |
| Fee Accounting | 1 | **Not implemented** |
| Supply Cap Governance | 2 | Basic cap, no process |
| Bridge Accounting | 1 | **Not implemented** |
| Blacklist Accounting | 1 | **Not implemented** |
| Historical Snapshots | 1 | **Not implemented** |
| **OVERALL** | **1.1** | **FAIL** |

---

## 5. REMEDIATION ROADMAP

### Phase 1: Foundation (Blocks Everything)
1. [ ] Design chart of accounts for IDRC
2. [ ] Implement double-entry ledger tables + migrations
3. [ ] Replace all float arithmetic with integer/Decimal
4. [ ] Add hash-chained audit log
5. [ ] Implement journal entry validation (debit=credit)

### Phase 2: Core Workflows
6. [ ] Implement issuance state machine + ledger entries
7. [ ] Implement redemption state machine + ledger entries
8. [ ] Add fee parameters and collection
9. [ ] Implement supply cap governance + monitoring

### Phase 3: Reconciliation & Reporting
10. [ ] Build daily reconciliation engine
11. [ ] Add discrepancy alerting with thresholds
12. [ ] Implement bridge accounting
13. [ ] Add blacklist/encumbrance accounting
14. [ ] Build financial snapshot system
15. [ ] Create auditor/regulatory export package

### Phase 4: Advanced
16. [ ] Real-time reserve dashboard with ledger backing
17. [ ] Automated regulatory reporting (BI, OJK, PPATK)
18. [ ] Stress testing: simulated bank failure, reorg, key compromise
19. [ ] Independent audit of financial code

---

## 6. VERIFICATION CRITERIA

Each remediation must pass:

| Test | Description |
|------|-------------|
| **Balance Test** | Every journal entry: SUM(debit) == SUM(credit) |
| **Reconciliation Test** | Daily: onchain_supply == ledger_liability ± 0 |
| **Reserve Test** | fiat_reserve >= token_liability (100%+) |
| **Idempotency Test** | Duplicate API calls → single ledger entry |
| **Audit Trail Test** | Hash chain unbroken from genesis |
| **Snapshot Test** | Point-in-time balance sheet matches ledger |
| **Regulatory Export Test** | BI/OJK format generated correctly |

---

**END OF FINANCIAL_INTEGRITY_ASSESSMENT.md**