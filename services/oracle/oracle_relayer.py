"""
Oracle Relayer Service
Fetches fiat balance from bank custodian and updates ProofOfReserve contract
"""
import os
import asyncio
import logging
import signal
import json
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

from web3 import Web3
from web3.contract import Contract
from eth_account import Account

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("oracle-relayer")


@dataclass
class OracleConfig:
    chain_id: int
    rpc_url: str
    reserve_address: str
    oracle_private_key: str
    poll_interval: int = 900  # 15 minutes
    max_retries: int = 3
    retry_delay: int = 30


class BankCustodianClient:
    """Simulated bank custodian API client"""

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key

    async def get_fiat_balance(self) -> int:
        """
        Fetch current IDR balance from bank custodian
        Returns balance in wei (18 decimals)
        """
        # In production, this would call the bank's BI-FAST/ISO 20022 API
        # For now, simulate with a mock value
        import random
        base_balance = 10_000_000_000 * 10**18  # 10B IDR
        variation = random.randint(-100_000_000, 100_000_000) * 10**18
        return base_balance + variation


class OracleRelayer:
    def __init__(self, config: OracleConfig):
        self.config = config
        self.w3 = Web3(Web3.HTTPProvider(config.rpc_url))
        self.account = Account.from_key(config.oracle_private_key)

        # Load reserve contract
        with open("./out/ProofOfReserve.sol/ProofOfReserve.json") as f:
            artifact = json.load(f)

        self.reserve = self.w3.eth.contract(
            address=Web3.to_checksum_address(config.reserve_address),
            abi=artifact["abi"]
        )

        self.bank_client = BankCustodianClient(
            api_url=os.getenv("BANK_API_URL", "https://api.bank.example.com"),
            api_key=os.getenv("BANK_API_KEY", "")
        )

        self.running = False
        self.last_update = None
        self.consecutive_failures = 0

    async def fetch_and_update(self) -> bool:
        """Fetch balance from bank and update reserve contract"""
        try:
            logger.info("Fetching fiat balance from bank custodian...")
            fiat_balance = await self.bank_client.get_fiat_balance()

            logger.info(f"Updating reserve with balance: {fiat_balance / 10**18:,.0f} IDR")

            # Build transaction
            nonce = self.w3.eth.get_transaction_count(self.account.address)
            tx = self.reserve.functions.updateFiatBalance(fiat_balance).build_transaction({
                "from": self.account.address,
                "nonce": nonce,
                "gas": 100000,
                "gasPrice": self.w3.eth.gas_price,
                "chainId": self.config.chain_id
            })

            # Sign and send
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.config.oracle_private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)

            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt.status == 1:
                logger.info(f"Successfully updated reserve. Tx: {tx_hash.hex()}")
                self.last_update = datetime.utcnow()
                self.consecutive_failures = 0
                return True
            else:
                logger.error(f"Transaction failed: {tx_hash.hex()}")
                return False

        except Exception as e:
            logger.error(f"Failed to update reserve: {e}")
            self.consecutive_failures += 1
            return False

    async def run(self):
        """Main loop"""
        self.running = True
        logger.info(f"Starting Oracle Relayer for chain {self.config.chain_id}")
        logger.info(f"Poll interval: {self.config.poll_interval}s")

        while self.running:
            try:
                success = await self.fetch_and_update()

                if not success:
                    self.consecutive_failures += 1
                    if self.consecutive_failures >= 5:
                        logger.critical("Too many consecutive failures! Alerting...")
                        # In production: send alert to PagerDuty, Slack, etc.

            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                self.consecutive_failures += 1

            # Wait for next poll
            await asyncio.sleep(self.config.poll_interval)

    def stop(self):
        self.running = False


async def main():
    # Load configuration
    config = OracleConfig(
        chain_id=int(os.getenv("CHAIN_ID", "11155111")),
        rpc_url=os.getenv("RPC_URL", "https://rpc.sepolia.org"),
        reserve_address=os.getenv("RESERVE_ADDRESS", ""),
        oracle_private_key=os.getenv("ORACLE_PRIVATE_KEY", ""),
        poll_interval=int(os.getenv("POLL_INTERVAL", "900"))
    )

    if not config.reserve_address or not config.oracle_private_key:
        logger.error("Missing required environment variables")
        return

    relayer = OracleRelayer(config)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, relayer.stop)

    await relayer.run()


if __name__ == "__main__":
    asyncio.run(main())