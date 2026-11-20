# DATA_RETENTION_POLICY.md
# Data Retention Policy
**Version:** 1.0
**Date:** 2026-11-20
**Phase:** 5 - Database and Data Governance
**Classification:** CONFIDENTIAL - Legal/Compliance
**Owner:** Data Protection Officer (DPO)

---

## 1. PURPOSE

This policy defines the retention periods, storage requirements, and disposal procedures for all data processed by the IDRC system, in compliance with:
- UU No. 27/2022 (Personal Data Protection Law - UU PDP)
- Bank Indonesia Regulation (Payment System, Stablecoin)
- AML/CFT Law (Anti-Money Laundering)
- Indonesian Banking Law (Financial records)
- ISO 27001 (Information Security)

---

## 2. DATA CLASSIFICATION

| Classification | Description | Examples |
|----------------|-------------|----------|
| PUBLIC | No harm if disclosed | Marketing materials, public API docs |
| INTERNAL | Internal use only | System configs, operational metrics |
| CONFIDENTIAL | Harm if disclosed | Financial models, user analytics |
| RESTRICTED | Severe harm if disclosed | PII, KYC data, private keys, audit logs, financial ledger |

---

## 3. RETENTION SCHEDULE

### 3.1 Financial Records (RESTRICTED)

| Data Type | Retention Period | Start Trigger | Legal Basis | Disposal |
|-----------|------------------|---------------|-------------|----------|
| Journal Entries | Permanent | Entry posted | Banking Law Art. 46, BI Reg | Never delete; archive only |
| Accounts (Chart of Accounts) | Permanent | Creation | Banking Law | Never delete |
| Financial Snapshots | 7 years + current | Snapshot date | Audit standards, BI Reg | Secure archive |
| Reconciliations | 7 years | Resolution date | Audit standards | Secure archive |
| Token Events | 7 years | Event timestamp | BI Reg, Audit | Archive to cold storage |
| Reserve Events | 7 years | Event timestamp | BI Reg, Audit | Archive to cold storage |
| Bridge Events | 7 years | Event timestamp | BI Reg, Audit | Archive to cold storage |
| Fee Revenue Records | 10 years | Fiscal year end | Tax Law | Archive |

### 3.2 Compliance & KYC (RESTRICTED)

| Data Type | Retention Period | Start Trigger | Legal Basis | Disposal |
|-----------|------------------|---------------|-------------|----------|
| KYC Profiles | 7 years after relationship ends | Account closure | UU PDP Art. 15, AML Law | Anonymize + secure delete |
| KYC Documents (KTP, selfie) | 7 years after relationship ends | Account closure | UU PDP Art. 15 | Secure delete (shred digital) |
| Sanctions Screenings | 7 years | Screening date | AML Law Art. 15 | Secure delete |
| Transaction Monitoring Alerts | 7 years | Alert date | AML Law | Secure delete |
| SARs (Suspicious Activity Reports) | 7 years | Filing date | AML Law | Secure archive |
| PEP Lists | Duration of relationship + 7 years | List update | AML Law | Secure delete |

### 3.3 User & Access Data (CONFIDENTIAL/RESTRICTED)

| Data Type | Retention Period | Start Trigger | Legal Basis | Disposal |
|-----------|------------------|---------------|-------------|----------|
| User Accounts | 7 years after closure | Account closure | UU PDP Art. 15 | Anonymize (retain hash) |
| API Keys | 1 year after revocation | Revocation date | Security | Secure delete |
| Audit Logs | 7 years | Log timestamp | UU PDP, Banking Law | Secure archive |
| Login History | 2 years | Login date | Security | Auto-purge |
| Session Data | 30 days | Session expiry | Security | Auto-purge |

### 3.4 Operational Data (INTERNAL/CONFIDENTIAL)

| Data Type | Retention Period | Start Trigger | Legal Basis | Disposal |
|-----------|------------------|---------------|-------------|----------|
| System Metrics | 1 year | Collection date | Operations | Auto-purge |
| Application Logs | 90 days | Log date | Operations | Auto-purge |
| Error Logs | 1 year | Error date | Debugging | Auto-purge |
| Backup Metadata | 7 years | Backup date | DR compliance | Archive |
| Rate Limit Logs | 30 days | Log date | Security | Auto-purge |

### 3.4 Public Data (PUBLIC)

| Data Type | Retention Period | Notes |
|-----------|------------------|-------|
| Public API Documentation | Until superseded | Version controlled |
| Marketing Materials | 3 years | Marketing archive |
| Whitepapers | Permanent | Legal archive |

---

## 4. DATA SUBJECT RIGHTS (UU PDP)

### 4.1 Rights Supported

| Right | Implementation | SLA |
|-------|----------------|-----|
| Access | Self-service portal + API | 14 days |
| Rectification | Self-service + admin review | 30 days |
| Erasure (Right to be Forgotten) | Anonymization workflow | 30 days* |
| Restriction | Account freeze | 14 days |
| Portability | JSON/CSV export | 30 days |
| Objection | Opt-out flags | Immediate |

*Financial records exempt per Banking Law Art. 46 - anonymize instead of delete

### 4.2 Erasure Procedure

1. Verify identity (KYC re-check)
2. Check legal holds (litigation, audit, regulatory)
3. If financial records: anonymize (replace PII with hash, retain amounts)
4. If non-financial: secure delete (cryptographic erasure)
5. Update all references (foreign keys to anonymized IDs)
6. Log erasure in audit trail
7. Confirm to data subject

---

## 5. STORAGE & ENCRYPTION

### 5.1 At Rest

| Tier | Encryption | Key Management |
|------|------------|----------------|
| Hot (Primary DB) | PostgreSQL TDE / LUKS | HashiCorp Vault |
| Warm (Replicas) | Same as primary | Same as primary |
| Cold (Backups/S3) | AES-256 (SSE-KMS) | AWS KMS / Vault |
| Archive (Glacier) | AES-256 (SSE-KMS) | AWS KMS |

### 5.2 Key Rotation

| Key Type | Rotation Period | Process |
|----------|-----------------|---------|
| Data Encryption Keys | 90 days | Automated via Vault |
| Master Keys | 1 year | Manual ceremony |
| Backup Keys | 1 year | Separate from production |
| API Keys | 90 days | Automated rotation |

---

## 6. DISPOSAL PROCEDURES

### 6.1 Digital Disposal

| Media | Method | Verification |
|-------|--------|--------------|
| Database Records | Cryptographic erasure (key deletion) + overwrite | Audit log entry |
| S3 Objects | SSE-KMS key deletion + version purge | S3 inventory report |
| Database Backups | Key deletion + object expiry | Backup inventory |
| Logs | Automated TTL expiry | Log retention report |

### 6.2 Physical Disposal (if applicable)

| Media | Method | Certificate |
|-------|--------|-------------|
| Hard Drives | NIST 800-88 Purge (3-pass) | Destruction certificate |
| SSDs | Crypto erase + physical destroy | Destruction certificate |
| Paper Records | Cross-cut shred (P-4) | Destruction log |

---

## 7. LEGAL HOLDS

### 7.1 Trigger Events

- Regulatory investigation (BI, OJK, PPATK)
- Litigation (court order, preservation letter)
- Internal audit finding
- Suspected fraud/security incident

### 7.2 Hold Procedure

1. Legal issues hold notice to DPO
2. DPO notifies engineering/data team
3. Implement hold (prevent deletion, snapshot data)
4. Document hold scope and duration
5. Quarterly review until release

### 7.3 Hold Release

- Legal confirms no further need
- DPO authorizes release
- Resume normal retention schedule
- Document release date

---

## 8. COMPLIANCE MONITORING

### 8.1 Automated Checks

```sql
-- Daily: Check for overdue deletions
SELECT 'users' as table, count(*) as overdue
FROM users 
WHERE deleted_at IS NOT NULL 
  AND deleted_at < NOW() - INTERVAL '7 years'
UNION ALL
SELECT 'kyc_profiles', count(*)
FROM kyc_profiles
WHERE relationship_ended < NOW() - INTERVAL '7 years'
AND status != 'ANONYMIZED';
```

### 8.2 Quarterly Review

- Review retention schedule against new regulations
- Verify disposal procedures executed
- Check legal hold register
- Update policy for new data types

### 8.3 Annual Audit

- Third-party compliance audit
- Penetration test on disposal procedures
- Key rotation verification
- Report to Board/Compliance Committee

---

## 9. INCIDENT RESPONSE

### 9.1 Retention Violations

| Severity | Trigger | Response |
|----------|---------|----------|
| Critical | PII retained beyond legal limit | Immediate containment, DPO notification, 72h report to Kominfo |
| High | Financial records deleted prematurely | Restore from backup, root cause analysis |
| Medium | Backup retained beyond schedule | Delete excess, update automation |
| Low | Logs retained beyond schedule | Delete, update TTL |

### 9.2 Breach Notification (UU PDP Art. 46)

- 72 hours to Kominfo (Ministry of Communication)
- Without undue delay to affected data subjects
- Document in breach register

---

## 10. TRAINING & AWARENESS

| Audience | Frequency | Content |
|----------|-----------|---------|
| All Staff | Annual | Data classification, handling, reporting |
| Engineering | Quarterly | Secure coding, deletion procedures, key management |
| DPO/Compliance | Semi-annual | Regulatory updates, audit prep |
| New Hires | Onboarding | Policy overview, incident reporting |

---

## 11. POLICY REVIEW

| Trigger | Review Cycle |
|---------|--------------|
| Regulatory Change | Within 30 days of publication |
| Business Change | Within 60 days of launch |
| Incident | Within 14 days of closure |
| Scheduled | Annual (Q1) |

Approval: DPO to CISO to Legal to Board

---

**END OF DATA_RETENTION_POLICY.md**