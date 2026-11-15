"""
Bridge Relayer Service
Listens for bridge events on source chains and relays them to destination chains
"""
import os
import asyncio
import logging
import signal
import json
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

from web3 import Web3
from web3.contract import Contract
from eth_account import Account
from eth_typing import ChecksumAddress

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bridge-relayer")


@dataclass
class ChainConfig:
    chain_id: int
    name: str
    rpc_url: str
    vault_address: str
    relayer_address: str
    token_address: str
    poll_interval: int = 30
    confirmation_blocks: int = 3


@dataclass
class BridgeMessage:
    bridge_nonce: int
    src_chain: int
    dst_chain: int
    sender: str
    recipient: str
    amount: int
    block_number: int
    tx_hash: str


class BridgeRelayer:
    def __init__(self, configs: Dict[int, ChainConfig], relayer_private_key: str):
        self.configs = configs
        self.relayer_account = Account.from_key(relayer_private_key)
        self.providers: Dict[int, Web3] = {}
        self.vaults: Dict[int, Contract] = {}
        self.relayers: Dict[int, Contract] = {}
        self.tokens: Dict[int, Contract] = {}
        self.processed_nonces: Dict[int, Set[int]] = {}  # src_chain -> set of nonces
        self.running = False

        # Load ABIs
        with open("./out/BridgeVault.sol/BridgeVault.json") as f:
            self.vault_abi = json.load(f)["abi"]
        with open("./out/BridgeRelayer.sol/BridgeRelayer.json") as f:
            self.relayer_abi = json.load(f)["abi"]
        with open("./out/IDRCToken.sol/IDRCToken.json") as f:
            self.token_abi = json.load(f)["abi"]

    async def initialize(self):
        """Initialize providers and contracts for all chains"""
        for chain_id, config in self.configs.items():
            w3 = Web3(Web3.HTTPProvider(config.rpc_url))

            # Add POA middleware for non-Ethereum chains
            if chain_id in [56, 97, 137, 80002, 42161, 421614, 10, 11155420, 8453, 84532]:
                from web3.middleware import geth_poa_middleware
                w3.middleware_onion.inject(geth_poa_middleware, layer=0)

            self.providers[chain_id] = w3
            self.processed_nonces[chain_id] = set()

            # Initialize contracts
            self.vaults[chain_id] = w3.eth.contract(
                address=Web3.to_checksum_address(config.vault_address),
                abi=self.vault_abi
            )
            self.relayers[chain_id] = w3.eth.contract(
                address=Web3.to_checksum_address(config.relayer_address),
                abi=self.relayer_abi
            )
            self.tokens[chain_id] = w3.eth.contract(
                address=Web3.to_checksum_address(config.token_address),
                abi=self.token_abi
            )

            # Load already processed nonces from contract
            await self._load_processed_nonces(chain_id)

            logger.info(f"Initialized chain {config.name} ({chain_id})")

    async def _load_processed_nonces(self, src_chain: int):
        """Load already processed nonces from relayer contract"""
        for dst_chain in self.configs.keys():
            if dst_chain == src_chain:
                continue
            try:
                relayer = self.relayers[dst_chain]
                # This would need event indexing in production
                # For now, we track in memory
            except Exception as e:
                logger.warning(f"Could not load processed nonces for {src_chain}->{dst_chain}: {e}")

    async def poll_chain(self, src_chain: int):
        """Poll source chain for new Lock events"""
        config = self.configs[src_chain]
        vault = self.vaults[src_chain]
        w3 = self.providers[src_chain]

        try:
            latest_block = w3.eth.get_block("latest").number
            from_block = getattr(self, f"_last_poll_block_{src_chain}", latest_block - 100)
            to_block = latest_block - config.confirmation_blocks

            if from_block > to_block:
                return

            # Query Lock events
            event_signature = w3.keccak(text="TokensLocked(uint256,address,address,uint256,uint256)").hex()
            logs = w3.eth.get_logs({
                "fromBlock": from_block,
                "toBlock": to_block,
                "address": config.vault_address,
                "topics": [event_signature]
            })

            for log in logs:
                await self._process_lock_event(log, src_chain)

            setattr(self, f"_last_poll_block_{src_chain}", to_block + 1)

        except Exception as e:
            logger.error(f"Error polling chain {config.name}: {e}")

    async def _process_lock_event(self, log, src_chain: int):
        """Process a TokensLocked event"""
        try:
            # Decode event data
            # Topics: [event_signature, bridge_nonce, sender, recipient]
            # Data: amount, dstChainId
            bridge_nonce = int(log["topics"][1].hex(), 16)
            sender = "0x" + log["topics"][2].hex()[-40:]
            recipient = "0x" + log["topics"][3].hex()[-40:]

            # Decode data (amount, dstChainId)
            data = log["data"]
            amount = int(data[:66], 16)
            dst_chain = int(data[66:], 16)

            # Check if already processed
            if bridge_nonce in self.processed_nonces.get(src_chain, set()):
                logger.debug(f"Nonce {bridge_nonce} from chain {src_chain} already processed")
                return

            logger.info(f"Found Lock event: nonce={bridge_nonce}, {sender} -> {recipient}, "
                       f"{amount / 10**18:.6f} IDRC, {src_chain} -> {dst_chain}")

            # Relay to destination chain
            success = await self._relay_message(
                bridge_nonce, src_chain, dst_chain, sender, recipient, amount
            )

            if success:
                self.processed_nonces.setdefault(src_chain, set()).add(bridge_nonce)
                logger.info(f"Successfully relayed nonce {bridge_nonce} to chain {dst_chain}")
            else:
                logger.error(f"Failed to relay nonce {bridge_nonce} to chain {dst_chain}")

        except Exception as e:
            logger.error(f"Error processing lock event: {e}")

    async def _relay_message(
        self, bridge_nonce: int, src_chain: int, dst_chain: int,
        sender: str, recipient: str, amount: int
    ) -> bool:
        """Relay message to destination chain"""
        if dst_chain not in self.configs:
            logger.error(f"Destination chain {dst_chain} not configured")
            return False

        try:
            relayer = self.relayers[dst_chain]
            token = self.tokens[dst_chain]
            w3 = self.providers[dst_chain]

            # Check if already processed on destination
            processed = relayer.functions.processedMessages(src_chain, bridge_nonce).call()
            if processed:
                logger.info(f"Message {bridge_nonce} from {src_chain} already processed on {dst_chain}")
                return True

            # Build relay transaction
            nonce = w3.eth.get_transaction_count(self.relayer_account.address)
            tx = relayer.functions.relay(
                bridge_nonce, src_chain, dst_chain, recipient, amount, token.address
            ).build_transaction({
                "from": self.relayer_account.address,
                "nonce": nonce,
                "gas": 500000,
                "gasPrice": w3.eth.gas_price,
                "chainId": dst_chain
            })

            # Sign and send
            signed_tx = w3.eth.account.sign_transaction(tx, self.relayer_account.key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)

            # Wait for confirmation
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

            return receipt.status == 1

        except Exception as e:
            logger.error(f"Error relaying to chain {dst_chain}: {e}")
            return False

    async def run(self):
        """Main loop - poll all chains"""
        self.running = True
        logger.info("Starting Bridge Relayer...")

        while self.running:
            try:
                # Poll all source chains in parallel
                tasks = [self.poll_chain(chain_id) for chain_id in self.configs.keys()]
                await asyncio.gather(*tasks, return_exceptions=True)

                # Wait before next poll
                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(30)

    def stop(self):
        self.running = False


async def main():
    # Load chain configurations from environment
    configs = {}

    # Example configuration - in production load from config file
    chain_configs = {
        11155111: ChainConfig(  # Sepolia
            chain_id=11155111,
            name="Ethereum Sepolia",
            rpc_url=os.getenv("SEPOLIA_RPC_URL", "https://rpc.sepolia.org"),
            vault_address=os.getenv("SEPOLIA_VAULT_ADDRESS", ""),
            relayer_address=os.getenv("SEPOLIA_RELAYER_ADDRESS", ""),
            token_address=os.getenv("SEPOLIA_TOKEN_ADDRESS", ""),
        ),
        80002: ChainConfig(  # Polygon Amoy
            chain_id=80002,
            name="Polygon Amoy",
            rpc_url=os.getenv("AMOY_RPC_URL", "https://rpc-amoy.polygon.technology"),
            vault_address=os.getenv("AMOY_VAULT_ADDRESS", ""),
            relayer_address=os.getenv("AMOY_RELAYER_ADDRESS", ""),
            token_address=os.getenv("AMOY_TOKEN_ADDRESS", ""),
        ),
    }

    # Filter out chains with missing addresses
    for chain_id, config in chain_configs.items():
        if all([config.vault_address, config.relayer_address, config.token_address]):
            configs[chain_id] = config
        else:
            logger.warning(f"Skipping chain {config.name} - missing contract addresses")

    if not configs:
        logger.error("No valid chain configurations!")
        return

    relayer_private_key = os.getenv("RELAYER_PRIVATE_KEY", "")
    if not relayer_private_key:
        logger.error("Missing RELAYER_PRIVATE_KEY")
        return

    relayer = BridgeRelayer(configs, relayer_private_key)
    await relayer.initialize()

    # Handle shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, relayer.stop)

    await relayer.run()


if __name__ == "__main__":
    asyncio.run(main())