# BACKUP_AND_RECOVERY.md
# Database Backup and Recovery Guide
**Version:** 1.0
**Date:** 2026-11-20
**Phase:** 5 - Database and Data Governance
**Classification:** OPERATIONS - Internal Use Only

---

## 1. BACKUP STRATEGY

### 1.1 Backup Types

| Backup Type | Frequency | Retention | Storage | Purpose |
|-------------|-----------|-----------|---------|---------|
| **Continuous Archiving (WAL-G)** | Continuous | 30 days | S3/GCS | Point-in-time recovery (PITR) |
| **Daily Logical (pg_dump)** | Daily 02:00 UTC | 90 days | S3/GCS | Schema+data export, cross-version |
| **Weekly Full (pg_basebackup)** | Weekly Sun 03:00 UTC | 1 year | S3/GCS | Fast restore, replication setup |
| **Monthly Snapshot** | Monthly 1st 04:00 UTC | 7 years | Glacier/Archive | Regulatory compliance |

### 1.2 Backup Commands

#### Continuous Archiving (WAL-G) - RECOMMENDED

```bash
# Install WAL-G
wget https://github.com/wal-g/wal-g/releases/download/v2.0.1/wal-g.linux-amd64.tar.gz
tar -xzf wal-g.linux-amd64.tar.gz
sudo mv wal-g /usr/local/bin/

# Configure environment
export WALG_S3_PREFIX=s3://idrc-backups/wal
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx
export PGDATA=/var/lib/postgresql/16/main

# Start continuous archiving
wal-g wal-push $PGDATA/pg_wal

# Schedule base backup (daily)
0 2 * * * /usr/local/bin/wal-g backup-push $PGDATA
```

#### Daily Logical Backup (pg_dump)

```bash
#!/bin/bash
# /usr/local/bin/backup_daily.sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/daily"
S3_BUCKET="s3://idrc-backups/daily"

pg_dump -h localhost -U postgres -d idrc \
  --format=custom \
  --compress=6 \
  --no-owner \
  --no-privileges \
  --file="${BACKUP_DIR}/idrc_${DATE}.dump"

# Verify backup
pg_restore --list "${BACKUP_DIR}/idrc_${DATE}.dump" > /dev/null

# Upload to S3
aws s3 cp "${BACKUP_DIR}/idrc_${DATE}.dump" "${S3_BUCKET}/"

# Cleanup local (keep 7 days)
find ${BACKUP_DIR} -name "idrc_*.dump" -mtime +7 -delete
```

#### Weekly Physical Backup (pg_basebackup)

```bash
#!/bin/bash
# /usr/local/bin/backup_weekly.sh
DATE=$(date +%Y%m%d)
BACKUP_DIR="/backups/weekly/${DATE}"

pg_basebackup -h localhost -U replicator -D ${BACKUP_DIR} \
  -Ft -z -P -R -X stream

# Upload to S3
tar -czf ${BACKUP_DIR}.tar.gz ${BACKUP_DIR}
aws s3 cp ${BACKUP_DIR}.tar.gz s3://idrc-backups/weekly/
```

---

## 2. RECOVERY PROCEDURES

### 2.1 Point-in-Time Recovery (PITR) - WAL-G

```bash
# Stop PostgreSQL
sudo systemctl stop postgresql

# Clean data directory
rm -rf /var/lib/postgresql/16/main/*

# Restore from WAL-G (specify timestamp)
wal-g backup-fetch LATEST /var/lib/postgresql/16/main

# Create recovery.signal for PITR
touch /var/lib/postgresql/16/main/recovery.signal

# Configure recovery (postgresql.auto.conf)
cat >> /var/lib/postgresql/16/main/postgresql.auto.conf << EOF
restore_command = 'wal-g wal-fetch "%f" "%p"'
recovery_target_time = '2026-11-20 10:30:00+00'
recovery_target_action = 'promote'
EOF

# Start PostgreSQL
sudo systemctl start postgresql

# Monitor recovery
tail -f /var/log/postgresql/postgresql-16-main.log
```

### 2.2 Full Restore from pg_dump

```bash
# Create empty database
sudo -u postgres createdb idrc_restore

# Restore
pg_restore -h localhost -U postgres -d idrc_restore \
  --jobs=4 \
  --no-owner \
  --no-privileges \
  /backups/daily/idrc_20261120_020000.dump

# Verify
psql -h localhost -U postgres -d idrc_restore -c "SELECT count(*) FROM users;"
```

### 2.3 Replica Promotion (Failover)

```bash
# On replica
sudo -u postgres pg_ctl promote -D /var/lib/postgresql/16/main

# Update application config to point to new primary
# Update DNS/load balancer
```

---

## 3. BACKUP VERIFICATION

### 3.1 Automated Verification (Daily)

```bash
#!/bin/bash
# /usr/local/bin/verify_backup.sh

LATEST_DUMP=$(ls -t /backups/daily/idrc_*.dump | head -1)

# Test restore to temporary database
pg_restore --list "$LATEST_DUMP" > /dev/null || exit 1

# Verify table counts
pg_restore -d idrc_verify --clean --if-exists "$LATEST_DUMP" 2>/dev/null
psql -d idrc_verify -c "SELECT 'users' as table, count(*) FROM users UNION ALL SELECT 'journal_entries', count(*) FROM journal_entries UNION ALL SELECT 'accounts', count(*) FROM accounts;"

# Cleanup
dropdb idrc_verify
```

### 3.2 Monthly Full Verification

- Restore weekly backup to staging environment
- Run full test suite against restored data
- Verify financial reconciliation reports match
- Document results in backup log

---

## 4. DISASTER RECOVERY RUNBOOK

### 4.1 RTO/RPO Targets

| Scenario | RTO | RPO |
|----------|-----|-----|
| Single table corruption | 15 min | 5 min |
| Database server failure | 30 min | 5 min (WAL-G) |
| Data center outage | 2 hours | 1 hour |
| Region outage | 4 hours | 1 hour |

### 4.2 Escalation Contacts

| Role | Contact | Backup |
|------|---------|--------|
| Primary DBA | dba-primary@idrc.io | dba-secondary@idrc.io |
| DevOps Lead | devops@idrc.io | platform@idrc.io |
| Security Officer | security@idrc.io | cis@idrc.io |

---

## 4. BACKUP MONITORING

### 4.1 Key Metrics

- Backup duration < 30 min (daily), < 2 hours (weekly)
- Backup size growth rate
- WAL archiving lag < 5 min
- Backup success rate > 99.9%

### 4.2 Alerting Rules

```yaml
# Prometheus alerts
- alert: BackupFailed
  expr: increase(backup_job_failed_total[1h]) > 0
  severity: critical

- alert: WALArchivingLag
  expr: pg_wal_archiving_lag_seconds > 300
  severity: warning

- alert: BackupSizeAnomaly
  expr: abs(backup_size_bytes - avg_over_time(backup_size_bytes[7d])) > 2 * stddev_over_time(backup_size_bytes[7d])
  severity: warning
```

---

## 5. DATA RETENTION POLICY

| Data Category | Retention | Legal Basis | Disposal Method |
|---------------|-----------|-------------|-----------------|
| Financial Ledger (journal_entries, accounts) | Permanent | Banking Law, BI Regulation | Never delete |
| Audit Logs | 7 years + current | UU PDP, Banking Law | Secure deletion after expiry |
| KYC Profiles | 7 years after relationship ends | UU PDP, AML Law | Anonymize after expiry |
| Sanctions Screenings | 7 years | AML Law | Secure deletion |
| Token/Bridge/Reserve Events | 7 years | Audit requirement | Archive to cold storage |
| Financial Snapshots | 7 years | Audit requirement | Archive to cold storage |
| API Access Logs | 1 year | Security monitoring | Auto-purge |
| Reconciliations | 7 years | Audit requirement | Archive |

---

## 6. ENCRYPTION

### 6.1 At Rest

- **Database**: PostgreSQL TDE (tablespace encryption) or filesystem encryption (LUKS)
- **Backups**: AES-256 (WAL-G / pg_dump --compress with encryption)
- **S3 Storage**: SSE-S3 or SSE-KMS

### 6.2 In Transit

- **Client-Database**: TLS 1.3 (require SSL mode=verify-full)
- **Replication**: TLS 1.3
- **Backup Transfer**: TLS 1.3 (S3 HTTPS)

### 6.3 Key Management

- **Database Keys**: HashiCorp Vault / AWS KMS
- **Backup Keys**: Separate KMS key per environment
- **Rotation**: Annual for data keys, 90 days for master keys


---

## 7. ACCESS CONTROL

### 7.1 Database Roles

```sql
-- Read-only for analytics
CREATE ROLE analytics_ro;
GRANT CONNECT ON DATABASE idrc TO analytics_ro;
GRANT USAGE ON SCHEMA public TO analytics_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analytics_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analytics_ro;

-- Application role (least privilege)
CREATE ROLE idrc_app;
GRANT CONNECT ON DATABASE idrc TO idrc_app;
GRANT USAGE ON SCHEMA public TO idrc_app;
GRANT SELECT, INSERT, UPDATE ON journal_entries, journal_lines, accounts TO idrc_app;
GRANT SELECT, INSERT ON token_events, reserve_events, bridge_events TO idrc_app;
GRANT SELECT ON users, api_keys TO idrc_app;

-- Backup role
CREATE ROLE backup_user;
GRANT CONNECT ON DATABASE idrc TO backup_user;
GRANT USAGE ON SCHEMA public TO backup_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO backup_user;
```

### 7.2 Row-Level Security (PII)

```sql
-- Enable RLS on users table
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Policy: users can only see their own data
CREATE POLICY user_own_data ON users
  FOR ALL TO idrc_app
  USING (id = current_setting('app.current_user_id')::uuid);

-- Policy: admins see all
CREATE POLICY admin_all_data ON users
  FOR ALL TO admin_role
  USING (true);
```

---

## 8. AUDIT TRAIL

### 8.1 Audit Log Integrity

- Hash-chained audit logs (each entry references previous)
- Periodic anchoring to blockchain (Merkle root)
- Immutable storage (WORM) for audit logs

### 8.2 Audit Queries

```sql
-- Verify audit chain integrity
WITH chain AS (
  SELECT id, prev_hash,
         sha256(concat(id, action, resource_type, resource_id, details, created_at, lag(prev_hash) over (order by created_at))) as computed_hash
  FROM audit_logs
  ORDER BY created_at
)
SELECT * FROM chain WHERE prev_hash != computed_hash AND prev_hash IS NOT NULL;

-- Financial audit trail
SELECT je.entry_number, je.entry_date, je.description,
       SUM(jl.debit) as total_debit, SUM(jl.credit) as total_credit
FROM journal_entries je
JOIN journal_lines jl ON je.id = jl.journal_entry_id
WHERE je.status = 'POSTED'
GROUP BY je.id
HAVING SUM(jl.debit) != SUM(jl.credit);
```

---

## 9. TESTING SCHEDULE

| Test | Frequency | Scope |
|------|-----------|-------|
| Daily backup verification | Daily | pg_dump restore test |
| Weekly PITR test | Weekly | WAL-G recovery to staging |
| Monthly full DR drill | Monthly | Region failover simulation |
| Quarterly chaos engineering | Quarterly | Random failure injection |
| Annual compliance audit | Annual | Third-party audit |

---

## 10. DOCUMENTATION

- All procedures documented in Confluence/GitBook
- Runbooks version-controlled in Git
- Post-incident reviews within 48 hours
- Quarterly runbook review and update

---

**END OF BACKUP_AND_RECOVERY.md**