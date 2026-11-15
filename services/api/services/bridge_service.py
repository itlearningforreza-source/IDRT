"""
Bridge Service - Business logic for cross-chain bridge operations
"""
from typing import List, Dict, Any
from web3 import Web3
from web3.contract import Contract

from ..models import AddressStr, WeiAmount, IDRCAmount, ChainId


class BridgeService:
    def __init__(self, contracts: Dict[str, Contract]):
        self.contracts = contracts
        self.w3 = list(contracts.values())[0].w3 if contracts else None

    async def get_chain_status(self, chain_id: int) -> Dict[str, Any]:
        vault = self.contracts.get(f"vault_{chain_id}")
        relayer = self.contracts.get(f"relayer_{chain_id}")
        token = self.contracts.get(f"token_{chain_id}")

        if not vault:
            return {}

        return {
            "chain_id": chain_id,
            "total_locked": IDRCAmount(vault.functions.totalLocked().call() / 10**18),
            "relayer": vault.functions.relayer().call(),
            "vault_address": vault.address,
            "token_address": token.address if token else "",
        }

    async def get_all_chains_status(self) -> List[Dict[str, Any]]:
        statuses = []
        for key, contract in self.contracts.items():
            if key.startswith("vault_"):
                chain_id = int(key.split("_")[1])
                status = await self.get_chain_status(chain_id)
                if status:
                    statuses.append(status)
        return statuses

    async def get_supported_chains(self) -> List[int]:
        chains = []
        for key in self.contracts.keys():
            if key.startswith("vault_"):
                chains.append(int(key.split("_")[1]))
        return chains

    async def transfer(
        self, src_chain: int, dst_chain: int, sender: AddressStr,
        recipient: AddressStr, amount: WeiAmount, caller: AddressStr
    ) -> Dict[str, Any]:
        vault = self.contracts.get(f"vault_{src_chain}")
        if not vault:
            raise ValueError(f"No vault for chain {src_chain}")

        tx_hash = vault.functions.lock(
            self.contracts[f"token_{src_chain}"].address,
            sender, recipient, amount, dst_chain
        ).transact({"from": caller})

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        # Parse bridge nonce from event
        bridge_nonce = 0
        for log in receipt.logs:
            if log.topics[0].hex() == self.w3.keccak(text="TokensLocked(uint256,address,address,uint256,uint256)").hex():
                bridge_nonce = int(log.topics[1].hex(), 16)
                break

        return {
            "bridge_nonce": bridge_nonce,
            "src_chain": src_chain,
            "dst_chain": dst_chain,
            "sender": sender,
            "recipient": recipient,
            "amount": IDRCAmount(amount / 10**18),
            "lock_tx_hash": tx_hash.hex()
        }

    async def complete_transfer(
        self, bridge_nonce: int, src_chain: int, dst_chain: int,
        recipient: AddressStr, amount: WeiAmount, caller: AddressStr
    ) -> str:
        relayer = self.contracts.get(f"relayer_{dst_chain}")
        token = self.contracts.get(f"token_{dst_chain}")

        if not relayer or not token:
            raise ValueError(f"No relayer or token for chain {dst_chain}")

        tx_hash = relayer.functions.relay(
            bridge_nonce, src_chain, dst_chain, recipient, amount, token.address
        ).transact({"from": caller})

        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def is_nonce_processed(self, bridge_nonce: int, src_chain: int) -> bool:
        # Check on destination chain's relayer
        for key, contract in self.contracts.items():
            if key.startswith("relayer_") and hasattr(contract.functions, 'processedMessages'):
                try:
                    return contract.functions.processedMessages(src_chain, bridge_nonce).call()
                except Exception:
                    pass
        return False

    async def get_locked_balance(self, address: AddressStr) -> int:
        # Sum locked amounts across all vaults for this address
        # Simplified - would need event indexing in production
        return 0

    async def has_relayer_admin_role(self, address: AddressStr) -> bool:
        for key, contract in self.contracts.items():
            if key.startswith("relayer_"):
                role_hash = self.w3.keccak(text="RELAYER_ADMIN_ROLE")
                return contract.functions.hasRole(role_hash, address).call()
        return False

    async def pause(self, caller: AddressStr) -> str:
        for key, contract in self.contracts.items():
            if key.startswith("vault_") or key.startswith("relayer_"):
                try:
                    tx_hash = contract.functions.pause().transact({"from": caller})
                    self.w3.eth.wait_for_transaction_receipt(tx_hash)
                    return tx_hash.hex()
                except Exception:
                    pass
        return ""

    async def unpause(self, caller: AddressStr) -> str:
        for key, contract in self.contracts.items():
            if key.startswith("vault_") or key.startswith("relayer_"):
                try:
                    tx_hash = contract.functions.unpause().transact({"from": caller})
                    self.w3.eth.wait_for_transaction_receipt(tx_hash)
                    return tx_hash.hex()
                except Exception:
                    pass
        return ""

    async def set_relayer(self, new_relayer: AddressStr, caller: AddressStr) -> str:
        for key, contract in self.contracts.items():
            if key.startswith("relayer_"):
                tx_hash = contract.functions.setRelayer(new_relayer).transact({"from": caller})
                self.w3.eth.wait_for_transaction_receipt(tx_hash)
                return tx_hash.hex()
        return ""