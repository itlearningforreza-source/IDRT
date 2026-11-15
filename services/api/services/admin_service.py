"""
Admin Service - Business logic for administrative operations
"""
from typing import List
from web3 import Web3
from web3.contract import Contract

from ..models import AddressStr, Role


class AdminService:
    def __init__(self, contract: Contract, chain_id: int):
        self.contract = contract
        self.chain_id = chain_id
        self.w3 = contract.w3

    async def upgrade(self, new_implementation: AddressStr, caller: AddressStr) -> str:
        tx_hash = self.contract.functions.upgrade("IDRCToken", new_implementation).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def upgrade_and_call(
        self, new_implementation: AddressStr, init_data: str, caller: AddressStr
    ) -> str:
        tx_hash = self.contract.functions.upgradeAndCall(
            "IDRCToken", new_implementation, bytes.fromhex(init_data[2:])
        ).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def get_implementation(self) -> AddressStr:
        return self.contract.functions.getImplementation("IDRCToken").call()

    async def get_implementation_history(self) -> List[AddressStr]:
        # Would need event parsing in production
        return []

    async def grant_role(self, role: str, account: AddressStr, caller: AddressStr) -> str:
        role_hash = self.w3.keccak(text=role) if role != "DEFAULT_ADMIN_ROLE" else bytes(32)
        tx_hash = self.contract.functions.grantRole(role_hash, account).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def revoke_role(self, role: str, account: AddressStr, caller: AddressStr) -> str:
        role_hash = self.w3.keccak(text=role) if role != "DEFAULT_ADMIN_ROLE" else bytes(32)
        tx_hash = self.contract.functions.revokeRole(role_hash, account).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def get_role_members(self, role: str) -> List[AddressStr]:
        # Would need EnumerableSet in production
        return []

    async def pause_token(self, caller: AddressStr) -> str:
        tx_hash = self.contract.functions.pause().transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def unpause_token(self, caller: AddressStr) -> str:
        tx_hash = self.contract.functions.unpause().transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def blacklist(self, account: AddressStr, caller: AddressStr) -> str:
        tx_hash = self.contract.functions.blacklist(account).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def unblacklist(self, account: AddressStr, caller: AddressStr) -> str:
        tx_hash = self.contract.functions.unblacklist(account).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()