"""Off-chain Oracle Relayer Service for IDR Coin Proof of Reserve (PoR)."""

import logging
import time
from typing import Optional
from idrc.reserve import ProofOfReserve

logger = logging.getLogger("IDRC_Oracle_Service")


class OracleRelayerService:
    """Simulates a secure off-chain service fetching bank balances and pushing updates to the ProofOfReserve on-chain contract."""

    def __init__(self, reserve_contract: ProofOfReserve, oracle_address: str):
        self.reserve = reserve_contract
        self.oracle_address = oracle_address

    def fetch_bank_custodian_balance(self) -> int:
        """Simulate secure API call to bank escrow account."""
        # In production, this makes a signed HTTPS request to Bank BI-FAST / Escrow API
        return self.reserve.get_fiat_balance()

    def sync_oracle(self, new_balance: Optional[int] = None) -> bool:
        """Push current bank balance to reserve contract."""
        if new_balance is None:
            new_balance = self.fetch_bank_custodian_balance()

        logger.info(f"Syncing Oracle Balance: {new_balance} IDR")
        self.reserve.update_fiat_balance(new_balance, caller=self.oracle_address)
        return True
