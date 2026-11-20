# PII_ENCRYPTION_GUIDE.md
# PII Encryption Implementation Guide
**Version:** 1.0
**Date:** 2026-11-20
**Phase:** 5 - Database and Data Governance
**Classification:** CONFIDENTIAL - Security

---

## 1. OVERVIEW

This guide details the implementation of Personally Identifiable Information (PII) encryption for the IDRC system, ensuring compliance with UU PDP (Indonesian Data Protection Law) and banking regulations.

### 1.1 PII Data Categories

| Category | Fields | Classification |
|----------|--------|----------------|
| Direct Identifiers | Full name, NIK (KTP), email, phone, address | RESTRICTED |
| Biometric | Selfie, fingerprint, face scan | RESTRICTED |
| Financial | Bank account, transaction history | RESTRICTED |
| Authentication | Password hashes, API keys, session tokens | RESTRICTED |
| Location | IP address, geolocation | CONFIDENTIAL |

### 1.2 Encryption Requirements

| Requirement | Standard |
|-------------|----------|
| Algorithm | AES-256-GCM (authenticated encryption) |
| Key Derivation | Argon2id (for passwords) / HKDF (for data keys) |
| Key Rotation | 90 days (data keys), 1 year (master keys) |
| Key Storage | HashiCorp Vault / AWS KMS / Hardware Security Module |
| IV/Nonce | 96-bit random per encryption (never reuse) |
| Associated Data | Include table name, column name, record ID for integrity |

---

## 2. ARCHITECTURE

### 2.1 Encryption Layers

```
+-----------------------------------------------------------+
|                    APPLICATION LAYER                        |
|  +---------------+  +---------------+  +-----------------+  |
|  |  Field-Level  |  |  Record-Level |  |  Application-   |  |
|  |  Encryption   |  |  Encryption   |  |  Level (TLS)    |  |
+---------------+  +---------------+  +-----------------+  |
+-----------------------------------------------------------+
|                    DATABASE LAYER                           |
|  +---------------+  +---------------+  +-----------------+  |
|  |  Column       |  |  Tablespace   |  |  Backup         |  |
|  |  Encryption   |  |  Encryption   |  |  Encryption     |  |
+---------------+  +---------------+  +-----------------+  |
+-----------------------------------------------------------+
|                    STORAGE LAYER                            |
|  +---------------+  +---------------+  +-----------------+  |
|  |  Disk         |  |  S3/Backup    |  |  Archive        |  |
|  |  Encryption   |  |  Encryption   |  |  Encryption     |  |
+---------------+  +---------------+  +-----------------+  |
```

### 2.2 Key Hierarchy

```
Master Key (Vault/HSM) - Rotated annually
    |
    +-- Data Encryption Key (DEK) - Rotated 90 days
    |     +-- PII DEK (for direct identifiers)
    |     +-- Financial DEK (for transaction data)
    |     +-- Auth DEK (for passwords, tokens)
    |     +-- KYC DEK (for documents, biometrics)
    |
    +-- Backup Encryption Key (BEK) - Rotated annually
          +-- Per-backup DEK (envelope encryption)
```

---

## 3. IMPLEMENTATION

### 3.1 Field-Level Encryption (Application Layer)

#### Python Implementation

```python
# services/api/utils/pii_encryption.py
import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
import hvac  # HashiCorp Vault client

class PIIEncryption:
    def __init__(self, vault_client: hvac.Client):
        self.vault = vault_client
        self.key_cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    def _get_dek(self, key_name: str) -> bytes:
        """Get Data Encryption Key from Vault with caching"""
        if key_name in self.key_cache:
            cached = self.key_cache[key_name]
            if time.time() - cached['timestamp'] < self.cache_ttl:
                return cached['key']
        
        # Generate or retrieve DEK from Vault
        response = self.vault.secrets.transit.encrypt_data(
            name=key_name,
            plaintext=base64.b64encode(os.urandom(32)).decode()
        )
        dek = base64.b64decode(response['data']['ciphertext'])
        
        self.key_cache[key_name] = {'key': dek, 'timestamp': time.time()}
        return dek
    
    def encrypt(self, plaintext: str, key_name: str, associated_data: bytes = b'') -> dict:
        """Encrypt PII field with AES-256-GCM"""
        dek = self._get_dek(key_name)
        aesgcm = AESGCM(dek)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), associated_data)
        
        return {
            'ciphertext': base64.b64encode(ciphertext).decode(),
            'nonce': base64.b64encode(nonce).decode(),
            'key_version': self._get_key_version(key_name)
        }
    
    def decrypt(self, encrypted_data: dict, key_name: str, associated_data: bytes = b'') -> str:
        """Decrypt PII field"""
        dek = self._get_dek(key_name)
        aesgcm = AESGCM(dek)
        ciphertext = base64.b64decode(encrypted_data['ciphertext'])
        nonce = base64.b64decode(encrypted_data['nonce'])
        
        plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data)
        return plaintext.decode()


# Usage in models
class User(Base):
    # Encrypted fields
    email_encrypted = Column(JSONB, nullable=True)  # {ciphertext, nonce, key_version}
    phone_encrypted = Column(JSONB, nullable=True)
    address_encrypted = Column(JSONB, nullable=True)
    
    # Non-encrypted (for indexing/search)
    email_hash = Column(String(64), nullable=True, index=True)  # SHA-256
    
    @hybrid_property
    def email(self):
        if self.email_encrypted:
            return pii_encrypt.decrypt(self.email_encrypted, 'pii_identifiers', 
                                       f"users:{self.id}:email".encode())
        return None
    
    @email.setter
    def email(self, value):
        if value:
            self.email_encrypted = pii_encrypt.encrypt(value, 'pii_identifiers',
                                                       f"users:{self.id}:email".encode())
            self.email_hash = hashlib.sha256(value.encode()).hexdigest()
        else:
            self.email_encrypted = None
            self.email_hash = None
```

### 3.2 Database-Level Encryption

#### PostgreSQL TDE (Transparent Data Encryption)

```bash
# Option 1: Tablespace encryption (PostgreSQL 15+)
CREATE TABLESPACE encrypted_ts LOCATION '/mnt/encrypted' 
  WITH (encryption_algorithm='AES256');

CREATE TABLE users (
    ...
) TABLESPACE encrypted_ts;

# Option 2: Column-level with pgcrypto
CREATE EXTENSION pgcrypto;

-- Encrypted column
ALTER TABLE users ADD COLUMN email_encrypted BYTEA;

-- Insert with encryption
INSERT INTO users (email_encrypted) 
VALUES (pgp_sym_encrypt('user@example.com', current_setting('app.encryption_key')));

-- Decrypt on read
SELECT pgp_sym_decrypt(email_encrypted, current_setting('app.encryption_key')) 
FROM users WHERE id = '...';
```

#### Tablespace Encryption (LUKS + Filesystem)

```bash
# Create encrypted volume
cryptsetup luksFormat /dev/nvme1n1 --type luks2 --cipher aes-xts-plain64 --key-size 512
cryptsetup open /dev/nvme1n1 postgres_encrypted
mkfs.ext4 /dev/mapper/postgres_encrypted
mount /dev/mapper/postgres_encrypted /var/lib/postgresql/16/main

# Auto-mount on boot (/etc/crypttab)
postgres_encrypted /dev/nvme1n1 none luks,discard
```

### 3.3 Key Management with HashiCorp Vault

```hcl
# Vault policy for PII encryption
path "transit/encrypt/pii_identifiers" {
  capabilities = ["update"]
}

path "transit/decrypt/pii_identifiers" {
  capabilities = ["update"]
}

path "transit/encrypt/pii_financial" {
  capabilities = ["update"]
}

path "transit/decrypt/pii_financial" {
  capabilities = ["update"]
}

path "transit/encrypt/pii_kyc" {
  capabilities = ["update"]
}

path "transit/decrypt/pii_kyc" {
  capabilities = ["update"]
}

# Key rotation (automated via Vault)
# Transit keys support automatic rotation
```

```bash
# Enable transit engine
vault secrets enable transit

# Create encryption keys
vault write -f transit/keys/pii_identifiers type=aes256-gcm96
vault write -f transit/keys/pii_financial type=aes256-gcm96
vault write -f transit/keys/pii_kyc type=aes256-gcm96
vault write -f transit/keys/pii_auth type=aes256-gcm96

# Enable automatic rotation (daily check, rotate if needed)
vault write transit/keys/pii_identifiers/config auto_rotate_period=7776000  # 90 days
```

---

## 4. SPECIFIC FIELD IMPLEMENTATIONS

### 4.1 User Model

```python
class User(Base):
    # Direct identifiers (encrypted)
    email_encrypted = Column(JSONB, nullable=True)      # AES-256-GCM
    phone_encrypted = Column(JSONB, nullable=True)
    full_name_encrypted = Column(JSONB, nullable=True)
    address_encrypted = Column(JSONB, nullable=True)
    
    # Searchable hashes (not encrypted, but not reversible)
    email_hash = Column(String(64), nullable=True, index=True)    # SHA-256
    phone_hash = Column(String(64), nullable=True, index=True)
    
    # KYC data (encrypted)
    nik_encrypted = Column(JSONB, nullable=True)          # KTP number
    kyc_documents_encrypted = Column(JSONB, nullable=True) # Base64 encoded docs
    kyc_extracted_data_encrypted = Column(JSONB, nullable=True)
    
    # Authentication (hashed, not encrypted)
    hashed_password = Column(String(255), nullable=True)   # Argon2id
    
    # Non-PII
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 4.2 KYC Profile

```python
class KYCProfile(Base):
    __tablename__ = 'kyc_profiles'
    
    user_id = Column(UUID, ForeignKey('users.id'), primary_key=True)
    
    # Encrypted PII
    document_front_encrypted = Column(JSONB, nullable=True)    # KTP front
    document_back_encrypted = Column(JSONB, nullable=True)     # KTP back
    selfie_encrypted = Column(JSONB, nullable=True)            # Selfie with KTP
    extracted_data_encrypted = Column(JSONB, nullable=True)    # OCR results
    
    # Metadata (non-PII)
    tier = Column(Enum(KYCTier), default=KYCTier.TIER_0)
    status = Column(Enum(KYCStatus), default=KYCStatus.PENDING)
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.LOW)
    verified_at = Column(DateTime, nullable=True)
    kyc_expiry = Column(DateTime, nullable=True)
```

### 4.3 Sanctions Screening

```python
class SanctionsScreening(Base):
    __tablename__ = 'sanctions_screening'
    
    user_id = Column(UUID, ForeignKey('users.id'), nullable=False)
    
    # Encrypted match details (may contain PII from screening provider)
    match_details_encrypted = Column(JSONB, nullable=True)
    
    # Non-PII
    screening_type = Column(String(50))  # ONBOARDING, TRANSACTION, PERIODIC
    provider = Column(String(50))        # CHAINALYSIS, TRM, COMPLYADVANTAGE
    result = Column(Enum(ScreeningResult))
    screened_at = Column(DateTime, default=datetime.utcnow)
```

---

## 5. KEY ROTATION PROCEDURES

### 5.1 Automated Rotation (Vault Transit)

```bash
# Manual rotation
vault write -f transit/keys/pii_identifiers/rotate

# Verify rotation
vault read transit/keys/pii_identifiers
```

### 5.2 Application Key Rotation

```python
# services/api/utils/key_rotation.py
async def rotate_pii_keys():
    """Rotate PII encryption keys - run monthly via cron"""
    vault = hvac.Client()
    
    # Rotate each key
    for key_name in ['pii_identifiers', 'pii_financial', 'pii_kyc', 'pii_auth']:
        # Trigger rotation
        vault.secrets.transit.rotate_key(name=key_name)
        
        # Wait for rotation to complete
        await asyncio.sleep(2)
        
        # Verify new version works
        test_data = "rotation_test"
        encrypted = vault.secrets.transit.encrypt_data(name=key_name, plaintext=base64.b64encode(test_data.encode()).decode())
        decrypted = vault.secrets.transit.decrypt_data(name=key_name, ciphertext=encrypted['data']['ciphertext'])
        assert base64.b64decode(decrypted['data']['plaintext']).decode() == test_data
        
        # Clear application cache
        pii_encrypt.clear_cache(key_name)
        
        # Log rotation
        await log_audit('KEY_ROTATION', f'Rotated {key_name}', success=True)
```

### 5.3 Re-encryption of Existing Data (if needed)

```python
# services/api/utils/reencrypt.py
async def reencrypt_pii_field(table: str, column: str, old_key: str, new_key: str, batch_size: int = 1000):
    """Re-encrypt existing data after key rotation"""
    offset = 0
    while True:
        rows = await db.execute(
            f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL LIMIT :limit OFFSET :offset",
            {'limit': batch_size, 'offset': offset}
        )
        if not rows:
            break
        
        for row in rows:
            decrypted = pii_encrypt.decrypt(row[column], old_key)
            reencrypted = pii_encrypt.encrypt(decrypted, new_key)
            await db.execute(
                f"UPDATE {table} SET {column} = :value WHERE id = :id",
                {'value': json.dumps(reencrypted), 'id': row.id}
            )
        
        offset += batch_size
        await asyncio.sleep(0.1)  # Throttle
```

---

## 6. COMPLIANCE & AUDITING

### 6.1 Encryption Verification

```sql
-- Verify no plaintext PII in database
SELECT 'users.email' as field, count(*) as plaintext_count
FROM users WHERE email IS NOT NULL AND email NOT LIKE '{"ciphertext"%'
UNION ALL
SELECT 'users.phone', count(*)
FROM users WHERE phone IS NOT NULL AND phone NOT LIKE '{"ciphertext"%'
UNION ALL
SELECT 'kyc_profiles.document_front', count(*)
FROM kyc_profiles WHERE document_front IS NOT NULL AND document_front NOT LIKE '{"ciphertext"%';

-- Verify key versions are current
SELECT column_name, max((value->>'key_version')::int) as max_version
FROM users, jsonb_each(email_encrypted) 
WHERE email_encrypted IS NOT NULL
GROUP BY column_name;
```

### 6.2 Audit Logging

```python
async def log_pii_access(user_id: UUID, action: str, fields: list, success: bool):
    """Log all PII access for audit trail"""
    await log_audit(
        user_id=user_id,
        action=f"PII_{action}",
        resource_type="PII",
        resource_id=str(user_id),
        details={"fields": fields},
        success=success
    )
```

---

## 7. INCIDENT RESPONSE

### 7.1 Key Compromise

1. **Immediate**: Revoke compromised key in Vault
2. **Within 1 hour**: Rotate all related keys
3. **Within 4 hours**: Re-encrypt affected data
4. **Within 24 hours**: Notify DPO and Kominfo (if PII exposed)
5. **Post-incident**: Root cause analysis, update procedures

### 7.2 Vault Unavailability

- **Fallback**: Use cached DEKs (5-min TTL)
- **Alert**: Critical alert to on-call
- **Recovery**: Vault HA cluster failover

---

## 8. TESTING

### 8.1 Unit Tests

```python
def test_pii_encryption_roundtrip():
    encryptor = PIIEncryption(vault_client)
    original = "user@example.com"
    encrypted = encryptor.encrypt(original, 'pii_identifiers', b'users:123:email')
    decrypted = encryptor.decrypt(encrypted, 'pii_identifiers', b'users:123:email')
    assert decrypted == original

def test_pii_encryption_tamper_detection():
    encryptor = PIIEncryption(vault_client)
    original = "user@example.com"
    encrypted = encryptor.encrypt(original, 'pii_identifiers', b'users:123:email')
    # Tamper with ciphertext
    encrypted['ciphertext'] = base64.b64encode(b'tampered').decode()
    with pytest.raises(cryptography.exceptions.InvalidTag):
        encryptor.decrypt(encrypted, 'pii_identifiers', b'users:123:email')
```

### 8.2 Integration Tests

- Test key rotation with live data
- Test re-encryption performance
- Test Vault failover scenarios
- Test backup/restore with encrypted data

---

## 9. PERFORMANCE CONSIDERATIONS

| Optimization | Implementation |
|--------------|----------------|
| Key Caching | 5-min TTL in memory |
| Batch Operations | Encrypt/decrypt in batches |
| Async Vault Calls | Use asyncio for Vault operations |
| Connection Pooling | Vault connection pool (10-20) |
| Searchable Hashes | SHA-256 for equality queries |

---

## 10. REFERENCES

- NIST SP 800-57 - Key Management
- NIST SP 800-38D - AES-GCM
- RFC 5116 - AEAD
- UU PDP (Indonesia) - Articles 15, 16, 46
- PCI DSS v4.0 - Requirement 3
- ISO 27001 - Annex A.10

---

**END OF PII_ENCRYPTION_GUIDE.md**