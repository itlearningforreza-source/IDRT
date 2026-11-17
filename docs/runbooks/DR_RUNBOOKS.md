# IDRC Disaster Recovery Runbooks
## Complete Operational Procedures for Incident Response

---

# RUNBOOK INDEX

| ID | Scenario | Severity | RTO | Page |
|----|----------|----------|-----|------|
| DR-01 | Emergency Pause Activation | P1 | 5 min | 3 |
| DR-02 | Oracle Failure / Stale Data | P1 | 15 min | 6 |
| DR-03 | Bridge Halt / Stuck Nonces | P2 | 30 min | 10 |
| DR-04 | Database Corruption / Loss | P1 | 10 min | 14 |
| DR-05 | Key Compromise / Signer Loss | P1 | 1 hour | 18 |
| DR-06 | Smart Contract Critical Bug | P1 | 2 hours | 22 |
| DR-07 | Regulatory Action / Compliance Mode | P2 | 30 min | 26 |
| DR-08 | Force Majeure / Region Outage | P1 | 1 hour | 30 |

---

# DR-01: EMERGENCY PAUSE ACTIVATION

## Overview
Activate global pause on all token transfers, minting, and burning via multisig.

## Trigger Conditions
- Suspected smart contract exploit
- Oracle manipulation detected
- Bridge exploit in progress
- Regulatory order to halt operations
- Internal security team detects anomaly

## Prerequisites
- Access to multisig wallet (Gnosis Safe / custom MultisigWallet)
- Minimum threshold signers available (3-of-5 or configured threshold)
- Secure communication channel (Keybase/Signal) established

## Procedure

### Step 1: Verify Need (2 min)
```bash
# Check current pause state
cast call <TOKEN_ADDRESS> "paused()(bool)" --rpc-url $MAINNET_RPC

# Check recent events for anomalies
cast logs --from-block latest --to-block latest   --address <TOKEN_ADDRESS>   --rpc-url $MAINNET_RPC
```

### Step 2: Coordinate Signers (1 min)
- Alert all signers via secure channel
- Confirm quorum available
- Designate transaction proposer

### Step 3: Propose Pause Transaction (1 min)
```bash
# Encode pause calldata
cast calldata "pause()"

# Submit via multisig (proposer)
cast send <MULTISIG_ADDRESS>   "submitTransaction(address,uint256,bytes)"   <TOKEN_ADDRESS> 0 <PAUSE_CALLDATA>   --private-key $SIGNER1_KEY --rpc-url $MAINNET_RPC
```

### Step 4: Collect Confirmations (1 min)
```bash
# Each signer confirms
cast send <MULTISIG_ADDRESS>   "confirmTransaction(uint256)" <TX_ID>   --private-key $SIGNER_KEY --rpc-url $MAINNET_RPC
```

### Step 5: Execute (immediate after threshold)
```bash
# Execute after timelock (if any)
cast send <MULTISIG_ADDRESS>   "executeTransaction(uint256)" <TX_ID>   --private-key $SIGNER_KEY --rpc-url $MAINNET_RPC
```

### Step 6: Verify (30 sec)
```bash
cast call <TOKEN_ADDRESS> "paused()(bool)" --rpc-url $MAINNET_RPC
# Should return true
```

## Post-Action
- Document incident in incident tracker
- Notify stakeholders (Slack #incidents, email)
- Begin root cause analysis
- Plan unpause procedure (DR-01-UNPAUSE)

## Rollback: UNPAUSE
Same process calling `unpause()` instead of `pause()`

---

# DR-02: ORACLE FAILURE / STALE DATA

## Overview
Oracle stops updating fiat balance, collateralization ratio becomes unreliable.

## Trigger Conditions
- `lastOracleUpdate()` > 1 hour (configurable threshold)
- Oracle signer key compromised
- Bank API unavailable
- Oracle transaction reverts consistently

## Detection
```bash
# Check oracle staleness
cast call <RESERVE_ADDRESS> "lastOracleUpdate()(uint256)" --rpc-url $MAINNET_RPC
cast call <RESERVE_ADDRESS> "fiatBalanceIdr()(uint256)" --rpc-url $MAINNET_RPC
cast call <RESERVE_ADDRESS> "oracle()(address)" --rpc-url $MAINNET_RPC

# Check collateralization
cast call <RESERVE_ADDRESS> "reserveRatio(uint256)" <TOTAL_SUPPLY> --rpc-url $MAINNET_RPC
```

## Procedure

### Phase 1: Immediate Assessment (5 min)
1. Check oracle address balance (ETH for gas)
2. Verify bank API status via monitoring
3. Check oracle relayer logs
4. Determine if oracle signer key issue or bank API issue

### Phase 2: Switch to Backup Oracle (10 min)
```bash
# If backup oracle configured, update oracle address
# Requires DEFAULT_ADMIN_ROLE on Reserve contract

cast send <RESERVE_ADDRESS>   "setOracle(address)" <BACKUP_ORACLE_ADDRESS>   --private-key $ADMIN_KEY --rpc-url $MAINNET_RPC
```

### Phase 3: Manual Attestation (if no backup)
If no backup oracle available:
1. Obtain signed bank statement (PDF)
2. Compute SHA-256: `sha256sum bank_statement.pdf`
3. Submit audit proof via multisig:
```bash
cast send <RESERVE_ADDRESS>   "submitAuditProof(bytes32,uint256)" <HASH> <FIAT_AMOUNT>   --private-key $AUDITOR_KEY --rpc-url $MAINNET_RPC
```

### Phase 4: Activate Circuit Breaker (if under-collateralized)
```bash
# If collateralization < 100%, activate emergency pause
# See DR-01
```

## Monitoring During Incident
```bash
# Watch for oracle updates
watch -n 30 "cast call <RESERVE_ADDRESS> 'lastOracleUpdate()(uint256)' --rpc-url $MAINNET_RPC"
```

## Recovery Validation
- Oracle updates resume within expected interval
- Collateralization ratio returns to >= 100%
- Alerting returns to normal

---

# DR-03: BRIDGE HALT / STUCK NONCES

## Overview
Bridge relayer stops processing, nonces accumulate, users cannot complete transfers.

## Trigger Conditions
- Relayer process crashed
- Nonce gap detected (nonce N+1 processed but N pending)
- Relayer out of gas/funds
- Destination chain RPC failure
- Nonce replay protection triggered incorrectly

## Detection
```bash
# Check pending nonces on source vault
cast call <VAULT_ADDRESS> "totalLocked()(uint256)" --rpc-url $SOURCE_RPC

# Check processed nonces on relayer
cast call <RELAYER_ADDRESS> "isProcessed(uint256,uint256)" <SRC_CHAIN> <NONCE> --rpc-url $SRC_RPC

# Check relayer balance
cast balance <RELAYER_ADDRESS> --rpc-url $SRC_RPC
```

## Procedure

### Scenario A: Relayer Crashed / Out of Funds
1. Fund relayer address with native token
2. Restart relayer process
3. Monitor for automatic catch-up

### Scenario B: Nonce Gap (Manual Relay Required)
1. Identify stuck nonce(s)
2. Verify source chain lock event exists
3. Manually call relay on destination:
```bash
cast send <RELAYER_ADDRESS>   "relay(uint256,uint256,uint256,address,uint256,address)"   <SRC_CHAIN> <DST_CHAIN> <NONCE> <RECIPIENT> <AMOUNT> <TOKEN>   --private-key $RELAYER_KEY --rpc-url $DST_RPC
```

### Scenario C: Replay Protection False Positive
1. Check if nonce actually processed
2. If not, verify relayer state
3. May require contract upgrade to fix nonce tracking

### Scenario D: Destination Chain Issue
1. Switch to backup RPC endpoint
2. If chain halted, pause bridge vault on source:
```bash
cast send <VAULT_ADDRESS> "pause()" --private-key $ADMIN_KEY --rpc-url $SRC_RPC
```

## Recovery
- All pending nonces processed
- Bridge volume returns to normal
- Alerting clears

---

# DR-04: DATABASE CORRUPTION / LOSS

## Overview
Primary database (PostgreSQL) corrupted, unavailable, or data loss detected.

## Trigger Conditions
- API returns 500 errors on database queries
- Replication lag > 5 minutes
- Backup verification fails
- Disk full / corruption alerts

## Procedure

### Phase 1: Immediate Response (2 min)
1. Check database status:
```bash
kubectl get pods -n idrc -l app=postgres
kubectl logs -n idrc -l app=postgres --tail=100
```

2. Check replication status:
```sql
SELECT * FROM pg_stat_replication;
```

### Phase 2: Failover to Replica (5 min)
```bash
# Promote replica to primary
kubectl exec -n idrc postgres-replica-0 -- pg_ctl promote -D /var/lib/postgresql/data

# Update DNS / service to point to new primary
kubectl patch service postgres -n idrc -p '{"spec":{"selector":{"role":"primary"}}}'
```

### Phase 3: Verify Application Connectivity (2 min)
```bash
# Test API health
curl -f https://api.idrc.id/health

# Run smoke tests
pytest tests/test_api_smoke.py -v
```

### Phase 4: Restore Replica (async)
```bash
# Rebuild former primary as new replica
# Use pg_basebackup from new primary
```

### Phase 5: Data Integrity Check (10 min)
```sql
-- Compare critical table counts
SELECT 'users', COUNT(*) FROM users;
SELECT 'transactions', COUNT(*) FROM transactions;
SELECT 'balances', COUNT(*) FROM balances;

-- Verify against blockchain state
-- Cross-reference with indexer data
```

## Recovery Validation
- API health checks pass
- Replication lag < 10 seconds
- All critical tables accessible
- No data loss confirmed

---

# DR-05: KEY COMPROMISE / SIGNER LOSS

## Overview
Multisig signer key compromised, hardware wallet lost, or signer unavailable.

## Trigger Conditions
- Signer reports lost/stolen hardware wallet
- Suspicious transactions from signer address
- Signer unreachable for extended period
- Security audit reveals key exposure

## Procedure

### Scenario A: Single Signer Compromised (Non-threshold)
1. **Immediate**: Revoke compromised signer's access if possible
2. **Emergency**: If threshold at risk, activate emergency pause (DR-01)
3. **Recovery**: Add replacement signer via multisig

### Step-by-Step:
```bash
# 1. Propose remove compromised signer
cast send <MULTISIG_ADDRESS>   "submitTransaction(address,uint256,bytes)"   <MULTISIG_ADDRESS> 0   $(cast calldata "removeOwner(address,uint256)" <COMPROMISED_ADDRESS> <NEW_THRESHOLD>)   --private-key $SIGNER1_KEY --rpc-url $MAINNET_RPC

# 2. Confirm with remaining signers
cast send <MULTISIG_ADDRESS>   "confirmTransaction(uint256)" <TX_ID>   --private-key $SIGNER2_KEY --rpc-url $MAINNET_RPC

# 3. Execute after timelock
cast send <MULTISIG_ADDRESS>   "executeTransaction(uint256)" <TX_ID>   --private-key $SIGNER3_KEY --rpc-url $MAINNET_RPC

# 4. Add replacement signer
cast send <MULTISIG_ADDRESS>   "submitTransaction(address,uint256,bytes)"   <MULTISIG_ADDRESS> 0   $(cast calldata "addOwnerWithThreshold(address,uint256)" <NEW_SIGNER> <THRESHOLD>)   --private-key $SIGNER1_KEY --rpc-url $MAINNET_RPC
```

### Scenario B: Threshold Signers Compromised (Critical)
1. **Immediate**: Emergency pause (DR-01)
2. **Legal**: Engage legal counsel, law enforcement
3. **Recovery**: Deploy new multisig, migrate ownership via governance

### Scenario C: Signer Unavailable (Non-compromised)
1. If threshold still met: Continue operations
2. If threshold at risk: Add replacement signer (same as Scenario A)
3. Document in incident tracker

## Key Rotation (Quarterly Routine)
```bash
# Rotate all signer keys quarterly
# 1. Generate new keys on hardware wallets
# 2. Add new signers via multisig
# 3. Remove old signers via multisig
# 3. Verify new configuration
```

## Shamir Backup Recovery (Emergency)
If all hardware wallets lost:
1. Gather 3-of-5 Shamir shares from secure locations
2. Reconstruct private key using SLIP-39 tool
3. Import to new hardware wallets
4. Execute key rotation

---

# DR-06: SMART CONTRACT CRITICAL BUG

## Overview
Critical vulnerability discovered in deployed contracts requiring immediate upgrade.

## Trigger Conditions
- Security audit finds critical vulnerability
- Bug bounty report with working exploit
- Internal testing reveals fund loss risk
- Exploit detected in mempool/mainnet

## Procedure

### Phase 1: Containment (0-30 min)
1. **Emergency Pause** (DR-01) - Stop all token movement
2. **Assess Impact** - Determine affected contracts, funds at risk
3. **Communicate** - Alert signers, legal, communications team

### Phase 2: Fix Development (30 min - 2 hours)
1. Develop fix in isolated environment
2. Write comprehensive tests
3. Deploy to testnet for verification
3. **External review** - At least 2 independent reviewers

### Phase 3: Upgrade Deployment (1-2 hours)
```bash
# 1. Deploy new implementation
forge create contracts/token/IDRCToken.sol:IDRCToken   --constructor-args "IDR Coin" "IDRC" <ADMIN> <MINTER> <PAUSER> <UPGRADER> <BURNER> <BLACKLISTER> 10000000000000000000000000000   --rpc-url $MAINNET_RPC --private-key $DEPLOYER_KEY

# 2. Verify implementation
cast call <NEW_IMPL> "name()(string)" --rpc-url $MAINNET_RPC

# 3. Propose upgrade via multisig
cast send <MULTISIG_ADDRESS>   "submitTransaction(address,uint256,bytes)"   <PROXY_ADMIN_ADDRESS> 0   $(cast calldata "upgrade(address,address)" <PROXY_ADDRESS> <NEW_IMPL>)   --private-key $SIGNER1_KEY --rpc-url $MAINNET_RPC

# 4. Collect confirmations & execute
cast send <MULTISIG_ADDRESS> "confirmTransaction(uint256)" <TX_ID> --private-key $SIGNER2_KEY --rpc-url $MAINNET_RPC
cast send <MULTISIG_ADDRESS> "executeTransaction(uint256)" <TX_ID> --private-key $SIGNER3_KEY --rpc-url $MAINNET_RPC
```

### Phase 4: State Migration (if needed)
If storage layout changed:
```bash
# Call migration function on new implementation
cast send <PROXY_ADDRESS>   "migrateFromV1()"   --private-key $UPGRADER_KEY --rpc-url $MAINNET_RPC
```

### Phase 5: Verification & Unpause (30 min)
1. Verify all balances preserved
2. Test mint/burn/transfer
3. Check collateralization
4. **Unpause** (DR-01 reverse)
5. Monitor for 1 hour

## Post-Incident
- Publish postmortem within 48 hours
- Update bug bounty payouts
- Review audit scope for future

---

# DR-07: REGULATORY ACTION / COMPLIANCE MODE

## Overview
Regulator issues order requiring operational changes (freeze accounts, enhanced KYC, transaction limits).

## Trigger Conditions
- Official order from BI/OJK/PPATK
- Court order to freeze specific addresses
- New regulation requiring immediate compliance
- Sanctions list updates affecting users

## Procedure

### Scenario A: Address Freeze Order
```bash
# Blacklist specific addresses via multisig
cast send <MULTISIG_ADDRESS>   "submitTransaction(address,uint256,bytes)"   <TOKEN_ADDRESS> 0   $(cast calldata "blacklist(address)" <TARGET_ADDRESS>)   --private-key $SIGNER1_KEY --rpc-url $MAINNET_RPC

# Confirm & execute
cast send <MULTISIG_ADDRESS> "confirmTransaction(uint256)" <TX_ID> --private-key $SIGNER2_KEY --rpc-url $MAINNET_RPC
cast send <MULTISIG_ADDRESS> "executeTransaction(uint256)" <TX_ID> --private-key $SIGNER3_KEY --rpc-url $MAINNET_RPC
```

### Scenario B: Transaction Limits
Deploy compliance module or update limits via governance:
```bash
# Update supply cap or add per-address limits
# Requires governance proposal + timelock
```

### Scenario C: Enhanced KYC Mode
1. Activate compliance mode flag via admin
2. API enforces enhanced KYC for all new transactions
3. Existing users grandfathered with timeline

### Scenario D: Sanctions List Update
1. Download updated OFAC/UN/EU lists
2. Batch blacklist via multisig
3. Screen all existing users against new lists
4. Notify affected users

## Compliance Mode API Changes
- All mint/burn require KYC Tier 2+
- Transaction limits: IDR 100M/day for Tier 1
- Enhanced monitoring alerts
- Automated SAR filing for suspicious patterns

---

# DR-08: FORCE MAJEURE / REGION OUTAGE

## Overview
Primary cloud region (AWS ap-southeast-1 / GCP asia-southeast1) completely unavailable.

## Trigger Conditions
- Cloud provider region-wide outage
- Natural disaster affecting data center
- Network partition isolating region
- Government-ordered internet shutdown

## Procedure

### Phase 1: Detection (2 min)
```bash
# Check region health
aws ec2 describe-instance-status --region ap-southeast-1
# Or check cloud provider status page

# Check Kubernetes cluster
kubectl get nodes --context=idrc-prod-primary
```

### Phase 2: Failover to DR Region (10 min)
```bash
# 1. Switch DNS to DR region (Route53 / Cloud DNS)
aws route53 change-resource-record-sets --hosted-zone-id $ZONE_ID --change-batch file://dr-failover.json

# 2. Scale up DR region deployments
kubectl scale deployment api --replicas=10 --context=idrc-prod-dr
kubectl scale deployment oracle --replicas=3 --context=idrc-prod-dr
kubectl scale deployment indexer --replicas=3 --context=idrc-prod-dr

# 3. Promote DR database
kubectl exec -n idrc postgres-dr-0 -- pg_ctl promote -D /var/lib/postgresql/data
```

### Phase 3: Verify Services (10 min)
```bash
# Health checks
curl -f https://api.idrc.id/health
curl -f https://api.idrc.id/metrics

# Test critical flows
# Mint, burn, transfer, bridge
```

### Phase 4: Update Monitoring (5 min)
- Update Prometheus scrape targets
- Update alertmanager routes
- Verify Grafana dashboards

### Phase 5: Communicate (5 min)
- Status page update
- Slack #incidents notification
- Email stakeholders

## Recovery
- Monitor primary region recovery
- Plan failback during low-traffic window
- Document lessons learned

---

# CONTACT ESCALATION MATRIX

| Role | Primary | Secondary | Contact Method |
|------|---------|-----------|----------------|
| **Incident Commander** | CTO | VP Eng | Phone + Signal |
| **Smart Contract Lead** | Lead Contract Eng | Senior Contract Eng | Signal |
| **Infrastructure Lead** | DevOps Lead | Senior DevOps | Phone + Slack |
| **Security Lead** | CISO | Security Eng | Signal (encrypted) |
| **Legal/Compliance** | General Counsel | Compliance Officer | Phone + Email |
| **Communications** | Head of Comms | PR Agency | Slack + Email |
| **Banking Partner** | Relationship Manager | Backup RM | Phone (24/7) |
| **Cloud Support** | AWS/GCP TAM | Enterprise Support | Support Portal |

---

# POST-INCIDENT PROCESS

## Within 1 Hour
- [ ] Incident contained
- [ ] Initial communication sent
- [ ] Timeline documented

## Within 4 Hours
- [ ] Root cause identified
- [ ] Fix deployed (if applicable)
- [ ] Stakeholder update sent

## Within 24 Hours
- [ ] Full incident report drafted
- [ ] Action items assigned
- [ ] Monitoring enhanced

## Within 48 Hours
- [ ] Public postmortem published (if user-facing)
- [ ] Action items tracked in Jira/Linear
- [ ] Runbook updated if gaps found

## Within 1 Week
- [ ] All action items completed or scheduled
- [ ] Runbook improvements deployed
- [ ] Team retrospective held

---

# RUNBOOK MAINTENANCE

| Task | Frequency | Owner |
|------|-----------|-------|
| Review all runbooks | Quarterly | DevOps Lead |
| Tabletop exercises | Monthly | Incident Commander |
| Contact list update | Monthly | DevOps Lead |
| DR region failover test | Quarterly | Infrastructure Lead |
| Key rotation drill | Quarterly | Security Lead |
| Multisig transaction drill | Monthly | Smart Contract Lead |

---

**Document Version**: 1.0
**Classification**: CONFIDENTIAL - Internal Use Only
**Next Review**: Monthly
**Approved By**: [CTO/CISO/COO]
