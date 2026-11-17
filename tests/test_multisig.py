"""
tests/test_multisig.py
======================
Unit tests for MultisigWallet (Section 6.1 & 7.2).
Covers: propose, approve, execute, cancel, threshold enforcement,
        timelock, owner management.
"""

import pytest

from idrc.multisig import MultisigWallet, TxStatus
from idrc.token import IDRCToken

OWNERS = ["Alice", "Bob", "Carol", "Dave", "Eve"]
THRESHOLD = 3


@pytest.fixture
def ms():
    return MultisigWallet(owners=OWNERS, threshold=THRESHOLD, timelock_s=0)


@pytest.fixture
def ms_with_timelock():
    return MultisigWallet(owners=OWNERS, threshold=THRESHOLD, timelock_s=3600)


@pytest.fixture
def token_with_ms():
    """Token whose MINTER_ROLE is held by a multisig address."""
    multisig_addr = "multisig:0xMS"
    t = IDRCToken()
    t.initialize(
        name="IDR Coin",
        symbol="IDRC",
        admin="0xAdmin",
        minter=multisig_addr,
        pauser=multisig_addr,
        upgrader="0xUpgrader",
    )
    return t, multisig_addr


# ─── Construction Validation ─────────────────────────────────────────────────

class TestConstruction:
    def test_valid_construction(self):
        ms = MultisigWallet(["A", "B", "C"], threshold=2)
        assert ms.threshold == 2
        assert len(ms.owners) == 3

    def test_empty_owners_raises(self):
        with pytest.raises(ValueError, match="empty"):
            MultisigWallet([], threshold=1)

    def test_threshold_too_high_raises(self):
        with pytest.raises(ValueError, match="invalid"):
            MultisigWallet(["A", "B"], threshold=3)

    def test_threshold_zero_raises(self):
        with pytest.raises(ValueError, match="invalid"):
            MultisigWallet(["A"], threshold=0)


# ─── Propose ─────────────────────────────────────────────────────────────────

class TestPropose:
    def test_propose_creates_pending_tx(self, ms):
        tx_id = ms.propose("Test TX", caller="Alice")
        tx = ms.get_tx(tx_id)
        assert tx.status == TxStatus.PENDING
        assert tx.proposed_by == "Alice"

    def test_proposer_auto_approves(self, ms):
        tx_id = ms.propose("Test TX", caller="Alice")
        tx = ms.get_tx(tx_id)
        assert "Alice" in tx.approvals

    def test_non_owner_cannot_propose(self, ms):
        with pytest.raises(PermissionError):
            ms.propose("Evil TX", caller="Mallory")

    def test_multiple_proposals_get_unique_ids(self, ms):
        id1 = ms.propose("TX 1", caller="Alice")
        id2 = ms.propose("TX 2", caller="Bob")
        assert id1 != id2


# ─── Approve ─────────────────────────────────────────────────────────────────

class TestApprove:
    def test_approval_increments_count(self, ms):
        tx_id = ms.propose("TX", caller="Alice")
        ms.approve(tx_id, caller="Bob")
        tx = ms.get_tx(tx_id)
        assert len(tx.approvals) == 2

    def test_reaching_threshold_marks_approved(self, ms):
        tx_id = ms.propose("TX", caller="Alice")
        ms.approve(tx_id, caller="Bob")
        ms.approve(tx_id, caller="Carol")
        tx = ms.get_tx(tx_id)
        assert tx.status == TxStatus.APPROVED

    def test_non_owner_cannot_approve(self, ms):
        tx_id = ms.propose("TX", caller="Alice")
        with pytest.raises(PermissionError):
            ms.approve(tx_id, caller="Mallory")

    def test_duplicate_approval_is_idempotent(self, ms):
        tx_id = ms.propose("TX", caller="Alice")
        ms.approve(tx_id, caller="Bob")
        ms.approve(tx_id, caller="Bob")  # second approval from Bob
        assert len(ms.get_tx(tx_id).approvals) == 2  # still only 2 unique


# ─── Execute ─────────────────────────────────────────────────────────────────

class TestExecute:
    def test_execute_calls_fn(self, ms):
        results = []
        def fn(value, caller):
            return results.append(value)

        tx_id = ms.propose("Call fn", fn=fn, fn_kwargs={"value": 42, "caller": "ms"}, caller="Alice")
        ms.approve(tx_id, caller="Bob")
        ms.approve(tx_id, caller="Carol")
        ms.execute(tx_id, caller="Alice")

        assert results == [42]

    def test_execute_marks_tx_executed(self, ms):
        tx_id = ms.propose("TX", caller="Alice")
        ms.approve(tx_id, caller="Bob")
        ms.approve(tx_id, caller="Carol")
        ms.execute(tx_id, caller="Alice")
        assert ms.get_tx(tx_id).status == TxStatus.EXECUTED

    def test_execute_without_threshold_raises(self, ms):
        tx_id = ms.propose("TX", caller="Alice")
        ms.approve(tx_id, caller="Bob")
        # Only 2 approvals, threshold is 3
        with pytest.raises(ValueError, match="approvals"):
            ms.execute(tx_id, caller="Alice")

    def test_execute_twice_raises(self, ms):
        tx_id = ms.propose("TX", caller="Alice")
        ms.approve(tx_id, caller="Bob")
        ms.approve(tx_id, caller="Carol")
        ms.execute(tx_id, caller="Alice")
        with pytest.raises(ValueError, match="already executed"):
            ms.execute(tx_id, caller="Alice")

    def test_execute_with_real_token_mint(self, token_with_ms, ms):
        """End-to-end: multisig proposes + approves + executes a token mint."""
        token, ms_addr = token_with_ms

        tx_id = ms.propose(
            "Mint 1000 IDRC to 0xUser",
            fn=token.mint,
            fn_kwargs={"to": "0xUser", "amount": 1000, "caller": ms_addr},
            caller="Alice",
        )
        ms.approve(tx_id, caller="Bob")
        ms.approve(tx_id, caller="Carol")
        ms.execute(tx_id, caller="Alice")

        assert token.balance_of("0xUser") == 1000

    def test_non_owner_cannot_execute(self, ms):
        tx_id = ms.propose("TX", caller="Alice")
        ms.approve(tx_id, caller="Bob")
        ms.approve(tx_id, caller="Carol")
        with pytest.raises(PermissionError):
            ms.execute(tx_id, caller="Mallory")


# ─── Cancel ──────────────────────────────────────────────────────────────────

class TestCancel:
    def test_proposer_can_cancel(self, ms):
        tx_id = ms.propose("TX", caller="Alice")
        ms.cancel(tx_id, caller="Alice")
        assert ms.get_tx(tx_id).status == TxStatus.CANCELLED

    def test_non_proposer_cannot_cancel(self, ms):
        tx_id = ms.propose("TX", caller="Alice")
        with pytest.raises(ValueError, match="only proposer"):
            ms.cancel(tx_id, caller="Bob")

    def test_cancelled_tx_cannot_be_executed(self, ms):
        tx_id = ms.propose("TX", caller="Alice")
        ms.approve(tx_id, caller="Bob")
        ms.approve(tx_id, caller="Carol")
        ms.cancel(tx_id, caller="Alice")
        with pytest.raises(ValueError, match="cancelled"):
            ms.execute(tx_id, caller="Alice")


# ─── Timelock ────────────────────────────────────────────────────────────────

class TestTimelock:
    def test_execute_before_timelock_raises(self, ms_with_timelock):
        tx_id = ms_with_timelock.propose("TX", caller="Alice")
        ms_with_timelock.approve(tx_id, caller="Bob")
        ms_with_timelock.approve(tx_id, caller="Carol")
        with pytest.raises(ValueError, match="timelocked"):
            ms_with_timelock.execute(tx_id, caller="Alice")

    def test_execute_after_timelock_succeeds(self):
        """Use 0-second timelock to simulate elapsed timelock."""
        ms = MultisigWallet(OWNERS, threshold=THRESHOLD, timelock_s=0)
        tx_id = ms.propose("TX", caller="Alice")
        ms.approve(tx_id, caller="Bob")
        ms.approve(tx_id, caller="Carol")
        ms.execute(tx_id, caller="Alice")  # should not raise
        assert ms.get_tx(tx_id).status == TxStatus.EXECUTED


# ─── Owner Management ────────────────────────────────────────────────────────

class TestOwnerManagement:
    def test_add_owner(self, ms):
        ms.add_owner("Frank", caller="Alice")
        assert "Frank" in ms.owners

    def test_remove_owner(self, ms):
        ms.remove_owner("Eve", caller="Alice")
        assert "Eve" not in ms.owners

    def test_remove_owner_below_threshold_raises(self):
        ms = MultisigWallet(["A", "B", "C"], threshold=3)
        with pytest.raises(ValueError, match="threshold"):
            ms.remove_owner("A", caller="B")

    def test_non_owner_cannot_add_owner(self, ms):
        with pytest.raises(PermissionError):
            ms.add_owner("Mallory", caller="Mallory")


# ─── Event Log ───────────────────────────────────────────────────────────────

class TestMultisigEvents:
    def test_propose_approve_execute_emits_events(self, ms):
        tx_id = ms.propose("TX", caller="Alice")
        ms.approve(tx_id, caller="Bob")
        ms.approve(tx_id, caller="Carol")
        ms.execute(tx_id, caller="Dave")

        kinds = [e.kind for e in ms.events]
        assert "PROPOSED" in kinds
        assert "APPROVED" in kinds
        assert "EXECUTED" in kinds
