# THREAT_MODEL.md
# IDRC Threat Model
**Version:** 2.0
**Date:** 2026-11-18
**Phase:** 1 - System Architecture Reconstruction
**Methodology:** STRIDE + Attack Trees + MITRE ATT&CK Mapping
**Classification:** CONFIDENTIAL

---

## 1. SYSTEM OVERVIEW FOR THREAT MODELING

### 1.1 Assets (What We Protect)

| Asset | Classification | Value | Impact if Compromised |
|-------|----------------|-------|----------------------|
| **IDRC Token Contract** | Critical | $$$$$ | Unauthorized mint/burn = direct financial loss |
| **Reserve Funds (Bank)** | Critical | $$$$$ | Loss of collateral = insolvency |
| **Multisig Private Keys** | Critical | $$$$$ | Full governance compromise |
| **Oracle Private Keys** | Critical | $$$$ | Fake reserve data = false solvency |
| **Bridge Relayer Keys** | Critical | $$$$ | Unauthorized cross-chain mint |
| **User PII (KYC)** | High | $$$ | Regulatory fines (UU PDP), reputational |
| **Financial Ledger** | High | $$$ | Audit failure, regulatory action |
| **API Infrastructure** | Medium | $$ | Service disruption, data leak |
| **Monitoring/Alerting** | Medium | $$ | Blind to attacks |

### 1.2 Trust Boundaries

```
TRUST BOUNDARIES (per TRUST_BOUNDARY.md):

TB1: USER ↔ API GATEWAY (Untrusted → Semi-Trusted)
TB2: API GATEWAY ↔ DOMAIN SERVICES (Semi-Trusted → Trusted)
TB3: DOMAIN SERVICES ↔ DATABASE (Trusted → Trusted)
TB4: DOMAIN SERVICES ↔ BLOCKCHAIN ADAPTER (Trusted → External)
TB5: BLOCKCHAIN ADAPTER ↔ SMART CONTRACTS (External → Immutable)
TB6: ORACLE RELAYER ↔ PROOF OF RESERVE (External → Critical)
TB7: BRIDGE RELAYER ↔ BRIDGE CONTRACTS (External → Critical)
TB8: BANK CUSTODIAN ↔ ORACLE RELAYER (External → Trusted)
TB9: KYC/AML PROVIDERS ↔ COMPLIANCE ENGINE (External → Trusted)
TB10: ADMIN/OPERATOR ↔ MULTISIG (Human → Critical)
```

---

## 2. STRIDE ANALYSIS PER COMPONENT

### 2.1 Smart Contracts (Token, Reserve, Bridge, Multisig)

| Threat | Vectors | Likelihood | Impact | Mitigations |
|--------|---------|------------|--------|-------------|
| **Spoofing** | Fake permit sigs, replay attacks | Medium | High | Low-s enforcement; nonce; chainId in domain |
| **Tampering** | Storage corruption, delegatecall | Low | Critical | Immutable after deploy; upgrade timelock; formal verification |
| **Repudiation** | No audit trail for admin actions | Medium | High | Event emission; hash-chained audit log |
| **Info Disclosure** | On-chain data public | N/A | Low | Design for transparency; no secrets on-chain |
| **DoS** | Gas griefing, pause abuse | Medium | Medium | Gas bounds; circuit breakers; multisig pause |
| **Elevation** | Role escalation, owner drain | Low | Critical | Role hierarchy; multisig threshold; timelocks |

### 2.2 API Gateway & Services

| Threat | Vectors | Likelihood | Impact | Mitigations |
|--------|---------|------------|--------|-------------|
| **Spoofing** | Stolen JWT/API key, caller param injection | High | High | Short JWT expiry; refresh tokens; derive caller from auth |
| **Tampering** | Request modification, idempotency bypass | Medium | High | TLS 1.3; idempotency keys; request signing |
| **Repudiation** | Missing audit logs, log deletion | Medium | Medium | Hash-chained audit logs; blockchain anchoring |
| **Info Disclosure** | Error leaks, excessive logging, PII in logs | High | High | Standardized errors; PII redaction; log sanitization |
| **DoS** | No rate limit, large payloads, WS flood | High | Medium | Rate limiting; payload limits; WS auth |
| **Elevation** | RBAC bypass, role confusion | Medium | Critical | OZ AccessControl; integration tests; least privilege |

### 2.3 Oracle & Bridge Relayers

| Threat | Vectors | Likelihood | Impact | Mitigations |
|--------|---------|------------|--------|-------------|
| **Spoofing** | Fake attestation, compromised relayer key | Medium | Critical | Threshold signatures; HSM; MPC |
| **Tampering** | Modified balance in transit | Low | Critical | Signed attestations; on-chain verification |
| **Repudiation** | Oracle denies update | Low | Medium | On-chain events; audit log |
| **Info Disclosure** | Bank API keys, oracle keys | Medium | High | Vault/HSM; rotation; least privilege |
| **DoS** | Oracle/bridge down, spam | Medium | Medium | Circuit breakers; health checks; redundancy |
| **Elevation** | Single key controls mint | High | Critical | Decentralized bridge; threshold sigs |

### 2.4 Database & Infrastructure

| Threat | Vectors | Likelihood | Impact | Mitigations |
|--------|---------|------------|--------|-------------|
| **Spoofing** | DB credential theft | Medium | High | Vault; rotation; IAM |
| **Tampering** | SQL injection, direct DB write | Medium | High | Parameterized queries; read replicas; audit logs |
| **Repudiation** | Deleted audit logs | Medium | Medium | Hash chain; blockchain anchor; immutable storage |
| **Info Disclosure** | Backup leak, PII exposure | Medium | High | Encryption at rest; PII encryption; access controls |
| **DoS** | DB overload, connection exhaustion | Medium | Medium | Connection pooling; read replicas; rate limits |
| **Elevation** | Container escape, K8s RBAC bypass | Low | Critical | Non-root containers; PSS; network policies |

---

## 3. ATTACK TREES

### 3.1 Unauthorized Token Minting (Critical)

```
UNAUTHORIZED MINT
├── Compromise MINTER_ROLE holder
│   ├── Phishing multisig signer
│   ├── Malware on signer device
│   ├── Supply chain attack (hw wallet)
│   └── Social engineering
├── Exploit mint() vulnerability
│   ├── Reentrancy (mitigated: ReentrancyGuard)
│   ├── Access control bypass (mitigated: OZ AccessControl)
│   ├── Supply cap bypass (mitigated: check in mint)
│   └── Permit replay (mitigated: low-s, nonce, chainId)
├── Compromise Bridge Relayer
│   ├── Single key theft (CURRENT: HIGH RISK)
│   ├── MPC node compromise (TARGET: threshold)
│   └── Bridge contract vulnerability
├── Compromise Oracle
│   ├── Fake high balance → collateralization pass
│   └── Combined with mint exploit
└── Governance Attack
    ├── Multisig threshold reached (2-of-3)
    ├── Upgrade to malicious implementation
    └── Emergency pause bypass
```

**Risk Score: HIGH (Current) → MEDIUM (Target with mitigations)**

### 3.2 Reserve Data Manipulation (Critical)

```
RESERVE MANIPULATION
├── Oracle Key Compromise
│   ├── Single EOA key theft (CURRENT)
│   ├── HSM breach (TARGET: mitigated)
│   └── Insider threat
├── Bank API Compromise
│   ├── Credential theft
│   ├── Man-in-the-middle
│   └── Bank insider
├── Attestation Forgery
│   ├── Weak signature algorithm
│   ├── Certificate authority compromise
│   └── Replay old attestation
├── Threshold Bypass
│   ├── < threshold oracles collude
│   ├── Sybil attack on oracle network
│   └── Key share reconstruction
└── On-Chain Verification Bypass
    ├── verifyProof() bug (CURRENT: always true)
    └── Reserve contract upgrade
```

**Risk Score: CRITICAL (Current) → HIGH (Target)**

### 3.3 Bridge Fund Theft (Critical)

```
BRIDGE THEFT
├── Relayer Key Compromise
│   ├── Single key (CURRENT: HIGH)
│   ├── MPC threshold breach (TARGET)
│   └── Smart contract bug in relay()
├── Replay Attack
│   ├── Nonce reuse (mitigated: processedNonces)
│   ├── Cross-chain replay (mitigated: chainId)
│   └── Event replay after reorg
├── Finality Failure
│   ├── Source chain reorg after mint
│   ├── Light client sync failure
│   └── Relayer processes unfinalized block
├── Verification Bypass
│   ├── No verification (CURRENT)
│   ├── Merkle proof forgery
│   └── Block header forgery
└── Rate Limit Bypass
    ├── No limits (CURRENT)
    ├── Distributed relay attack
    └── Gas griefing on destination
```

**Risk Score: CRITICAL (Current) → MEDIUM (Target)**

### 3.4 User Data Breach (High)

```
PII BREACH
├── Database Compromise
│   ├── SQL injection
│   ├── Credential stuffing
│   ├── Backup theft
│   └── Insider access
├── API Leak
│   ├── Excessive fields in response
│   ├── Error message PII
│   ├── Log injection
│   └── Debug endpoint exposure
├── KYC Provider Breach
│   ├── Vendor compromise
│   ├── Data in transit
│   └── Shared credentials
└── Compliance Failure
    ├── No encryption at rest (CURRENT)
    ├── No retention policy
    ├── No access logging
    └── No breach notification
```

**Risk Score: HIGH (Current) → LOW (Target)**

---

## 4. MITRE ATT&CK MAPPING

| Technique | ID | Applicable Components | Detection |
|-----------|----|----------------------|-----------|
| **Supply Chain Compromise** | T1195 | Hardware wallets, Dependencies | SBOM; signed releases; dependency scanning |
| **Phishing** | T1566 | Multisig signers, Operators | MFA; hardware wallets; security training |
| **Exploit Public-Facing Application** | T1190 | API Gateway | WAF; rate limiting; input validation |
| **Private Keys Theft** | T1650 | Oracle, Bridge, Multisig | HSM; MPC; rotation; audit |
| **Man-in-the-Middle** | T1557 | Bank API, Oracle comms | mTLS; certificate pinning |
| **SQL Injection** | T1190 | Database | Parameterized queries; WAF |
| **Data from Local System** | T1005 | PII in database | Encryption; DLP; access controls |
| **Exfiltration Over Web Service** | T1567 | API, Database | Egress filtering; DLP; monitoring |
| **Account Manipulation** | T1098 | RBAC, Multisig | Audit logs; approval workflows |
| **Service Stop** | T1489 | Oracle, Bridge, API | Health checks; redundancy; alerting |
| **Resource Hijacking** | T1496 | K8s, Containers | Resource limits; admission control |

---

## 5. THREAT ACTORS

| Actor | Motivation | Capability | Target Assets |
|-------|------------|------------|---------------|
| **External Hacker** | Financial gain | High | Token minting, Bridge, User funds |
| **Malicious Insider** | Financial/Revenge | High (access) | Keys, Database, Governance |
| **Nation State** | Disruption/Intel | Very High | All critical infrastructure |
| **Competitor** | Market advantage | Medium | User data, Strategy |
| **Hacktivist** | Reputation | Medium | Availability, Defacement |
| **Script Kiddie** | Notoriety | Low | DoS, Defacement |

---

## 6. RISK ASSESSMENT MATRIX

| Risk ID | Threat | Likelihood | Impact | Risk Level | Current Controls | Residual Risk |
|---------|--------|------------|--------|------------|------------------|---------------|
| R-001 | Unauthorized mint via minter key compromise | Medium | Critical | **CRITICAL** | Multisig 2-of-3 | HIGH |
| R-002 | Unauthorized mint via bridge relayer key | High | Critical | **CRITICAL** | Single key | CRITICAL |
| R-003 | Fake reserve data via oracle key | Medium | Critical | **CRITICAL** | Single key | CRITICAL |
| R-004 | Reserve data manipulation via bank API | Low | Critical | **HIGH** | None (mock) | HIGH |
| R-005 | PII breach via database | Medium | High | **HIGH** | None (plaintext) | HIGH |
| R-006 | DoS on API/mint endpoint | High | Medium | **HIGH** | None | HIGH |
| R-007 | Governance takeover via multisig | Low | Critical | **HIGH** | 2-of-3 | MEDIUM |
| R-008 | Smart contract bug (reentrancy, logic) | Low | Critical | **HIGH** | ReentrancyGuard; tests | MEDIUM |
| R-009 | Bridge reorg double-mint | Medium | High | **HIGH** | None | HIGH |
| R-010 | Oracle staleness → false solvency | Medium | High | **HIGH** | Monitor only | HIGH |
| R-011 | Upgrade to malicious contract | Low | Critical | **HIGH** | Timelock (config only) | HIGH |
| R-012 | KYC/AML bypass (mock) | High | High | **HIGH** | None (mock) | HIGH |
| R-013 | Database credential leak | Medium | High | **MEDIUM** | Env vars | MEDIUM |
| R-014 | Container escape | Low | High | **MEDIUM** | Non-root | LOW |
| R-015 | Log tampering | Medium | Medium | **MEDIUM** | None | MEDIUM |

---

## 7. SECURITY REQUIREMENTS (Derived from Threats)

### 7.1 Critical (Must Implement Before Mainnet)

| Req ID | Requirement | Threats Addressed |
|--------|-------------|-------------------|
| SEC-001 | Decentralized bridge (LayerZero/Axelar/MPC) | R-002, R-009 |
| SEC-002 | Multi-oracle threshold signatures (3-of-5) | R-003, R-004 |
| SEC-003 | Real KYC/AML integration | R-012 |
| SEC-004 | PII encryption at rest + in transit | R-005 |
| SEC-005 | Rate limiting + idempotency on all endpoints | R-006 |
| SEC-006 | TimelockController for upgrades (48h) | R-011 |
| SEC-007 | Circuit breakers: oracle stale → pause mint | R-010 |
| SEC-008 | Hash-chained audit logs + blockchain anchoring | R-015 |
| SEC-009 | verifyProof() implementation | R-003 |
| SEC-010 | Permit low-s enforcement | R-001 |
| SEC-011 | Bridge finality verification | R-009 |
| SEC-012 | Secrets management (Vault/ExternalSecrets) | R-013 |

### 7.2 High (Pre-Launch)

| Req ID | Requirement | Threats Addressed |
|--------|-------------|-------------------|
| SEC-013 | Multisig simulation before execute | R-007 |
| SEC-013 | Role separation (admin ≠ upgrader ≠ minter) | R-007, R-011 |
| SEC-014 | Gas bounds on all transact() calls | R-006 |
| SEC-015 | Distributed tracing (Jaeger) | R-006, R-015 |
| SEC-016 | K8s network policies + PSS | R-014 |
| SEC-017 | SBOM generation + dependency scanning | R-008 |
| SEC-018 | Chaos engineering + DR drills | R-008, R-009 |

### 7.3 Medium (Post-Launch)

| Req ID | Requirement | Threats Addressed |
|--------|-------------|-------------------|
| SEC-019 | Anomaly detection on financial flows | R-001, R-002 |
| SEC-020 | ZK-proof reserve verification | R-003, R-004 |
| SEC-021 | Formal verification (Certora) | R-008 |
| SEC-022 | Bug bounty program (Immunefi) | All |

---

## 8. INCIDENT RESPONSE MAPPING

| Incident Type | Detection | Response | Recovery |
|---------------|-----------|----------|----------|
| **Unauthorized Mint** | Supply monitor alert | 1. Pause token (multisig)<br>2. Freeze bridge<br>3. Investigate source | 1. Identify exploit<br>2. Upgrade if contract bug<br>3. Rotate keys<br>4. Reconcile supply |
| **Oracle Compromise** | Stale/fake balance alert | 1. Pause minting (circuit breaker)<br>2. Rotate oracle keys<br>3. Verify reserve with bank | 1. Multi-sig oracle deploy<br>2. Re-process attestations<br>3. Reconcile reserve |
| **Bridge Hack** | Unusual mint rate alert | 1. Pause bridge (multisig)<br>2. Identify unauthorized mints<br>3. Coordinate with destination chain | 1. Relayer rotation<br>2. Upgrade bridge<br>3. User compensation plan |
| **PII Breach** | DLP alert / External report | 1. Contain (revoke creds, isolate DB)<br>2. Assess scope (PDP UU 72h)<br>3. Notify regulator/users | 1. Rotate all keys<br>2. Re-encrypt data<br>3. Forensic audit |
| **Governance Attack** | Role change alert | 1. Emergency pause<br>2. Multisig owner rotation<br>3. Timelock enforcement | 1. Key rotation<br>2. Security audit<br>3. Legal action |

---

## 9. SECURITY TESTING REQUIREMENTS

| Test Type | Scope | Frequency | Tools |
|-----------|-------|-----------|-------|
| **Static Analysis** | All contracts | Every PR | Slither (full detectors) |
| **Fuzz Testing** | All contracts | Every PR | Echidna (10k runs) |
| **Invariant Testing** | Critical properties | Every PR | Foundry (5k runs, depth 100) |
| **Formal Verification** | Token, Reserve, Bridge | Pre-mainnet | Certora/Halmos |
| **Penetration Test** | API, Infrastructure | Quarterly | External firm |
| **Smart Contract Audit** | All contracts | Pre-mainnet + annual | Top-tier firm (Trail of Bits, etc.) |
| **Dependency Scan** | All deps | Every PR | Trivy, OWASP Dependency Check |
| **Secret Scan** | Repo, CI, Containers | Every push | TruffleHog, GitLeaks |
| **Chaos Engineering** | Infrastructure | Monthly | Litmus, Chaos Mesh |
| **DR Drill** | Full stack | Quarterly | Runbook execution |

---

## 10. RESIDUAL RISK ACCEPTANCE

| Risk | Residual Level | Acceptance Authority | Review Date |
|------|----------------|---------------------|-------------|
| R-001: Minter key compromise | MEDIUM | CISO + Legal | Quarterly |
| R-007: Governance takeover | MEDIUM | Board | Quarterly |
| R-008: Contract bug | MEDIUM | Lead Auditor | Per audit |
| R-013: DB credential leak | MEDIUM | CISO | Monthly |
| R-015: Log tampering | MEDIUM | CISO | Monthly |

**Note:** CRITICAL and HIGH residual risks **cannot be accepted** for mainnet launch.

---

**END OF THREAT_MODEL.md**