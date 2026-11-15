"""
Multisig Service - Business logic for multisig operations
"""
from typing import List, Dict, Any, Tuple
from web3 import Web3
from web3.contract import Contract

from ..models import AddressStr, WeiAmount


class MultisigService:
    def __init__(self, multisig_contract: Contract, chain_id: int):
        self.multisig = multisig_contract
        self.chain_id = chain_id
        self.w3 = multisig_contract.w3

    async def is_owner(self, address: AddressStr) -> bool:
        return self.multisig.functions.isOwner(address).call()

    async def get_owners(self) -> List[AddressStr]:
        return self.multisig.functions.getOwners().call()

    async def get_threshold(self) -> int:
        return self.multisig.functions.getThreshold().call()

    async def get_transaction_count(self) -> int:
        return self.multisig.functions.getTransactionCount().call()

    async def propose(
        self, to: AddressStr, value: WeiAmount, data: str, caller: AddressStr
    ) -> int:
        tx_hash = self.multisig.functions.submitTransaction(to, value, data).transact({"from": caller})
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        # Parse transaction ID from event
        for log in receipt.logs:
            if log.topics[0].hex() == self.w3.keccak(text="Submission(address,uint256)").hex():
                return int(log.topics[2].hex(), 16)
        return self.multisig.functions.getTransactionCount().call() - 1

    async def confirm(self, tx_id: int, caller: AddressStr) -> str:
        tx_hash = self.multisig.functions.confirmTransaction(tx_id).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def revoke(self, tx_id: int, caller: AddressStr) -> str:
        tx_hash = self.multisig.functions.revokeConfirmation(tx_id).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def execute(self, tx_id: int, caller: AddressStr) -> str:
        tx_hash = self.multisig.functions.executeTransaction(tx_id).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def get_transaction(self, tx_id: int) -> Dict[str, Any]:
        tx = self.multisig.functions.transactions(tx_id).call()
        confirmations, executed = self.multisig.functions.getConfirmations(tx_id).call()
        confirmers = confirmations

        return {
            "to": tx[0],
            "value": tx[1],
            "data": tx[2].hex() if isinstance(tx[2], bytes) else tx[2],
            "executed": tx[3],
            "threshold": self.multisig.functions.getThreshold().call(),
            "confirmers": confirmers,
            "proposed_by": "",  # Would need event parsing
            "submission_time": None,
            "confirmations": len(confirmers)
        }

    async def get_transaction_lists(
        self, from_id: int, to_id: int
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        count = await self.get_transaction_count()
        to_id = min(to_id, count)

        pending, confirmed, executed = [], [], []
        for i in range(from_id, to_id):
            tx = await self.get_transaction(i)
            if tx["executed"]:
                executed.append(tx)
            elif tx["confirmations"] >= tx["threshold"]:
                confirmed.append(tx)
            else:
                pending.append(tx)

        return pending, confirmed, executed

    async def add_owner(self, new_owner: AddressStr, new_threshold: int, caller: AddressStr) -> str:
        tx_hash = self.multisig.functions.addOwnerWithThreshold(new_owner, new_threshold).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def remove_owner(self, owner: AddressStr, new_threshold: int, caller: AddressStr) -> str:
        tx_hash = self.multisig.functions.removeOwner(owner, new_threshold).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def change_threshold(self, new_threshold: int, caller: AddressStr) -> str:
        tx_hash = self.multisig.functions.changeThreshold(new_threshold).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()