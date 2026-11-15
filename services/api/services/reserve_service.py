"""
Reserve Service - Business logic for Proof of Reserve operations
"""
from typing import List, Dict, Any, Optional
from decimal import Decimal
from web3 import Web3
from web3.contract import Contract

from ..models import AddressStr, WeiAmount, IDRCAmount


class ReserveService:
    def __init__(self, reserve_contract: Contract, chain_id: int):
        self.reserve = reserve_contract
        self.chain_id = chain_id
        self.w3 = reserve_contract.w3

    async def get_status(self, token_supply: int) -> Dict[str, Any]:
        fiat_balance = self.reserve.functions.fiatBalanceIdr().call()
        last_update = self.reserve.functions.lastOracleUpdate().call()
        proof_hash = self.reserve.functions.latestProofHash().call()
        report_count = self.reserve.functions.auditReportCount().call()

        ratio = (fiat_balance * 10**18) // token_supply if token_supply > 0 else 2**256 - 1
        is_fully = ratio >= 10**18

        return {
            "fiat_balance_idr": IDRCAmount(fiat_balance / 10**18),
            "latest_proof_hash": proof_hash.hex(),
            "last_oracle_update": last_update if last_update > 0 else None,
            "reserve_ratio": Decimal(ratio) / 10**18,
            "is_fully_collateralised": is_fully,
            "audit_report_count": report_count
        }

    async def submit_audit_proof(self, proof_hash: str, reported_fiat: WeiAmount, caller: AddressStr) -> str:
        tx_hash = self.reserve.functions.submitAuditProof(
            bytes.fromhex(proof_hash[2:]), reported_fiat
        ).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def update_fiat_balance(self, new_balance: WeiAmount, caller: AddressStr) -> str:
        tx_hash = self.reserve.functions.updateFiatBalance(new_balance).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def set_oracle(self, new_oracle: AddressStr, caller: AddressStr) -> str:
        tx_hash = self.reserve.functions.setOracle(new_oracle).transact({"from": caller})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    async def get_audit_reports(self, limit: int, offset: int) -> List[Dict[str, Any]]:
        reports = []
        count = self.reserve.functions.auditReportCount().call()
        for i in range(min(count, offset + limit) - 1, offset - 1, -1):
            report = self.reserve.functions.getAuditReport(i + 1).call()
            reports.append({
                "seq": report[0],
                "proof_hash": report[1].hex(),
                "reported_fiat_idr": IDRCAmount(report[2] / 10**18),
                "submitted_by": report[3],
                "timestamp": report[4]
            })
        return reports

    async def get_audit_report(self, seq: int) -> Optional[Dict[str, Any]]:
        try:
            report = self.reserve.functions.getAuditReport(seq).call()
            return {
                "seq": report[0],
                "proof_hash": report[1].hex(),
                "reported_fiat_idr": IDRCAmount(report[2] / 10**18),
                "submitted_by": report[3],
                "timestamp": report[4]
            }
        except Exception:
            return None

    async def verify_proof(self, report_data: str) -> bool:
        return self.reserve.functions.verifyProof(report_data.encode()).call()

    async def check_collateralisation(self, token_supply: int) -> bool:
        return self.reserve.functions.checkCollateralisation(token_supply).call()

    async def reserve_ratio(self, token_supply: int) -> int:
        return self.reserve.functions.reserveRatio(token_supply).call()

    async def has_role(self, role: str, account: AddressStr) -> bool:
        role_hash = self.w3.keccak(text=role) if role != "DEFAULT_ADMIN_ROLE" else bytes(32)
        return self.reserve.functions.hasRole(role_hash, account).call()