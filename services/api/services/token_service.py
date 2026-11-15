"""
Token Service - Business logic for token operations
"""
from typing import List, Dict, Any
from web3 import Web3
from web3.contract import Contract
from eth_typing import ChecksumAddress

from ..models import AddressStr, WeiAmount, IDRCAmount


class TokenService:
    def __init__(self, token_contract: Contract, chain_id: int):
        self.token = token_contract
        self.chain_id = chain_id
        self.w3 = token_contract.w3

    async def get_token_info(self) -> Dict[str, Any]:
        """Get token basic information"""
        return {
            "name": self.token.functions.name().call(),
            "symbol": self.token.functions.symbol().call(),
            "decimals": self.token.functions.decimals().call(),
            "total_supply": IDRCAmount(self.token.functions.totalSupply().call() / 10**18),
            "supply_cap": IDRCAmount(self.token.functions.supplyCap().call() / 10**18),
            "paused": self.token.functions.paused().call(),
            "reserve_proof_hash": self.token.functions.reserveProofHash().call().hex()
        }

    async def balance_of(self, address: AddressStr) -> int:
        return self.token.functions.balanceOf(address).call()

    async def allowance(self, owner: AddressStr, spender: AddressStr) -> int:
        return self.token.functions.allowance(owner, spender).call()

    async def mint(self, to: AddressStr, amount: WeiAmount, caller: AddressStr) -> str:
        tx_hash = self.token.functions.mint(to, amount).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def issuer_burn(self, from_: AddressStr, amount: WeiAmount, caller: AddressStr) -> str:
        tx_hash = self.token.functions.issuerBurn(from_, amount).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def burn(self, amount: WeiAmount, caller: AddressStr) -> str:
        tx_hash = self.token.functions.burn(amount).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def transfer(self, to: AddressStr, amount: WeiAmount, caller: AddressStr) -> str:
        tx_hash = self.token.functions.transfer(to, amount).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def approve(self, spender: AddressStr, amount: WeiAmount, caller: AddressStr) -> str:
        tx_hash = self.token.functions.approve(spender, amount).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def permit(
        self, owner: AddressStr, spender: AddressStr, value: WeiAmount,
        deadline: int, v: int, r: str, s: str
    ) -> str:
        tx_hash = self.token.functions.permit(owner, spender, value, deadline, v, r, s).transact()
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def pause(self, caller: AddressStr) -> str:
        tx_hash = self.token.functions.pause().transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def unpause(self, caller: AddressStr) -> str:
        tx_hash = self.token.functions.unpause().transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def blacklist(self, account: AddressStr, caller: AddressStr) -> str:
        tx_hash = self.token.functions.blacklist(account).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def unblacklist(self, account: AddressStr, caller: AddressStr) -> str:
        tx_hash = self.token.functions.unblacklist(account).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def is_blacklisted(self, address: AddressStr) -> bool:
        return self.token.functions.isBlacklisted(address).call()

    async def get_top_holders(self, limit: int) -> List[Dict[str, Any]]:
        # This would require event indexing in production
        # Simplified version
        return []

    async def has_role(self, role: str, account: AddressStr) -> bool:
        role_hash = self.w3.keccak(text=role) if role != "DEFAULT_ADMIN_ROLE" else bytes(32)
        return self.token.functions.hasRole(role_hash, account).call()