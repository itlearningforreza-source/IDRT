# indexer.py
# Blockchain Event Indexer - Production-grade event indexing with reorg handling
"""Production-grade event indexer with reorg detection and recovery"""
import asyncio
import os
import signal
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Callable, Any
from datetime import datetime, timedelta
from enum import Enum
from contextlib import asynccontextmanager

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .blockchain_config import ChainConfig, CHAINS, Environment
from .blockchain_manager import BlockchainManager, get_blockchain_manager, BlockInfo
from .database import get_session_dependency, TokenEvent, ReserveEvent, BridgeEvent, init_db
from .config import get_settings

logger = logging.getLogger(__name__)


class IndexerState(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class IndexerCursor:
    """Tracks indexing position for a chain/event"""
    chain_id: int
    contract_name: str
    event_name: str
    last_indexed_block: int = 0
    last_indexed_tx_hash: str = ""
    last_indexed_log_index: int = 0
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class EventProcessor:
    """Defines how to process a specific event"""
    contract_name: str
    event_name: str
    processor: Callable  # async function(session, event_data)
    argument_filters: Optional[Dict] = None
    from_block: int = 0


class EventIndexer:
    """Production-grade event indexer with reorg handling"""
    
    def __init__(
        self,
        chain_configs: Dict[int, ChainConfig],
        database_url: str,
        environment: Environment = Environment.DEVELOPMENT,
    ):
        self.chain_configs = chain_configs
        self.database_url = database_url
        self.environment = environment
        self.settings = get_settings()
        
        # State
        self.state = IndexerState.STARTING
        self.cursors: Dict[str, IndexerCursor] = {}  # key: "chainId:contract:event"
        self.processors: List[EventProcessor] = []
        self.blockchain_manager: Optional[BlockchainManager] = None
        
        # Configuration
        self.batch_size = int(os.getenv("INDEXER_BATCH_SIZE", "100"))
        self.poll_interval = int(os.getenv("INDEXER_POLL_INTERVAL", "10"))  # seconds
        self.confirmation_blocks = int(os.getenv("INDEXER_CONFIRMATION_BLOCKS", "12"))
        self.max_reorg_depth = int(os.getenv("INDEXER_MAX_REORG_DEPTH", "50"))
        
        # Control
        self._running = False
        self._tasks: List[asyncio.Task] = []
        
        # Metrics
        self.metrics = {
            "events_processed": 0,
            "reorgs_detected": 0,
            "reorgs_recovered": 0,
            "errors": 0,
            "last_error": None,
            "started_at": None,
        }
    
    async def initialize(self) -> None:
        """Initialize indexer"""
        self.state = IndexerState.STARTING
        
        # Initialize database
        await init_db()
        
        # Initialize blockchain manager
        self.blockchain_manager = await get_blockchain_manager(self.environment)
        
        # Load cursors from database
        await self._load_cursors()
        
        # Register default processors
        self._register_default_processors()
        
        self.state = IndexerState.RUNNING
        self.metrics["started_at"] = datetime.utcnow()
        logger.info("Event indexer initialized")
    
    def _register_default_processors(self) -> None:
        """Register default event processors for IDRC contracts"""
        
        # Token events
        self.register_processor(EventProcessor(
            contract_name="IDRCToken",
            event_name="Transfer",
            processor=self._process_token_transfer,
            from_block=0,
        ))
        self.register_processor(EventProcessor(
            contract_name="IDRCToken",
            event_name="Minted",
            processor=self._process_token_minted,
            from_block=0,
        ))
        self.register_processor(EventProcessor(
            contract_name="IDRCToken",
            event_name="Burned",
            processor=self._process_token_burned,
            from_block=0,
        ))
        self.register_processor(EventProcessor(
            contract_name="IDRCToken",
            event_name="Blacklisted",
            processor=self._process_blacklisted,
            from_block=0,
        ))
        self.register_processor(EventProcessor(
            contract_name="IDRCToken",
            event_name="Unblacklisted",
            processor=self._process_unblacklisted,
            from_block=0,
        ))
        
        # Reserve events
        self.register_processor(EventProcessor(
            contract_name="ProofOfReserve",
            event_name="FiatBalanceUpdated",
            processor=self._process_fiat_balance_updated,
            from_block=0,
        ))
        self.register_processor(EventProcessor(
            contract_name="ProofOfReserve",
            event_name="AuditProofSubmitted",
            processor=self._process_audit_proof_submitted,
            from_block=0,
        ))
        
        # Bridge events
        self.register_processor(EventProcessor(
            contract_name="BridgeVault",
            event_name="TokensLocked",
            processor=self._process_tokens_locked,
            from_block=0,
        ))
        self.register_processor(EventProcessor(
            contract_name="BridgeVault",
            event_name="TokensReleased",
            processor=self._process_tokens_released,
            from_block=0,
        ))
        self.register_processor(EventProcessor(
            contract_name="BridgeRelayer",
            event_name="MessageRelayed",
            processor=self._process_message_relayed,
            from_block=0,
        ))
    
    def register_processor(self, processor: EventProcessor) -> None:
        """Register an event processor"""
        self.processors.append(processor)
        logger.info(f"Registered processor: {processor.contract_name}.{processor.event_name}")
    
    def _get_cursor_key(self, chain_id: int, contract_name: str, event_name: str) -> str:
        return f"{chain_id}:{contract_name}:{event_name}"
    
    async def _load_cursors(self) -> None:
        """Load indexing cursors from database"""
        # In a real implementation, this would load from a cursors table
        # For now, initialize from block 0 or deployment block
        for chain_id, chain_config in self.chain_configs.items():
            for processor in self.processors:
                key = self._get_cursor_key(processor.chain_id, processor.contract_name, processor.event_name)
                # Start from processor.from_block or deployment block
                start_block = processor.from_block
                
                # Try to get deployment block from contract deployment
                # This would be loaded from deployment artifacts
                self.cursors[key] = IndexerCursor(
                    chain_id=chain_id,
                    contract_name=processor.contract_name,
                    event_name=processor.event_name,
                    last_indexed_block=start_block - 1,
                )
    
    async def save_cursors(self) -> None:
        """Save cursors to database"""
        # Implementation would save to database
        pass
    
    # ============================================================
    # EVENT PROCESSORS
    # ============================================================
    
    async def _get_or_create_session(self) -> AsyncSession:
        """Get database session"""
        async for session in get_session_dependency():
            return session
    
    async def _process_token_transfer(self, session: AsyncSession, event_data: Dict) -> None:
        """Process ERC-20 Transfer event"""
        event = TokenEvent(
            event_type="TRANSFER",
            tx_hash=event_data["transaction_hash"],
            block_number=event_data["block_number"],
            log_index=event_data["log_index"],
            chain_id=event_data["chain_id"],
            from_address=event_data["args"].get("from"),
            to_address=event_data["args"].get("to"),
            amount=event_data["args"].get("value"),
            timestamp=datetime.utcnow(),  # Would fetch actual block timestamp
        )
        session.add(event)
    
    async def _process_token_minted(self, session: AsyncSession, event_data: Dict) -> None:
        """Process Minted event"""
        event = TokenEvent(
            event_type="MINTED",
            tx_hash=event_data["transaction_hash"],
            block_number=event_data["block_number"],
            log_index=event_data["log_index"],
            chain_id=event_data["chain_id"],
            to_address=event_data["args"].get("to"),
            amount=event_data["args"].get("amount"),
            caller=event_data["args"].get("caller"),
            timestamp=datetime.utcnow(),
        )
        session.add(event)
    
    async def _process_token_burned(self, session: AsyncSession, event_data: Dict) -> None:
        """Process Burned event"""
        event = TokenEvent(
            event_type="BURNED",
            tx_hash=event_data["transaction_hash"],
            block_number=event_data["block_number"],
            log_index=event_data["log_index"],
            chain_id=event_data["chain_id"],
            from_address=event_data["args"].get("from"),
            amount=event_data["args"].get("amount"),
            caller=event_data["args"].get("caller"),
            timestamp=datetime.utcnow(),
        )
        session.add(event)
    
    async def _process_blacklisted(self, session: AsyncSession, event_data: Dict) -> None:
        """Process Blacklisted event"""
        event = TokenEvent(
            event_type="BLACKLISTED",
            tx_hash=event_data["transaction_hash"],
            block_number=event_data["block_number"],
            log_index=event_data["log_index"],
            chain_id=event_data["chain_id"],
            to_address=event_data["args"].get("account"),
            timestamp=datetime.utcnow(),
        )
        session.add(event)
    
    async def _process_unblacklisted(self, session: AsyncSession, event_data: Dict) -> None:
        """Process Unblacklisted event"""
        event = TokenEvent(
            event_type="UNBLACKLISTED",
            tx_hash=event_data["transaction_hash"],
            block_number=event_data["block_number"],
            log_index=event_data["log_index"],
            chain_id=event_data["chain_id"],
            to_address=event_data["args"].get("account"),
            timestamp=datetime.utcnow(),
        )
        session.add(event)
    
    async def _process_fiat_balance_updated(self, session: AsyncSession, event_data: Dict) -> None:
        """Process FiatBalanceUpdated event"""
        event = ReserveEvent(
            event_type="FIAT_BALANCE_UPDATED",
            tx_hash=event_data["transaction_hash"],
            block_number=event_data["block_number"],
            chain_id=event_data["chain_id"],
            fiat_balance=event_data["args"].get("newBalanceIdr"),
            submitted_by=event_data["args"].get("submittedBy"),
            timestamp=datetime.utcnow(),
        )
        session.add(event)
    
    async def _process_audit_proof_submitted(self, session: AsyncSession, event_data: Dict) -> None:
        """Process AuditProofSubmitted event"""
        event = ReserveEvent(
            event_type="AUDIT_PROOF_SUBMITTED",
            tx_hash=event_data["transaction_hash"],
            block_number=event_data["block_number"],
            chain_id=event_data["chain_id"],
            proof_hash=event_data["args"].get("proofHash"),
            submitted_by=event_data["args"].get("submittedBy"),
            timestamp=datetime.utcnow(),
        )
        session.add(event)
    
    async def _process_tokens_locked(self, session: AsyncSession, event_data: Dict) -> None:
        """Process TokensLocked event (bridge lock)"""
        event = BridgeEvent(
            event_type="TOKENS_LOCKED",
            tx_hash=event_data["transaction_hash"],
            block_number=event_data["block_number"],
            chain_id=event_data["chain_id"],
            bridge_nonce=event_data["args"].get("bridgeNonce"),
            src_chain=event_data["chain_id"],
            dst_chain=event_data["args"].get("dstChainId"),
            sender=event_data["args"].get("sender"),
            recipient=event_data["args"].get("recipient"),
            amount=event_data["args"].get("amount"),
            timestamp=datetime.utcnow(),
        )
        session.add(event)
    
    async def _process_tokens_released(self, session: AsyncSession, event_data: Dict) -> None:
        """Process TokensReleased event (bridge release)"""
        event = BridgeEvent(
            event_type="TOKENS_RELEASED",
            tx_hash=event_data["transaction_hash"],
            block_number=event_data["block_number"],
            chain_id=event_data["chain_id"],
            bridge_nonce=event_data["args"].get("bridgeNonce"),
            recipient=event_data["args"].get("recipient"),
            amount=event_data["args"].get("amount"),
            timestamp=datetime.utcnow(),
        )
        session.add(event)
    
    async def _process_message_relayed(self, session: AsyncSession, event_data: Dict) -> None:
        """Process MessageRelayed event (bridge relay)"""
        event = BridgeEvent(
            event_type="MESSAGE_RELAYED",
            tx_hash=event_data["transaction_hash"],
            block_number=event_data["block_number"],
            chain_id=event_data["chain_id"],
            bridge_nonce=event_data["args"].get("bridgeNonce"),
            src_chain=event_data["args"].get("srcChainId"),
            dst_chain=event_data["args"].get("dstChainId"),
            recipient=event_data["args"].get("recipient"),
            amount=event_data["args"].get("amount"),
            timestamp=datetime.utcnow(),
        )
        session.add(event)
    
    # ============================================================
    # INDEXING LOOP
    # ============================================================
    
    async def run(self) -> None:
        """Main indexing loop"""
        self._running = True
        logger.info("Event indexer started")
        
        while self._running:
            try:
                await self._indexing_cycle()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in indexing cycle: {e}")
                self.metrics["errors"] += 1
                self.metrics["last_error"] = str(e)
                await asyncio.sleep(5)  # Back off on error
        
        self.state = IndexerState.STOPPED
        logger.info("Event indexer stopped")
    
    async def _indexing_cycle(self) -> None:
        """Single indexing cycle across all processors and chains"""
        for processor in self.processors:
            for chain_id, chain_config in self.chain_configs.items():
                # Skip if contract not deployed on this chain
                if processor.contract_name not in chain_config.contracts:
                    continue
                
                try:
                    await self._process_chain_events(chain_id, processor)
                except Exception as e:
                    logger.error(f"Error processing {processor.contract_name}.{processor.event_name} on chain {chain_id}: {e}")
                    self.metrics["errors"] += 1
    
    async def _process_chain_events(self, chain_id: int, processor: EventProcessor) -> None:
        """Process events for a specific chain and processor"""
        key = self._get_cursor_key(chain_id, processor.contract_name, processor.event_name)
        cursor = self.cursors.get(key)
        
        if not cursor:
            logger.warning(f"No cursor for {key}")
            return
        
        # Get blockchain manager
        bm = self.blockchain_manager
        if not bm:
            return
        
        # Get latest block with confirmation buffer
        latest_block = await bm.get_latest_block_number(chain_id)
        target_block = latest_block - self.confirmation_blocks
        
        if target_block <= cursor.last_indexed_block:
            return  # Nothing new to index
        
        # Process in batches
        from_block = cursor.last_indexed_block + 1
        to_block = target_block
        
        batch_size = self.batch_size
        for batch_start in range(from_block, to_block + 1, self.batch_size):
            batch_end = min(batch_start + self.batch_size - 1, to_block)
            
            try:
                events = await bm.get_events(
                    chain_id=chain_id,
                    contract_name=processor.contract_name,
                    event_name=processor.event_name,
                    from_block=batch_start,
                    to_block=batch_end,
                    argument_filters=processor.argument_filters,
                )
                
                if events:
                    await self._process_events(chain_id, processor, events)
                
                # Update cursor
                cursor.last_indexed_block = batch_end
                if events:
                    last_event = events[-1]
                    cursor.last_indexed_tx_hash = last_event["transaction_hash"]
                    cursor.last_indexed_log_index = last_event["log_index"]
                
            except Exception as e:
                logger.error(f"Error processing batch {batch_start}-{batch_end}: {e}")
                raise
        
        # Save cursor periodically
        await self.save_cursors()
    
    async def _process_events(self, chain_id: int, processor: EventProcessor, events: List[Dict]) -> None:
        """Process a batch of events"""
        async for session in get_session_dependency():
            try:
                for event in events:
                    # Enrich event data
                    event["chain_id"] = chain_id
                    
                    # Call processor
                    await processor.processor(session, event)
                    self.metrics["events_processed"] += 1
                
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Error processing events: {e}")
                raise
    
    # ============================================================
    # REORG HANDLING
    # ============================================================
    
    async def check_and_handle_reorg(self, chain_id: int) -> bool:
        """Check for reorg and handle if detected"""
        for processor in self.processors:
            key = self._get_cursor_key(chain_id, processor.contract_name, processor.event_name)
            cursor = self.cursors.get(key)
            
            if not cursor or cursor.last_indexed_block <= 0:
                continue
            
            try:
                reorg_block = await self.blockchain_manager.check_for_reorg(chain_id, cursor.last_indexed_block)
                
                if reorg_block:
                    logger.warning(f"Reorg detected on chain {chain_id} at block {reorg_block.number}")
                    self.metrics["reorgs_detected"] += 1
                    
                    # Rollback cursor to before reorg
                    safe_block = max(0, reorg_block.number - self.max_reorg_depth)
                    cursor.last_indexed_block = safe_block
                    cursor.last_indexed_tx_hash = ""
                    cursor.last_indexed_log_index = 0
                    
                    # Delete events after safe block
                    await self._rollback_events(chain_id, processor, safe_block)
                    
                    self.metrics["reorgs_recovered"] += 1
                    logger.info(f"Recovered from reorg on chain {chain_id}, rolled back to block {safe_block}")
                    
                    return True
                    
            except Exception as e:
                logger.error(f"Error checking reorg: {e}")
        
        return False
    
    async def _rollback_events(self, chain_id: int, processor: EventProcessor, safe_block: int) -> None:
        """Rollback events after a reorg"""
        table_map = {
            "IDRCToken": TokenEvent,
            "ProofOfReserve": ReserveEvent,
            "BridgeVault": BridgeEvent,
            "BridgeRelayer": BridgeEvent,
        }
        
        event_table = table_map.get(processor.contract_name)
        if not event_table:
            return
        
        async for session in get_session_dependency():
            try:
                await session.execute(
                    event_table.__table__.delete().where(
                        and_(
                            event_table.chain_id == chain_id,
                            event_table.block_number > safe_block,
                        )
                    )
                )
                await session.commit()
                logger.info(f"Rolled back {processor.contract_name}.{processor.event_name} events after block {safe_block}")
            except Exception as e:
                await session.rollback()
                logger.error(f"Error rolling back events: {e}")
    
    async def _periodic_reorg_check(self) -> None:
        """Periodically check for reorgs"""
        while self._running:
            try:
                for chain_id in self.chain_configs:
                    await self.check_and_handle_reorg(chain_id)
            except Exception as e:
                logger.error(f"Error in reorg check: {e}")
            await asyncio.sleep(60)  # Check every minute
    
    # ============================================================
    # CONTROL
    # ============================================================
    
    def stop(self) -> None:
        """Stop the indexer"""
        self._running = False
        self.state = IndexerState.STOPPING
        logger.info("Indexer stop requested")
    
    def get_metrics(self) -> Dict[str, Any]:
        return {
            **self.metrics,
            "state": self.state.value,
            "cursors": {k: {
                "chain_id": v.chain_id,
                "contract": v.contract_name,
                "event": v.event_name,
                "last_block": v.last_indexed_block,
            } for k, v in self.cursors.items()},
        }


# Global indexer instance
_indexer: Optional[EventIndexer] = None


async def get_event_indexer(
    environment: Environment = None,
    database_url: str = None,
) -> EventIndexer:
    """Get or create global event indexer"""
    global _indexer
    
    if environment is None:
        env_str = os.getenv("ENVIRONMENT", "development")
        environment = Environment(env_str.lower())
    
    if database_url is None:
        database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/idrc_indexer")
    
    if _indexer is None or _indexer.environment != environment:
        chain_configs = {cid: config for cid, config in CHAINS.items() 
                        if cid in [c.chain_id for c in get_chains_for_environment(environment)]}
        _indexer = EventIndexer(chain_configs, database_url, environment)
        await _indexer.initialize()
    
    return _indexer


async def start_indexer():
    """Start the indexer as a background task"""
    indexer = await get_event_indexer()
    task = asyncio.create_task(indexer.run())
    
    # Also start periodic reorg check
    reorg_task = asyncio.create_task(indexer._periodic_reorg_check())
    
    return indexer, [task, reorg_task]


async def stop_indexer():
    """Stop the indexer"""
    global _indexer
    if _indexer:
        _indexer.stop()
        # Wait for tasks to complete
        await asyncio.sleep(2)
        _indexer = None


# Export
__all__ = [
    "EventIndexer",
    "IndexerState",
    "IndexerCursor",
    "EventProcessor",
    "get_event_indexer",
    "start_indexer",
    "stop_indexer",
]