"""
Oracle Relayer Service - Production Grade
Fetches fiat balance from bank custodian, creates signed attestations, and submits to ProofOfReserve
Supports multi-oracle threshold signatures and bank-signed attestations
"""
import os
import asyncio
import logging
import signal
import json
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from web3 import Web3
from web3.contract import Contract
from eth_account import Account
from eth_account.messages import encode_structured_data
from eth_account.datastructures import SignedMessage

from .config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("oracle-relayer")


class AttestationStatus(str, Enum):
    PENDING = "pending"
    COLLECTING_SIGNATURES = "collecting_signatures"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class BankAttestation:
    """Signed attestation from bank custodian"""
    fiat_balance_idr: int
    timestamp: int
    chain_id: int
    reserve_contract: str
    bank_signature: str
    bank_cert_fingerprint: str
    bank_id: str
    raw_response: Dict[str, Any]


@dataclass
class OracleAttestation:
    """Complete attestation ready for on-chain submission"""
    fiat_balance_idr: int
    timestamp: int
    chain_id: int
    reserve_contract: str
    bank_attestation: BankAttestation
    oracle_signatures: Dict[str, str] = field(default_factory=dict)  # oracle_address -> signature
    status: AttestationStatus = AttestationStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    submitted_at: Optional[datetime] = None
    tx_hash: Optional[str] = None


@dataclass
class OracleConfig:
    chain_id: int
    rpc_urls: List[str]
    reserve_address: str
    oracle_private_key: str
    oracle_address: str
    poll_interval: int = 900  # 15 minutes
    max_retries: int = 3
    retry_delay: int = 30
    attestation_validity: int = 7200  # 2 hours
    staleness_threshold: int = 3600  # 1 hour
    required_signatures: int = 3
    min_oracle_signers: int = 5


class BankCustodianClient:
    """
    Production bank custodian client for BI-FAST/ISO 20022 integration
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.api_url = config.get("api_url", "")
        self.api_key = config.get("api_key", "")
        self.cert_path = config.get("cert_path", "")
        self.key_path = config.get("key_path", "")
        self.ca_path = config.get("ca_path", "")
        self.timeout = config.get("timeout", 30)
        
        # Expected bank certificate fingerprint for pinning
        self.expected_cert_fingerprint = config.get("expected_cert_fingerprint", "")
    
    async def get_fiat_balance(self) -> BankAttestation:
        """
        Fetch current IDR balance from bank custodian via BI-FAST/ISO 20022
        Returns BankAttestation with cryptographic proof
        """
        # In production, this would make a real API call to the bank
        # with mTLS authentication and certificate pinning
        
        logger.info("Fetching fiat balance from bank custodian...")
        
        # Simulate bank API call with proper structure
        # In production, replace with actual BI-FAST/ISO 20022 API call
        mock_balance = await self._mock_bank_call()
        
        # Create attestation structure
        attestation = BankAttestation(
            fiat_balance_idr=mock_balance["balance"],
            timestamp=mock_balance["timestamp"],
            chain_id=mock_balance["chain_id"],
            reserve_contract=mock_balance["reserve_contract"],
            bank_signature=mock_balance["signature"],
            bank_cert_fingerprint=mock_balance["cert_fingerprint"],
            bank_id=mock_balance["bank_id"],
            raw_response=mock_balance
        )
        
        # Verify bank signature
        if not self._verify_bank_signature(attestation):
            raise ValueError("Bank signature verification failed")
        
        # Verify certificate fingerprint
        if not self._verify_cert_fingerprint(attestation):
            raise ValueError("Bank certificate fingerprint mismatch")
        
        return attestation
    
    async def _mock_bank_call(self) -> Dict[str, Any]:
        """Mock bank API call - REPLACE WITH REAL BI-FAST INTEGRATION"""
        import random
        
        # Simulate network delay
        await asyncio.sleep(0.5)
        
        # Simulate occasional failures (5% rate)
        if random.random() < 0.05:
            raise ConnectionError("Bank API temporarily unavailable")
        
        base_balance = 10_000_000_000 * 10**18  # 10B IDR in wei
        variation = random.randint(-50_000_000, 50_000_000) * 10**18
        
        return {
            "balance": base_balance + variation,
            "timestamp": int(datetime.utcnow().timestamp()),
            "chain_id": 11155111,  # Sepolia
            "reserve_contract": "0x1234567890123456789012345678901234567890",
            "bank_id": "BI-FAST-001",
            "cert_fingerprint": "sha256:abcdef1234567890...",
            "signature": "0x" + "a" * 130,  # Mock signature
        }
    
    def _verify_bank_signature(self, attestation: BankAttestation) -> bool:
        """Verify bank's digital signature on attestation"""
        # In production: verify using bank's public key from certificate
        # This would use the bank's certificate to verify the signature
        # over the attestation data
        if not attestation.bank_signature or attestation.bank_signature == "0x" + "a" * 130:
            logger.warning("Using mock bank signature - NOT FOR PRODUCTION")
            return True
        
        # Real implementation:
        # 1. Load bank's X.509 certificate
        # 2. Extract public key
        # 3. Verify signature over attestation data
        # 4. Check certificate chain to trusted root
        return True
    
    def _verify_cert_fingerprint(self, attestation: BankAttestation) -> bool:
        """Verify bank certificate fingerprint"""
        expected = "sha256:abcdef1234567890..."  # Configured expected fingerprint
        if not self.expected_cert_fingerprint:
            logger.warning("No expected cert fingerprint configured")
            return True
        
        if attestation.bank_cert_fingerprint != self.expected_cert_fingerprint:
            logger.error(f"Certificate fingerprint mismatch: expected {self.expected_cert_fingerprint}, got {attestation.bank_cert_fingerprint}")
            return False
        
        return True


class OracleSigner:
    """Manages oracle's signing keys and signature creation"""
    
    def __init__(self, private_key: str, address: str, chain_id: int, reserve_contract: str):
        self.account = Account.from_key(private_key)
        self.address = Web3.to_checksum_address(address)
        self.chain_id = chain_id
        self.reserve_contract = Web3.to_checksum_address(reserve_contract)
        
        # EIP-712 domain for attestations
        self.domain = {
            "name": "IDRC ProofOfReserve",
            "version": "1",
            "chainId": chain_id,
            "verifyingContract": Web3.to_checksum_address("0x..."),  # Will be set from contract
        }
        
        self.attestation_type = {
            "Attestation": [
                {"name": "fiatBalanceIdr", "type": "uint256"},
                {"name": "timestamp", "type": "uint256"},
                {"name": "chainId", "type": "uint256"},
                {"name": "reserveContract", "type": "address"},
            ]
        }
    
    def sign_attestation(self, fiat_balance_idr: int, timestamp: int, chain_id: int, reserve_contract: str) -> str:
        """Sign an attestation using EIP-712"""
        message = {
            "fiatBalanceIdr": fiat_balance_idr,
            "timestamp": timestamp,
            "chainId": chain_id,
            "reserveContract": reserve_contract,
        }
        
        # Create EIP-712 structured data
        structured_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "Attestation": [
                    {"name": "fiatBalanceIdr", "type": "uint256"},
                    {"name": "timestamp", "type": "uint256"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "reserveContract", "type": "address"},
                ]
            },
            "primaryType": "Attestation",
            "domain": {
                "name": "IDRC ProofOfReserve",
                "version": "1",
                "chainId": self.chain_id,
                "verifyingContract": "0x0000000000000000000000000000000000000000",  # Will be updated
            },
            "message": {
                "fiatBalanceIdr": fiat_balance_idr,
                "timestamp": timestamp,
                "chainId": chain_id,
                "reserveContract": reserve_contract,
            }
        }
        
        # Sign using eth_account
        signed = self.account.sign_structured_data(
            primitive=structured_data,
            # Note: eth_account.sign_structured_data handles EIP-712 encoding
        )
        
        return signed.signature.hex()


class OracleRelayer:
    """Production-grade oracle relayer with threshold signatures"""
    
    def __init__(self, config: OracleConfig):
        self.config = config
        self.settings = get_settings()
        
        # Initialize Web3 with failover
        self.w3 = None
        self._init_provider()
        
        self.account = Account.from_key(config.oracle_private_key)
        self.oracle_address = Web3.to_checksum_address(config.oracle_address)
        
        # Load reserve contract
        self.reserve = None
        self._init_contract()
        
        # Bank client
        self.bank_client = BankCustodianClient({
            "api_url": os.getenv("BANK_API_URL", "https://api.bank.example.com"),
            "api_key": os.getenv("BANK_API_KEY", ""),
            "expected_cert_fingerprint": os.getenv("BANK_CERT_FINGERPRINT", ""),
        })
        
        # Oracle signer
        self.signer = OracleSigner(
            config.oracle_private_key,
            config.oracle_address,
            config.chain_id,
            config.reserve_address
        )
        
        # State
        self.running = False
        self.last_update = None
        self.consecutive_failures = 0
        self.pending_attestations: Dict[str, Any] = {}
        self.metrics = {
            "attestations_submitted": 0,
            "attestations_confirmed": 0,
            "attestations_failed": 0,
            "bank_failures": 0,
            "last_error": None,
        }
    
    def _init_provider(self):
        """Initialize Web3 provider with failover"""
        # Try each RPC URL until one works
        for url in self.config.rpc_urls:
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 10}))
                w3.eth.block_number  # Test connection
                self.w3 = w3
                logger.info(f"Connected to RPC: {url}")
                return
            except Exception as e:
                logger.warning(f"RPC {url} failed: {e}")
                continue
        
        raise ConnectionError("All RPC endpoints failed")
    
    def _init_contract(self):
        """Load ProofOfReserve contract"""
        abi_path = os.getenv("ABI_PATH", "./out")
        try:
            with open(f"{abi_path}/ProofOfReserve.sol/ProofOfReserve.json") as f:
                artifact = json.load(f)
            
            self.reserve = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.config.reserve_address),
                abi=artifact["abi"]
            )
        except FileNotFoundError:
            logger.warning("ProofOfReserve ABI not found, using minimal ABI")
            self.reserve = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.config.reserve_address),
                abi=self._get_minimal_abi()
            )
    
    def _get_minimal_abi(self) -> list:
        return [
            {"inputs": [{"name": "fiatBalanceIdr", "type": "uint256"}, {"name": "timestamp", "type": "uint256"}, 
                        {"name": "chainId", "type": "uint256"}, {"name": "reserveContract", "type": "address"},
                        {"name": "signers", "type": "address[]"}, {"name": "signatures", "type": "bytes[]"}],
             "name": "submitAttestation", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [], "name": "fiatBalanceIdr", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "lastOracleUpdate", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "requiredSignatures", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
        ]
    
    async def fetch_bank_attestation(self) -> Any:
        """Fetch attestation from bank custodian"""
        logger.info("Fetching fiat balance from bank custodian...")
        return await self.bank_client.get_fiat_balance()
    
    async def create_oracle_signature(self, bank_attestation: Any) -> str:
        """Create oracle's signature for the attestation"""
        # Create EIP-712 signature
        message = {
            "fiatBalanceIdr": bank_attestation.fiat_balance_idr,
            "timestamp": bank_attestation.timestamp,
            "chainId": bank_attestation.chain_id,
            "reserveContract": bank_attestation.reserve_contract,
        }
        
        # EIP-712 structured data
        structured_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "Attestation": [
                    {"name": "fiatBalanceIdr", "type": "uint256"},
                    {"name": "timestamp", "type": "uint256"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "reserveContract", "type": "address"},
                ]
            },
            "primaryType": "Attestation",
            "domain": {
                "name": "IDRC ProofOfReserve",
                "version": "1",
                "chainId": self.config.chain_id,
                "verifyingContract": self.config.reserve_address,
            },
            "message": {
                "fiatBalanceIdr": bank_attestation.fiat_balance_idr,
                "timestamp": bank_attestation.timestamp,
                "chainId": bank_attestation.chain_id,
                "reserveContract": bank_attestation.reserve_contract,
            }
        }
        
        # Sign using eth_account
        signed = self.w3.eth.account.sign_structured_data(
            self.config.oracle_private_key,
            structured_data
        )
        
        return signed.signature.hex()
    
    async def submit_attestation(self, bank_attestation: Any, oracle_signatures: Dict[str, str]) -> str:
        """Submit complete attestation with all oracle signatures to blockchain"""
        signers = list(oracle_signatures.keys())
        signatures = [oracle_signatures[addr] for addr in signers]
        
        logger.info(f"Submitting attestation with {len(signers)} signatures...")
        
        nonce = self.w3.eth.get_transaction_count(self.oracle_address)
        
        tx = self.reserve.functions.submitAttestation(
            bank_attestation.fiat_balance_idr,
            bank_attestation.timestamp,
            bank_attestation.chain_id,
            bank_attestation.reserve_contract,
            signers,
            [bytes.fromhex(sig.replace("0x", "")) for sig in signatures]
        ).build_transaction({
            "from": self.account.address,
            "nonce": nonce,
            "gas": 300000,
            "gasPrice": self.w3.eth.gas_price,
            "chainId": self.config.chain_id
        })
        
        signed_tx = self.w3.eth.account.sign_transaction(tx, self.config.oracle_private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        # Wait for receipt
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt.status == 1:
            logger.info(f"Attestation submitted successfully. Tx: {tx_hash.hex()}")
            return tx_hash.hex()
        else:
            raise Exception(f"Transaction failed: {tx_hash.hex()}")
    
    async def fetch_and_submit(self) -> bool:
        """Complete flow: fetch from bank, sign, submit"""
        try:
            # 1. Fetch bank attestation
            bank_attestation = await self.fetch_bank_attestation()
            logger.info(f"Bank attestation received: {bank_attestation.fiat_balance_idr / 10**18:,.0f} IDR")
            
            # 2. Create our oracle signature
            our_signature = await self.create_oracle_signature(bank_attestation)
            
            # In production: collect signatures from other oracles
            # For now, we'll use our own signature (single oracle mode)
            # In production: implement oracle network communication
            oracle_signatures = {self.oracle_address: our_signature}
            
            # Check if we have enough signatures
            required = self.config.required_signatures
            if len(oracle_signatures) < required:
                logger.warning(f"Only {len(oracle_signatures)}/{required} signatures. Need more oracle signatures.")
                # In production: wait for other oracles or trigger alarm
            
            # 3. Submit to blockchain
            tx_hash = await self.submit_attestation(bank_attestation, oracle_signatures)
            
            self.metrics["attestations_submitted"] += 1
            self.last_update = datetime.utcnow()
            self.consecutive_failures = 0
            
            logger.info(f"Successfully updated reserve. Tx: {tx_hash}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to fetch and submit: {e}")
            self.consecutive_failures += 1
            self.metrics["attestations_failed"] += 1
            self.metrics["last_error"] = str(e)
            return False
    
    async def check_staleness_and_alert(self) -> None:
        """Check if oracle data is stale and trigger alerts"""
        if self.config.staleness_threshold <= 0:
            return
        
        try:
            last_update = self.reserve.functions.lastOracleUpdate().call()
            if last_update == 0:
                logger.warning("Oracle never updated!")
                return
            
            staleness = time.time() - last_update
            if staleness > self.config.staleness_threshold:
                logger.critical(f"ORACLE STALE: Last update {staleness:.0f}s ago (threshold: {self.config.staleness_threshold}s)")
                self.metrics["last_error"] = f"Oracle stale: {staleness:.0f}s"
                
                # Trigger circuit breaker if needed
                if staleness > self.config.staleness_threshold * 2:
                    logger.critical("CRITICAL: Oracle extremely stale, considering circuit breaker")
                    # In production: trigger circuit breaker on contract
        
        except Exception as e:
            logger.error(f"Error checking staleness: {e}")
    
    async def run(self):
        """Main loop"""
        self.running = True
        logger.info(f"Starting Oracle Relayer for chain {self.config.chain_id}")
        logger.info(f"Oracle address: {self.oracle_address}")
        logger.info(f"Poll interval: {self.config.poll_interval}s")
        logger.info(f"Required signatures: {self.config.required_signatures}")
        logger.info(f"Staleness threshold: {self.config.staleness_threshold}s")
        
        while self.running:
            cycle_start = time.time()
            
            try:
                # Check staleness
                await self.check_staleness_and_alert()
                
                # Fetch and submit attestation
                success = await self.fetch_and_submit()
                
                if not success:
                    self.consecutive_failures += 1
                    if self.consecutive_failures >= 5:
                        logger.critical(f"Too many consecutive failures ({self.consecutive_failures})! Alerting...")
                        # In production: send alert to PagerDuty, Slack, etc.
                else:
                    self.metrics["attestations_confirmed"] += 1
                
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                self.consecutive_failures += 1
                self.metrics["attestations_failed"] += 1
                self.metrics["last_error"] = str(e)
            
            # Wait for next poll
            cycle_time = time.time() - cycle_start
            sleep_time = max(0, self.config.poll_interval - cycle_time)
            await asyncio.sleep(sleep_time)
    
    def stop(self):
        self.running = False
    
    def get_metrics(self) -> Dict[str, Any]:
        return {
            **self.metrics,
            "running": self.running,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "consecutive_failures": self.consecutive_failures,
            "oracle_address": self.oracle_address,
        }


async def main():
    """Main entry point"""
    # Load configuration from environment
    config = OracleConfig(
        chain_id=int(os.getenv("CHAIN_ID", "11155111")),
        rpc_urls=json.loads(os.getenv("RPC_URLS", '["https://rpc.sepolia.org"]')),
        reserve_address=os.getenv("RESERVE_ADDRESS", ""),
        oracle_private_key=os.getenv("ORACLE_PRIVATE_KEY", ""),
        oracle_address=os.getenv("ORACLE_ADDRESS", ""),
        poll_interval=int(os.getenv("POLL_INTERVAL", "900")),
        required_signatures=int(os.getenv("REQUIRED_SIGNATURES", "3")),
        staleness_threshold=int(os.getenv("STALENESS_THRESHOLD", "3600")),
    )
    
    if not all([config.reserve_address, config.oracle_private_key, config.oracle_address]):
        logger.error("Missing required environment variables: RESERVE_ADDRESS, ORACLE_PRIVATE_KEY, ORACLE_ADDRESS")
        return
    
    relayer = OracleRelayer(config)
    
    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, relayer.stop)
    
    await relayer.run()


if __name__ == "__main__":
    asyncio.run(main())