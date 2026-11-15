"""
Blockchain Indexer Service
Indexes events from all IDRC contracts for analytics and monitoring
"""
import os
import asyncio
import logging
import signal
import json
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

from web3 import Web3
from web3.contract import Contract
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, Numeric, Text, Index, select
from sqlalchemy.orm import DeclarativeBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("indexer")


# Database Models
class Base(DeclarativeBase):
    pass


class TokenEvent(Base):
    __tablename__ = "token_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)
    tx_hash = Column(String(66), nullable=False, index=True)
    block_number = Column(BigInteger, nullable=False, index=True)
    log_index = Column(Integer, nullable=False)
    chain_id = Column(Integer, nullable=False, index=True)
    from_address = Column(String(42), nullable=True, index=True)
    to_address = Column(String(42), nullable=True, index=True)
    amount = Column(Numeric(precision=78, scale=0), nullable=True)
    caller = Column(String(42), nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_token_event_chain_block", "chain_id", "block_number"),
    )


class MultisigEvent(Base):
    __tablename__ = "multisig_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)
    tx_hash = Column(String(66), nullable=False, index=True)
    block_number = Column(BigInteger, nullable=False, index=True)
    chain_id = Column(Integer, nullable=False, index=True)
    multisig_address = Column(String(42), nullable=False, index=True)
    transaction_id = Column(BigInteger, nullable=False, index=True)
    proposer = Column(String(42), nullable=True, index=True)
    confirmer = Column(String(42), nullable=True, index=True)
    executor = Column(String(42), nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReserveEvent(Base):
    __tablename__ = "reserve_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)
    tx_hash = Column(String(66), nullable=False, index=True)
    block_number = Column(BigInteger, nullable=False, index=True)
    chain_id = Column(Integer, nullable=False, index=True)
    reserve_address = Column(String(42), nullable=False, index=True)
    fiat_balance = Column(Numeric(precision=78, scale=0), nullable=True)
    proof_hash = Column(String(66), nullable=True)
    submitted_by = Column(String(42), nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BridgeEvent(Base):
    __tablename__ = "bridge_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)
    tx_hash = Column(String(66), nullable=False, index=True)
    block_number = Column(BigInteger, nullable=False, index=True)
    chain_id = Column(Integer, nullable=False, index=True)
    vault_address = Column(String(42), nullable=True, index=True)
    relayer_address = Column(String(42), nullable=True, index=True)
    bridge_nonce = Column(BigInteger, nullable=False, index=True)
    src_chain = Column(Integer, nullable=True, index=True)
    dst_chain = Column(Integer, nullable=True, index=True)
    sender = Column(String(42), nullable=True, index=True)
    recipient = Column(String(42), nullable=True, index=True)
    amount = Column(Numeric(precision=78, scale=0), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_bridge_event_nonce_chain", "bridge_nonce", "src_chain"),
    )


@dataclass
class ChainConfig:
    chain_id: int
    name: str
    rpc_url: str
    contracts: Dict[str, str]  # contract_name -> address
    start_block: int = 0
    poll_interval: int = 10
    batch_size: int = 1000


class Indexer:
    def __init__(self, configs: Dict[int, ChainConfig], database_url: str):
        self.configs = configs
        self.database_url = database_url
        self.engine = None
        self.session_factory = None
        self.providers: Dict[int, Web3] = {}
        self.contracts: Dict[int, Dict[str, Contract]] = {}
        self.current_blocks: Dict[int, int] = {}
        self.running = False

        # Event signatures
        self.event_signatures = {
            "Transfer": Web3.keccak(text="Transfer(address,address,uint256)").hex(),
            "Approval": Web3.keccak(text="Approval(address,address,uint256)").hex(),
            "Minted": Web3.keccak(text="Minted(address,uint256)").hex(),
            "Burned": Web3.keccak(text="Burned(address,uint256)").hex(),
            "Blacklisted": Web3.keccak(text="Blacklisted(address)").hex(),
            "Unblacklisted": Web3.keccak(text="Unblacklisted(address)").hex(),
            "Paused": Web3.keccak(text="Paused(address)").hex(),
            "Unpaused": Web3.keccak(text="Unpaused(address)").hex(),
            "RoleGranted": Web3.keccak(text="RoleGranted(bytes32,address,address)").hex(),
            "RoleRevoked": Web3.keccak(text="RoleRevoked(bytes32,address,address)").hex(),
            "Submission": Web3.keccak(text="Submission(address,uint256)").hex(),
            "Confirmation": Web3.keccak(text="Confirmation(address,uint256)").hex(),
            "Revocation": Web3.keccak(text="Revocation(address,uint256)").hex(),
            "Execution": Web3.keccak(text="Execution(address,uint256)").hex(),
            "ExecutionFailure": Web3.keccak(text="ExecutionFailure(address,uint256)").hex(),
            "AuditProofSubmitted": Web3.keccak(text="AuditProofSubmitted(uint256,bytes32,uint256,address)").hex(),
            "FiatBalanceUpdated": Web3.keccak(text="FiatBalanceUpdated(uint256,address)").hex(),
            "TokensLocked": Web3.keccak(text="TokensLocked(uint256,address,address,uint256,uint256)").hex(),
            "TokensReleased": Web3.keccak(text="TokensReleased(uint256,address,uint256)").hex(),
            "MessageRelayed": Web3.keccak(text="MessageRelayed(uint256,uint256,uint256,address,uint256)").hex(),
        }

    async def initialize(self):
        """Initialize database and blockchain connections"""
        # Database
        self.engine = create_async_engine(
            self.database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

        # Create tables
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Blockchain providers
        for chain_id, config in self.configs.items():
            w3 = Web3(Web3.HTTPProvider(config.rpc_url))

            # POA middleware for non-Ethereum chains
            if chain_id in [56, 97, 137, 80002, 42161, 421614, 10, 11155420, 8453, 84532]:
                from web3.middleware import geth_poa_middleware
                w3.middleware_onion.inject(geth_poa_middleware, layer=0)

            self.providers[chain_id] = w3

            # Load contract ABIs and create instances
            self.contracts[chain_id] = {}
            for contract_name, address in config.contracts.items():
                abi = self._load_abi(contract_name)
                self.contracts[chain_id][contract_name] = w3.eth.contract(
                    address=Web3.to_checksum_address(address),
                    abi=abi
                )

            # Get starting block
            latest = w3.eth.get_block("latest").number
            self.current_blocks[chain_id] = max(config.start_block, latest - 1000)

            logger.info(f"Initialized indexer for {config.name} ({chain_id}) at block {self.current_blocks[chain_id]}")

    def _load_abi(self, contract_name: str) -> list:
        """Load contract ABI from artifacts"""
        try:
            with open(f"./out/{contract_name}.sol/{contract_name}.json") as f:
                artifact = json.load(f)
                return artifact["abi"]
        except FileNotFoundError:
            logger.warning(f"ABI not found for {contract_name}, using minimal")
            return []

    async def index_chain(self, chain_id: int):
        """Index new blocks for a chain"""
        config = self.configs[chain_id]
        w3 = self.providers[chain_id]
        contracts = self.contracts[chain_id]

        try:
            latest_block = w3.eth.get_block("latest").number
            from_block = self.current_blocks[chain_id]
            to_block = min(from_block + config.batch_size, latest_block - 1)

            if from_block > to_block:
                return

            logger.debug(f"Indexing {config.name} blocks {from_block}-{to_block}")

            # Collect all contract addresses
            contract_addresses = list(contracts.values())

            # Get all logs for these contracts
            logs = w3.eth.get_logs({
                "fromBlock": from_block,
                "toBlock": to_block,
                "address": contract_addresses
            })

            # Process logs
            async with self.session_factory() as session:
                for log in logs:
                    await self._process_log(log, chain_id, session)

                await session.commit()

            self.current_blocks[chain_id] = to_block + 1

        except Exception as e:
            logger.error(f"Error indexing chain {config.name}: {e}")

    async def _process_log(self, log, chain_id: int, session: AsyncSession):
        """Process a single log entry"""
        topics = [t.hex() for t in log["topics"]]
        event_sig = topics[0] if topics else None
        address = log["address"].lower()

        # Determine contract and event type
        for contract_name, contract_addr in self.contracts[chain_id].items():
            if contract_addr.address.lower() == address:
                await self._handle_contract_event(contract_name, event_sig, log, chain_id, session)
                break

    async def _handle_contract_event(
        self, contract_name: str, event_sig: str, log, chain_id: int, session: AsyncSession
    ):
        """Handle event based on contract and signature"""
        data = log["data"]
        block_number = log["blockNumber"]
        tx_hash = log["transactionHash"].hex()
        log_index = log["logIndex"]
        timestamp = datetime.utcnow()  # In production, get from block

        # Token events
        if contract_name == "IDRCToken":
            await self._handle_token_event(event_sig, log, topics, data, block_number, tx_hash, log_index, chain_id, timestamp, session)

        # Multisig events
        elif contract_name == "MultisigWallet":
            await self._handle_multisig_event(event_sig, log, topics, data, block_number, tx_hash, log_index, chain_id, timestamp, session)

        # Reserve events
        elif contract_name == "ProofOfReserve":
            await self._handle_reserve_event(event_sig, log, topics, data, block_number, tx_hash, log_index, chain_id, timestamp, session)

        # Bridge events
        elif contract_name in ["BridgeVault", "BridgeRelayer"]:
            await self._handle_bridge_event(contract_name, event_sig, log, topics, data, block_number, tx_hash, log_index, chain_id, timestamp, session)

    async def _handle_token_event(self, event_sig, log, topics, data, block_number, tx_hash, log_index, chain_id, timestamp, session):
        """Handle IDRCToken events"""
        event_map = {
            self.event_signatures["Transfer"]: "Transfer",
            self.event_signatures["Approval"]: "Approval",
            self.event_signatures["Minted"]: "Mint",
            self.event_signatures["Burned"]: "Burn",
            self.event_signatures["Blacklisted"]: "Blacklist",
            self.event_signatures["Unblacklisted"]: "Unblacklist",
            self.event_signatures["Paused"]: "Pause",
            self.event_signatures["Unpaused"]: "Unpause",
            self.event_signatures["RoleGranted"]: "RoleGranted",
            self.event_signatures["RoleRevoked"]: "RoleRevoked",
        }

        event_type = event_map.get(event_sig)
        if not event_type:
            return

        # Decode based on event type
        from_addr = to_addr = amount = caller = None

        if event_type == "Transfer":
            from_addr = "0x" + topics[1][-40:]
            to_addr = "0x" + topics[2][-40:]
            amount = int(data, 16)
        elif event_type in ["Mint", "Burn"]:
            to_addr = "0x" + topics[1][-40:] if event_type == "Mint" else None
            from_addr = "0x" + topics[1][-40:] if event_type == "Burn" else None
            amount = int(data, 16)
        elif event_type in ["Blacklist", "Unblacklist"]:
            from_addr = "0x" + topics[1][-40:]

        event = TokenEvent(
            event_type=event_type,
            tx_hash=tx_hash,
            block_number=block_number,
            log_index=log_index,
            chain_id=chain_id,
            from_address=from_addr,
            to_address=to_addr,
            amount=amount,
            timestamp=timestamp
        )
        session.add(event)

    async def _handle_multisig_event(self, event_sig, log, topics, data, block_number, tx_hash, log_index, chain_id, timestamp, session):
        """Handle MultisigWallet events"""
        event_map = {
            self.event_signatures["Submission"]: "Submission",
            self.event_signatures["Confirmation"]: "Confirmation",
            self.event_signatures["Revocation"]: "Revocation",
            self.event_signatures["Execution"]: "Execution",
            self.event_signatures["ExecutionFailure"]: "ExecutionFailure",
        }

        event_type = event_map.get(event_sig)
        if not event_type:
            return

        multisig_addr = log["address"]
        tx_id = int(topics[1], 16) if len(topics) > 1 else 0
        actor = "0x" + topics[2][-40:] if len(topics) > 2 else None

        event = MultisigEvent(
            event_type=event_type,
            tx_hash=tx_hash,
            block_number=block_number,
            chain_id=chain_id,
            multisig_address=multisig_addr,
            transaction_id=tx_id,
            proposer=actor if event_type == "Submission" else None,
            confirmer=actor if event_type == "Confirmation" else None,
            executor=actor if event_type == "Execution" else None,
            timestamp=timestamp
        )
        session.add(event)

    async def _handle_reserve_event(self, event_sig, log, topics, data, block_number, tx_hash, log_index, chain_id, timestamp, session):
        """Handle ProofOfReserve events"""
        event_map = {
            self.event_signatures["AuditProofSubmitted"]: "AuditProofSubmitted",
            self.event_signatures["FiatBalanceUpdated"]: "FiatBalanceUpdated",
        }

        event_type = event_map.get(event_sig)
        if not event_type:
            return

        reserve_addr = log["address"]

        if event_type == "AuditProofSubmitted":
            seq = int(topics[1], 16)
            proof_hash = "0x" + topics[2][-64:]
            submitted_by = "0x" + topics[3][-40:]
            # Data: reportedFiatIdr
            fiat_balance = int(data, 16)

            event = ReserveEvent(
                event_type=event_type,
                tx_hash=tx_hash,
                block_number=block_number,
                chain_id=chain_id,
                reserve_address=reserve_addr,
                fiat_balance=fiat_balance,
                proof_hash=proof_hash,
                submitted_by=submitted_by,
                timestamp=timestamp
            )
        elif event_type == "FiatBalanceUpdated":
            fiat_balance = int(topics[1], 16)
            oracle = "0x" + topics[2][-40:]

            event = ReserveEvent(
                event_type=event_type,
                tx_hash=tx_hash,
                block_number=block_number,
                chain_id=chain_id,
                reserve_address=reserve_addr,
                fiat_balance=fiat_balance,
                submitted_by=oracle,
                timestamp=timestamp
            )

        session.add(event)

    async def _handle_bridge_event(self, contract_name, event_sig, log, topics, data, block_number, tx_hash, log_index, chain_id, timestamp, session):
        """Handle Bridge events"""
        event_map = {
            self.event_signatures["TokensLocked"]: "TokensLocked",
            self.event_signatures["TokensReleased"]: "TokensReleased",
            self.event_signatures["MessageRelayed"]: "MessageRelayed",
        }

        event_type = event_map.get(event_sig)
        if not event_type:
            return

        vault_addr = log["address"] if contract_name == "BridgeVault" else None
        relayer_addr = log["address"] if contract_name == "BridgeRelayer" else None

        if event_type == "TokensLocked":
            bridge_nonce = int(topics[1], 16)
            sender = "0x" + topics[2][-40:]
            recipient = "0x" + topics[3][-40:]
            amount = int(data[:66], 16)
            dst_chain = int(data[66:], 16)
            src_chain = chain_id

            event = BridgeEvent(
                event_type=event_type,
                tx_hash=tx_hash,
                block_number=block_number,
                chain_id=chain_id,
                vault_address=vault_addr,
                bridge_nonce=bridge_nonce,
                src_chain=src_chain,
                dst_chain=dst_chain,
                sender=sender,
                recipient=recipient,
                amount=amount,
                timestamp=timestamp
            )
        elif event_type == "TokensReleased":
            bridge_nonce = int(topics[1], 16)
            recipient = "0x" + topics[2][-40:]
            amount = int(data, 16)
            src_chain = chain_id

            event = BridgeEvent(
                event_type=event_type,
                tx_hash=tx_hash,
                block_number=block_number,
                chain_id=chain_id,
                vault_address=vault_addr,
                bridge_nonce=bridge_nonce,
                src_chain=src_chain,
                recipient=recipient,
                amount=amount,
                timestamp=timestamp
            )
        elif event_type == "MessageRelayed":
            bridge_nonce = int(topics[1], 16)
            src_chain = int(topics[2], 16)
            dst_chain = int(topics[3], 16)
            recipient = "0x" + topics[4][-40:]
            amount = int(data, 16)

            event = BridgeEvent(
                event_type=event_type,
                tx_hash=tx_hash,
                block_number=block_number,
                chain_id=chain_id,
                relayer_address=relayer_addr,
                bridge_nonce=bridge_nonce,
                src_chain=src_chain,
                dst_chain=dst_chain,
                recipient=recipient,
                amount=amount,
                timestamp=timestamp
            )

        session.add(event)

    async def run(self):
        """Main indexing loop"""
        self.running = True
        logger.info("Starting Indexer...")

        while self.running:
            try:
                tasks = [self.index_chain(chain_id) for chain_id in self.configs.keys()]
                await asyncio.gather(*tasks, return_exceptions=True)

                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Error in indexer main loop: {e}")
                await asyncio.sleep(10)

    def stop(self):
        self.running = False


async def main():
    # Load configurations
    configs = {
        11155111: ChainConfig(  # Sepolia
            chain_id=11155111,
            name="Ethereum Sepolia",
            rpc_url=os.getenv("SEPOLIA_RPC_URL", "https://rpc.sepolia.org"),
            contracts={
                "IDRCToken": os.getenv("SEPOLIA_TOKEN_ADDRESS", ""),
                "MultisigWallet": os.getenv("SEPOLIA_MULTISIG_ADDRESS", ""),
                "ProofOfReserve": os.getenv("SEPOLIA_RESERVE_ADDRESS", ""),
                "BridgeVault": os.getenv("SEPOLIA_VAULT_ADDRESS", ""),
                "BridgeRelayer": os.getenv("SEPOLIA_RELAYER_ADDRESS", ""),
            },
        ),
        80002: ChainConfig(  # Polygon Amoy
            chain_id=80002,
            name="Polygon Amoy",
            rpc_url=os.getenv("AMOY_RPC_URL", "https://rpc-amoy.polygon.technology"),
            contracts={
                "IDRCToken": os.getenv("AMOY_TOKEN_ADDRESS", ""),
                "MultisigWallet": os.getenv("AMOY_MULTISIG_ADDRESS", ""),
                "ProofOfReserve": os.getenv("AMOY_RESERVE_ADDRESS", ""),
                "BridgeVault": os.getenv("AMOY_VAULT_ADDRESS", ""),
                "BridgeRelayer": os.getenv("AMOY_RELAYER_ADDRESS", ""),
            },
        ),
    }

    # Filter empty addresses
    for config in configs.values():
        config.contracts = {k: v for k, v in config.contracts.items() if v}

    database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/idrc_indexer")

    indexer = Indexer(configs, database_url)
    await indexer.initialize()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, indexer.stop)

    await indexer.run()


if __name__ == "__main__":
    asyncio.run(main())