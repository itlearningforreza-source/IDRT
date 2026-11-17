"""
tests/test_reserve.py
=====================
Unit tests for IDRCReserve (Section 4.6 & 6.1).
Covers: audit proof submission, hash verification, oracle updates,
        reserve ratio calculation, and collateralisation checks.
"""

import pytest

from idrc.exceptions import AccessControlError, ReserveError
from idrc.reserve import IDRCReserve

ADMIN  = "0xAdmin"
ORACLE = "0xOracle"


@pytest.fixture
def reserve():
    return IDRCReserve(admin=ADMIN, oracle=ORACLE)


# ─── Audit Proof (Approach A) ─────────────────────────────────────────────────

class TestAuditProof:
    def test_submit_proof_success(self, reserve):
        report = reserve.submit_audit_proof(
            proof_hash="abc123deadbeef",
            reported_fiat_idr=1_000_000 * 10**18,
            caller=ADMIN,
        )
        assert report.proof_hash == "abc123deadbeef"
        assert report.seq == 1
        assert reserve.latest_proof_hash == "abc123deadbeef"

    def test_submit_multiple_proofs_increments_seq(self, reserve):
        reserve.submit_audit_proof("hash1", 1_000 * 10**18, caller=ADMIN)
        r2 = reserve.submit_audit_proof("hash2", 2_000 * 10**18, caller=ADMIN)
        assert r2.seq == 2
        assert reserve.latest_proof_hash == "hash2"
        assert len(reserve.audit_reports) == 2

    def test_submit_proof_non_admin_reverts(self, reserve):
        with pytest.raises(AccessControlError):
            reserve.submit_audit_proof("hash1", 1_000 * 10**18, caller="0xEvil")

    def test_submit_empty_hash_reverts(self, reserve):
        with pytest.raises(ReserveError):
            reserve.submit_audit_proof("", 1_000 * 10**18, caller=ADMIN)

    def test_submit_negative_fiat_reverts(self, reserve):
        with pytest.raises(ReserveError):
            reserve.submit_audit_proof("hash1", -1, caller=ADMIN)

    def test_verify_proof_matches(self, reserve):
        """compute_proof_hash then verify round-trip."""
        report_bytes = b"Auditor Report Q1 2025 - IDR 1,000,000"
        proof_hash = IDRCReserve.compute_proof_hash(report_bytes)
        reserve.submit_audit_proof(proof_hash, 1_000_000 * 10**18, caller=ADMIN)

        assert reserve.verify_proof(report_bytes) is True

    def test_verify_proof_wrong_content(self, reserve):
        """Tampered report bytes should fail verification."""
        real_bytes    = b"Real report content"
        tampered_bytes = b"Fake content"
        proof_hash = IDRCReserve.compute_proof_hash(real_bytes)
        reserve.submit_audit_proof(proof_hash, 1_000 * 10**18, caller=ADMIN)

        assert reserve.verify_proof(tampered_bytes) is False

    def test_verify_with_no_proof_returns_false(self, reserve):
        assert reserve.verify_proof(b"anything") is False


# ─── Oracle Fiat Balance (Approach B) ─────────────────────────────────────────

class TestOracleFiatBalance:
    def test_update_fiat_balance_success(self, reserve):
        reserve.update_fiat_balance(5_000_000 * 10**18, caller=ORACLE)
        assert reserve.fiat_balance_idr == 5_000_000 * 10**18

    def test_update_fiat_balance_non_oracle_reverts(self, reserve):
        with pytest.raises(AccessControlError):
            reserve.update_fiat_balance(1_000 * 10**18, caller="0xEvil")

    def test_update_fiat_balance_negative_reverts(self, reserve):
        with pytest.raises(ReserveError):
            reserve.update_fiat_balance(-1, caller=ORACLE)

    def test_last_oracle_update_is_set(self, reserve):
        assert reserve.last_oracle_update is None
        reserve.update_fiat_balance(100 * 10**18, caller=ORACLE)
        assert reserve.last_oracle_update is not None

    def test_set_oracle_by_admin(self, reserve):
        new_oracle = "0xNewOracle"
        reserve.set_oracle(new_oracle, caller=ADMIN)
        reserve.update_fiat_balance(1_000 * 10**18, caller=new_oracle)
        assert reserve.fiat_balance_idr == 1_000 * 10**18

    def test_set_oracle_non_admin_reverts(self, reserve):
        with pytest.raises(AccessControlError):
            reserve.set_oracle("0xNewOracle", caller="0xEvil")


# ─── Reserve Ratio & Collateralisation ────────────────────────────────────────

class TestReserveRatio:
    def test_fully_collateralised(self, reserve):
        supply = 1_000 * 10**18
        reserve.update_fiat_balance(supply, caller=ORACLE)   # exactly 1:1
        assert reserve.is_fully_collateralised(supply) is True
        assert reserve.reserve_ratio(supply) == pytest.approx(1.0)

    def test_over_collateralised(self, reserve):
        supply = 1_000 * 10**18
        reserve.update_fiat_balance(2_000 * 10**18, caller=ORACLE)  # 2:1
        assert reserve.is_fully_collateralised(supply) is True
        assert reserve.reserve_ratio(supply) == pytest.approx(2.0)

    def test_under_collateralised(self, reserve):
        supply = 2_000 * 10**18
        reserve.update_fiat_balance(1_000 * 10**18, caller=ORACLE)  # 0.5:1
        assert reserve.is_fully_collateralised(supply) is False
        assert reserve.reserve_ratio(supply) == pytest.approx(0.5)

    def test_zero_supply_returns_infinity(self, reserve):
        reserve.update_fiat_balance(1_000 * 10**18, caller=ORACLE)
        assert reserve.reserve_ratio(0) == float("inf")

    def test_check_collateralisation_raises_when_under(self, reserve):
        supply = 2_000 * 10**18
        reserve.update_fiat_balance(500 * 10**18, caller=ORACLE)
        with pytest.raises(ReserveError, match="under-collateralised"):
            reserve.check_collateralisation(supply)

    def test_check_collateralisation_passes_when_fully_backed(self, reserve):
        supply = 1_000 * 10**18
        reserve.update_fiat_balance(1_000 * 10**18, caller=ORACLE)
        reserve.check_collateralisation(supply)  # should not raise


# ─── Events ───────────────────────────────────────────────────────────────────

class TestReserveEvents:
    def test_audit_proof_event_logged(self, reserve):
        reserve.submit_audit_proof("hash1", 1_000 * 10**18, caller=ADMIN)
        assert len(reserve.events) == 1

    def test_oracle_update_event_logged(self, reserve):
        reserve.update_fiat_balance(500 * 10**18, caller=ORACLE)
        assert len(reserve.events) == 1
