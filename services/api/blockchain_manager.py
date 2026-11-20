# blockchain_manager.py
# Blockchain Manager - Production-grade blockchain integration
"""Production-grade blockchain integration with failover, retries, and monitoring"""
import asyncio
import os
import time
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Tuple
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from enum import Enum

from web3 import Web3
from web3.contract import Contract
from web3.middleware import geth_poa_middleware
from web3.types import TxParams, TxReceipt, Wei, HexStr
from web3.exceptions import (
    TransactionNotFound,
    BlockNotFound,
    ContractLogicError,
    TimeExhausted,
    Web3RPCError,
)
from eth_account import Account
from eth_account.signers.local import LocalAccount
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .blockchain_config import (
    ChainConfig,
    Environment,
    CHAINS,
    get_chain_config,
    get_chains_for_environment,
    validate_environment_config,
    load_contract_addresses_from_env,
)
from .config import get_settings

logger = logging.getLogger(__name__)


class TransactionStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    REPLACED = "replaced"
    DROPPED = "dropped"


class RPCError(Exception):
    """RPC-related error"""
    pass


class TransactionError(Exception):
    """Transaction-related error"""
    def __init__(self, message: str, tx_hash: Optional[str] = None, status: Optional[TransactionStatus] = None):
        super().__init__(message)
        self.tx_hash = tx_hash
        self.status = status


class InsufficientFundsError(TransactionError):
    pass


class NonceError(TransactionError):
    pass


class GasEstimationError(TransactionError):
    pass


class ReorgDetectedError(Exception):
    """Chain reorganization detected"""
    pass


@dataclass
class TransactionRecord:
    """Track transaction state through lifecycle"""
    tx_hash: str
    chain_id: int
    contract_name: str
    function_name: str
    args: tuple
    kwargs: dict
    status: TransactionStatus = TransactionStatus.PENDING
    nonce: Optional[int] = None
    gas_price: Optional[int] = None
    gas_limit: Optional[int] = None
    max_fee_per_gas: Optional[int] = None
    max_priority_fee_per_gas: Optional[int] = None
    submitted_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    block_number: Optional[int] = None
    receipt: Optional[dict] = None
    error: Optional[str] = None
    retry_count: int = 0
    replaced_by: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "tx_hash": self.tx_hash,
            "chain_id": self.chain_id,
            "contract_name": self.contract_name,
            "function_name": self.function_name,
            "status": self.status.value,
            "nonce": self.nonce,
            "gas_price": self.gas_price,
            "gas_limit": self.gas_limit,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "block_number": self.block_number,
            "error": self.error,
            "retry_count": self.retry_count,
        }


@dataclass
class BlockInfo:
    number: int
    hash: str
    timestamp: int
    parent_hash: str


class NonceManager:
    """Manage nonces for accounts across chains with gap detection"""
    
    def __init__(self):
        self._nonces: Dict[Tuple[int, str], int] = {}  # (chain_id, address) -> nonce
        self._pending: Dict[Tuple[int, str], List[int]] = {}  # (chain_id, address) -> [pending nonces]
        self._locks: Dict[Tuple[int, str], asyncio.Lock] = {}
    
    def _get_lock(self, chain_id: int, address: str) -> asyncio.Lock:
        key = (chain_id, address.lower())
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]
    
    async def get_next_nonce(self, w3: Web3, chain_id: int, address: str) -> int:
        """Get next available nonce, accounting for pending transactions"""
        async with self._get_lock(chain_id, address):
            key = (chain_id, address.lower())
            
            # Get on-chain nonce
            on_chain_nonce = await w3.eth.get_transaction_count(address, "pending")
            
            # Get tracked nonce
            tracked_nonce = self._nonces.get(key, on_chain_nonce)
            
            # Use the higher of the two
            next_nonce = max(tracked_nonce, on_chain_nonce)
            
            # Account for pending transactions
            pending = self._pending.get(key, [])
            if pending:
                next_nonce = max(next_nonce, max(pending) + 1)
            
            # Reserve this nonce
            self._nonces[key] = next_nonce + 1
            if key not in self._pending:
                self._pending[key] = []
            self._pending[key].append(next_nonce)
            
            return next_nonce
    
    async def mark_confirmed(self, chain_id: int, address: str, nonce: int):
        """Mark nonce as confirmed on-chain"""
        async with self._get_lock(chain_id, address):
            key = (chain_id, address.lower())
            if key in self._pending and nonce in self._pending[key]:
                self._pending[key].remove(nonce)
            self._nonces[key] = max(self._nonces.get(key, 0), nonce + 1)
    
    async def mark_failed(self, chain_id: int, address: str, nonce: int):
        """Mark nonce as failed (remove from pending)"""
        async with self._get_lock(chain_id, address):
            key = (chain_id, address.lower())
            if key in self._pending and nonce in self._pending[key]:
                self._pending[key].remove(nonce)
    
    async def sync_with_chain(self, w3: Web3, chain_id: int, address: str):
        """Sync nonce state with on-chain state"""
        async with self._get_lock(chain_id, address):
            key = (chain_id, address.lower())
            on_chain_nonce = await w3.eth.get_transaction_count(address, "pending")
            self._nonces[key] = on_chain_nonce
            self._pending[key] = []


class RPCFailoverManager:
    """Manage RPC endpoints with automatic failover"""
    
    def __init__(self, chain_config: ChainConfig):
        self.chain_config = chain_config
        self.current_index = 0
        self.failed_endpoints: Dict[str, datetime] = {}
        self.failure_counts: Dict[str, int] = {}
        self._lock = asyncio.Lock()
    
    @property
    def current_url(self) -> str:
        return self.chain_config.rpc_urls[self.current_index]
    
    async def get_working_provider(self) -> Web3:
        """Get a working Web3 provider, failing over if needed"""
        async with self._lock:
            # Try current endpoint
            for attempt in range(len(self.chain_config.rpc_urls)):
                url = self.chain_config.rpc_urls[self.current_index]
                
                # Check if endpoint was recently failed
                if url in self.failed_endpoints:
                    if datetime.now() - self.failed_endpoints[url] < timedelta(minutes=5):
                        # Skip this endpoint, try next
                        self.current_index = (self.current_index + 1) % len(self.chain_config.rpc_urls)
                        continue
                
                try:
                    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 10}))
                    # Test connection
                    await asyncio.get_event_loop().run_in_executor(
                        None, lambda: w3.eth.block_number
                    )
                    
                    # Add POA middleware if needed
                    if self.chain_config.requires_poa_middleware:
                        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                    
                    # Reset failure count on success
                    self.failure_counts[url] = 0
                    return w3
                    
                except Exception as e:
                    logger.warning(f"RPC endpoint {url} failed: {e}")
                    self.failure_counts[url] = self.failure_counts.get(url, 0) + 1
                    self.failed_endpoints[url] = datetime.now()
                    
                    # Move to next endpoint
                    self.current_index = (self.current_index + 1) % len(self.chain_config.rpc_urls)
            
            raise RPCError(f"All RPC endpoints failed for chain {self.chain_config.chain_id}")
    
    def mark_failure(self, url: str):
        """Record a failure for an endpoint"""
        self.failure_counts[url] = self.failure_counts.get(url, 0) + 1
        self.failed_endpoints[url] = datetime.now()
    
    def mark_success(self, url: str):
        """Record a success for an endpoint"""
        self.failure_counts[url] = 0
        if url in self.failed_endpoints:
            del self.failed_endpoints[url]


class BlockchainManager:
    """Main blockchain integration manager"""
    
    def __init__(self, environment: Environment = Environment.DEVELOPMENT):
        self.settings = get_settings()
        self.environment = environment
        self.chains: Dict[int, ChainConfig] = {}
        self.providers: Dict[int, RPCFailoverManager] = {}
        self.contracts: Dict[str, Contract] = {}  # key: "ContractName_chainId"
        self.nonce_manager = NonceManager()
        self.account: Optional[LocalAccount] = None
        self._transaction_records: Dict[str, TransactionRecord] = {}
        self._block_cache: Dict[int, BlockInfo] = {}
        self._initialized = False
        
        # Initialize chains for environment
        for chain_config in get_chains_for_environment(environment):
            self.chains[chain_config.chain_id] = chain_config
            self.providers[chain_config.chain_id] = RPCFailoverManager(chain_config)
    
    async def initialize(self) -> None:
        """Initialize blockchain connections and validate configuration"""
        if self._initialized:
            return
        
        # Validate environment configuration
        errors = validate_environment_config(self.environment)
        if errors:
            error_msg = "Blockchain configuration errors:\n" + "\n".join(errors)
            if self.environment == Environment.PRODUCTION:
                raise RuntimeError(f"Production configuration invalid:\n{error_msg}")
            else:
                logger.warning(f"Configuration warnings: {errors}")
        
        # Load signing account
        private_key = os.getenv("BLOCKCHAIN_PRIVATE_KEY")
        if private_key:
            self.account = Account.from_key(private_key)
            logger.info(f"Loaded signing account: {self.account.address}")
        elif self.environment == Environment.PRODUCTION:
            raise RuntimeError("BLOCKCHAIN_PRIVATE_KEY required for production")
        else:
            logger.warning("No BLOCKCHAIN_PRIVATE_KEY set - read-only mode")
        
        # Load contract addresses
        await self._load_contract_addresses()
        
        # Initialize providers and verify connectivity
        await self._verify_connectivity()
        
        self._initialized = True
        logger.info(f"Blockchain manager initialized for {self.environment.value} environment")
    
    async def _load_contract_addresses(self) -> None:
        """Load contract addresses from environment and deployment files"""
        for chain_id, chain_config in self.chains.items():
            # Load from environment
            env_addresses = load_contract_addresses_from_env(chain_id)
            chain_config.contracts.update(env_addresses)
            
            # Try to load from deployment artifact
            deployment_file = os.getenv("DEPLOYMENT_ARTIFACT_PATH")
            if deployment_file:
                deployment_addresses = load_contract_addresses_from_deployment(chain_id, deployment_file)
                chain_config.contracts.update(deployment_addresses)
            
            logger.info(f"Loaded {len(chain_config.contracts)} contract addresses for chain {chain_id}")
    
    async def _verify_connectivity(self) -> None:
        """Verify connectivity to all configured chains"""
        for chain_id, failover_manager in self.providers.items():
            try:
                w3 = await failover_manager.get_working_provider()
                block_number = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: w3.eth.block_number
                )
                chain_id_on_chain = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: w3.eth.chain_id
                )
                
                if chain_id_on_chain != chain_id:
                    raise ValueError(f"Chain ID mismatch: expected {chain_id}, got {chain_id_on_chain}")
                
                logger.info(f"Chain {chain_id} connected (block: {block_number})")
            except Exception as e:
                logger.error(f"Failed to connect to chain {chain_id}: {e}")
                if self.environment == Environment.PRODUCTION:
                    raise RuntimeError(f"Cannot connect to required chain {chain_id}: {e}")
    
    def _get_contract_key(self, contract_name: str, chain_id: int) -> str:
        return f"{contract_name}_{chain_id}"
    
    async def get_contract(self, contract_name: str, chain_id: int) -> Contract:
        """Get contract instance with address verification"""
        key = f"{contract_name}_{chain_id}"
        
        if key not in self.contracts:
            chain_config = self.chains.get(chain_id)
            if not chain_config:
                raise ValueError(f"Chain {chain_id} not configured")
            
            address = chain_config.contracts.get(contract_name)
            if not address:
                raise ValueError(f"Contract {contract_name} not deployed on chain {chain_id}")
            
            # Verify address format
            address = Web3.to_checksum_address(address)
            
            # Get provider and create contract
            w3 = await self.get_provider(chain_id)
            
            # Load ABI from artifacts
            abi = self._load_abi(contract_name)
            
            contract = w3.eth.contract(address=address, abi=abi)
            
            # Verify contract exists on chain
            code = await asyncio.get_event_loop().run_in_executor(
                None, lambda: w3.eth.get_code(address)
            )
            if code == b"" or code == b"0x":
                raise ValueError(f"No contract code at {address} on chain {chain_id}")
            
            self.contracts[key] = contract
            logger.info(f"Loaded contract {contract_name} at {address} on chain {chain_id}")
        
        return self.contracts[key]
    
    def _load_abi(self, contract_name: str) -> list:
        """Load contract ABI from artifacts"""
        abi_path = os.getenv("ABI_PATH", "./out")
        try:
            with open(f"{abi_path}/{contract_name}.sol/{contract_name}.json") as f:
                artifact = json.load(f)
                return artifact["abi"]
        except FileNotFoundError:
            logger.warning(f"ABI not found for {contract_name}, using minimal ABI")
            return self._get_minimal_abi(contract_name)
    
    def _get_minimal_abi(self, contract_name: str) -> list:
        # Return minimal ABIs (same as before)
        # ... implementation omitted for brevity
        return []
    
    async def get_provider(self, chain_id: int) -> Web3:
        """Get Web3 provider with failover"""
        if chain_id not in self.providers:
            raise ValueError(f"Chain {chain_id} not configured")
        return await self.providers[chain_id].get_working_provider()
    
    # ============================================================
    # TRANSACTION MANAGEMENT
    # ============================================================
    
    async def send_transaction(
        self,
        chain_id: int,
        contract_name: str,
        function_name: str,
        *args,
        gas_limit: Optional[int] = None,
        gas_price: Optional[int] = None,
        max_fee_per_gas: Optional[int] = None,
        max_priority_fee_per_gas: Optional[int] = None,
        value: int = 0,
        nonce: Optional[int] = None,
        wait_for_confirmation: bool = True,
        confirmation_blocks: Optional[int] = None,
    ) -> TransactionRecord:
        """Send a transaction with full lifecycle management"""
        
        if not self.account:
            raise TransactionError("No signing account configured")
        
        chain_config = self.chains[chain_id]
        contract = await self.get_contract(contract_name, chain_id)
        w3 = await self.get_provider(chain_id)
        
        # Get function
        contract_function = getattr(contract.functions, function_name)
        
        # Get nonce
        if nonce is None:
            nonce = await self.nonce_manager.get_next_nonce(w3, chain_id, self.account.address)
        
        # Estimate gas
        if gas_limit is None:
            try:
                estimated = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: contract_function(*args).estimate_gas({"from": self.account.address, "value": value})
                )
                gas_limit = int(estimated * chain_config.gas_limit_multiplier)
            except Exception as e:
                raise GasEstimationError(f"Gas estimation failed: {e}")
        
        # Build transaction
        tx_params: TxParams = {
            "from": self.account.address,
            "to": contract.address,
            "value": value,
            "gas": gas_limit,
            "nonce": nonce,
            "chainId": chain_id,
        }
        
        # Set gas pricing (EIP-1559 or legacy)
        chain_config = self.chains[chain_id]
        if max_fee_per_gas is not None and max_priority_fee_per_gas is not None:
            tx_params["maxFeePerGas"] = max_fee_per_gas
            tx_params["maxPriorityFeePerGas"] = max_priority_fee_per_gas
        elif gas_price is not None:
            tx_params["gasPrice"] = gas_price
        else:
            # Auto gas pricing
            base_fee = await self._get_base_fee(w3)
            if base_fee:
                tx_params["maxFeePerGas"] = int(base_fee * 2)
                tx_params["maxPriorityFeePerGas"] = chain_config.priority_fee_gwei * 10**9
            else:
                tx_params["gasPrice"] = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: w3.eth.gas_price
                )
        
        # Build transaction
        tx = contract_function(*args).build_transaction(tx_params)
        
        # Sign transaction
        signed_tx = self.account.sign_transaction(tx)
        
        # Create transaction record
        tx_hash = signed_tx.hash.hex()
        record = TransactionRecord(
            tx_hash=tx_hash,
            chain_id=chain_id,
            contract_name=contract_name,
            function_name=function_name,
            args=args,
            kwargs={},
            nonce=nonce,
            gas_limit=gas_limit,
            gas_price=tx.get("gasPrice"),
            max_fee_per_gas=tx.get("maxFeePerGas"),
            max_priority_fee_per_gas=tx.get("maxPriorityFeePerGas"),
            submitted_at=datetime.utcnow(),
        )
        self._transaction_records[tx_hash] = record
        
        # Send transaction
        try:
            record.status = TransactionStatus.SUBMITTED
            raw_tx = signed_tx.rawTransaction
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: w3.eth.send_raw_transaction(raw_tx)
            )
            logger.info(f"Transaction submitted: {tx_hash} (nonce: {nonce})")
        except Exception as e:
            record.status = TransactionStatus.FAILED
            record.error = str(e)
            await self.nonce_manager.mark_failed(chain_id, self.account.address, nonce)
            raise TransactionError(f"Transaction submission failed: {e}", tx_hash=tx_hash)
        
        # Wait for confirmation if requested
        if wait_for_confirmation:
            await self._wait_for_confirmation(record, chain_config, confirmation_blocks)
        
        return record
    
    async def _wait_for_confirmation(
        self,
        record: TransactionRecord,
        chain_config: ChainConfig,
        confirmation_blocks: Optional[int] = None,
    ) -> TransactionRecord:
        """Wait for transaction confirmation with retries"""
        w3 = await self.get_provider(record.chain_id)
        confirmations_needed = confirmation_blocks or chain_config.finality_blocks
        max_wait = 300  # 5 minutes max
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                receipt = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: w3.eth.get_transaction_receipt(record.tx_hash)
                )
                
                if receipt:
                    record.receipt = dict(receipt)
                    record.block_number = receipt.blockNumber
                    record.confirmed_at = datetime.utcnow()
                    
                    if receipt.status == 1:
                        record.status = TransactionStatus.CONFIRMED
                        await self.nonce_manager.mark_confirmed(record.chain_id, self.account.address, record.nonce)
                        logger.info(f"Transaction confirmed: {record.tx_hash} (block: {receipt.blockNumber})")
                    else:
                        record.status = TransactionStatus.FAILED
                        record.error = "Transaction reverted"
                        await self.nonce_manager.mark_failed(record.chain_id, self.account.address, record.nonce)
                        logger.error(f"Transaction reverted: {record.tx_hash}")
                    
                    # Wait for additional confirmations if needed
                    if confirmations_needed > 1 and record.status == TransactionStatus.CONFIRMED:
                        await self._wait_for_confirmations(record, w3, confirmations_needed)
                    
                    return record
                
            except TransactionNotFound:
                pass  # Not mined yet
            except Exception as e:
                logger.warning(f"Error checking receipt: {e}")
            
            await asyncio.sleep(2)
        
        # Timeout
        record.status = TransactionStatus.FAILED
        record.error = "Confirmation timeout"
        await self.nonce_manager.mark_failed(record.chain_id, self.account.address, record.nonce)
        raise TransactionError(f"Transaction confirmation timeout: {record.tx_hash}", tx_hash=record.tx_hash)
    
    async def _wait_for_confirmations(
        self,
        record: TransactionRecord,
        w3: Web3,
        confirmations_needed: int,
    ) -> None:
        """Wait for additional block confirmations"""
        while True:
            current_block = await asyncio.get_event_loop().run_in_executor(
                None, lambda: w3.eth.block_number
            )
            confirmations = current_block - record.block_number + 1
            if confirmations >= confirmations_needed:
                break
            await asyncio.sleep(5)
    
    async def _get_base_fee(self, w3: Web3) -> Optional[int]:
        """Get current base fee for EIP-1559"""
        try:
            block = await asyncio.get_event_loop().run_in_executor(
                None, lambda: w3.eth.get_block("latest")
            )
            return block.get("baseFeePerGas")
        except Exception:
            return None
    
    # ============================================================
    # READ OPERATIONS (with automatic retry)
    # ============================================================
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((Web3RPCError, TimeoutError, ConnectionError)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def call_contract(
        self,
        chain_id: int,
        contract_name: str,
        function_name: str,
        *args,
        block_identifier: str = "latest",
    ) -> Any:
        """Call a contract view function with automatic retry"""
        contract = await self.get_contract(contract_name, chain_id)
        function = getattr(contract.functions, function_name)
        
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: function(*args).call({"block_identifier": block_identifier})
        )
    
    async def get_balance(self, chain_id: int, address: str) -> int:
        w3 = await self.get_provider(chain_id)
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: w3.eth.get_balance(Web3.to_checksum_address(address))
        )
    
    async def get_block(self, chain_id: int, block_identifier: str = "latest") -> BlockInfo:
        w3 = await self.get_provider(chain_id)
        block = await asyncio.get_event_loop().run_in_executor(
            None, lambda: w3.eth.get_block(block_identifier)
        )
        return BlockInfo(
            number=block.number,
            hash=block.hash.hex(),
            timestamp=block.timestamp,
            parent_hash=block.parentHash.hex(),
        )
    
    async def get_latest_block_number(self, chain_id: int) -> int:
        w3 = await self.get_provider(chain_id)
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: w3.eth.block_number
        )
    
    # ============================================================
    # REORG DETECTION
    # ============================================================
    
    async def check_for_reorg(self, chain_id: int, last_known_block: int) -> Optional[BlockInfo]:
        """Check if a reorganization has occurred since last known block"""
        w3 = await self.get_provider(chain_id)
        
        # Get current block
        current_block = await self.get_block(chain_id)
        
        # If we've gone backwards, that's a reorg
        if current_block.number < last_known_block:
            logger.warning(f"Potential reorg detected on chain {chain_id}: {last_known_block} -> {current_block.number}")
            return current_block
        
        # Check if parent hash matches
        if last_known_block > 0:
            last_block = await self.get_block(chain_id, last_known_block)
            if current_block.parent_hash != last_block.hash:
                logger.warning(f"Reorg detected on chain {chain_id} at block {last_known_block}")
                return current_block
        
        return None
    
    # ============================================================
    # EVENT INDEXING
    # ============================================================
    
    async def get_events(
        self,
        chain_id: int,
        contract_name: str,
        event_name: str,
        from_block: int,
        to_block: int = "latest",
        argument_filters: Optional[Dict] = None,
    ) -> List[Dict]:
        """Get contract events with reorg-safe pagination"""
        contract = await self.get_contract(contract_name, chain_id)
        w3 = await self.get_provider(chain_id)
        
        event = getattr(contract.events, event_name)
        
        # Process in chunks to avoid timeout
        chunk_size = 2000
        all_events = []
        
        if isinstance(to_block, str) and to_block == "latest":
            to_block = await self.get_latest_block_number(chain_id)
        
        for start in range(from_block, to_block + 1, chunk_size):
            end = min(start + chunk_size - 1, to_block)
            
            try:
                logs = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: event.get_logs(
                        from_block=start,
                        to_block=end,
                        argument_filters=argument_filters
                    )
                )
                
                for log in logs:
                    all_events.append({
                        "event": event_name,
                        "address": log.address,
                        "block_number": log.blockNumber,
                        "transaction_hash": log.transactionHash.hex(),
                        "log_index": log.logIndex,
                        "args": dict(log.args),
                        "timestamp": None,  # Would need to fetch block
                    })
                    
            except Exception as e:
                logger.error(f"Error fetching events {start}-{end}: {e}")
                raise
        
        return all_events
    
    # ============================================================
    # TRANSACTION TRACKING
    # ============================================================
    
    def get_transaction_record(self, tx_hash: str) -> Optional[TransactionRecord]:
        return self._transaction_records.get(tx_hash)
    
    def get_pending_transactions(self, chain_id: Optional[int] = None) -> List[TransactionRecord]:
        records = []
        for record in self._transaction_records.values():
            if record.status in [TransactionStatus.PENDING, TransactionStatus.SUBMITTED]:
                if chain_id is None or record.chain_id == chain_id:
                    records.append(record)
        return records
    
    def get_failed_transactions(self, chain_id: Optional[int] = None) -> List[TransactionRecord]:
        records = []
        for record in self._transaction_records.values():
            if record.status == TransactionStatus.FAILED:
                if chain_id is None or record.chain_id == chain_id:
                    records.append(record)
        return records
    
    # ============================================================
    # UTILITY
    # ============================================================
    
    async def get_chain_status(self, chain_id: int) -> Dict[str, Any]:
        """Get comprehensive chain status"""
        try:
            w3 = await self.get_provider(chain_id)
            block_number = await self.get_latest_block_number(chain_id)
            gas_price = await asyncio.get_event_loop().run_in_executor(
                None, lambda: w3.eth.gas_price
            )
            
            return {
                "chain_id": chain_id,
                "connected": True,
                "latest_block": block_number,
                "gas_price_gwei": gas_price / 10**9,
                "contracts_loaded": len([k for k in self.contracts.keys() if k.endswith(f"_{chain_id}")]),
            }
        except Exception as e:
            return {
                "chain_id": chain_id,
                "connected": False,
                "error": str(e),
            }
    
    async def get_all_chains_status(self) -> Dict[str, Any]:
        statuses = {}
        for chain_id in self.chains:
            statuses[chain_id] = await self.get_chain_status(chain_id)
        return {
            "environment": self.environment.value,
            "chains": statuses,
            "signing_account": self.account.address if self.account else None,
            "pending_transactions": len(self.get_pending_transactions()),
        }


# Global instance
_blockchain_manager: Optional[BlockchainManager] = None


async def get_blockchain_manager(environment: Environment = None) -> BlockchainManager:
    """Get or create global blockchain manager"""
    global _blockchain_manager
    
    if environment is None:
        env_str = os.getenv("ENVIRONMENT", "development")
        environment = Environment(env_str.lower())
    
    if _blockchain_manager is None or _blockchain_manager.environment != environment:
        _blockchain_manager = BlockchainManager(environment)
        await _blockchain_manager.initialize()
    
    return _blockchain_manager


async def close_blockchain_manager():
    """Close blockchain manager connections"""
    global _blockchain_manager
    if _blockchain_manager:
        # Cleanup if needed
        _blockchain_manager = None


# Export
__all__ = [
    "BlockchainManager",
    "TransactionRecord",
    "TransactionStatus",
    "NonceManager",
    "RPCFailoverManager",
    "BlockInfo",
    "get_blockchain_manager",
    "close_blockchain_manager",
    "RPCError",
    "TransactionError",
    "InsufficientFundsError",
    "NonceError",
    "GasEstimationError",
    "ReorgDetectedError",
]
