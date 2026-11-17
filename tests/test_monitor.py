"""
tests/test_monitor.py
=====================
Unit tests for IDRCMonitor (Section 9.1).
Covers: event indexing, statistics, alert rules, and CSV export.
"""

import pytest

from idrc.monitor import IDRCMonitor
from idrc.proxy import UUPSProxy
from idrc.reserve import IDRCReserve
from idrc.token import IDRCToken

ADMIN    = "0xAdmin"
MINTER   = "0xMinter"
PAUSER   = "0xPauser"
UPGRADER = "0xUpgrader"
ORACLE   = "0xOracle"


@pytest.fixture
def token():
    impl = IDRCToken()
    proxy = UUPSProxy(impl)
    t = proxy.as_token()
    t.initialize(
        name="IDR Coin", symbol="IDRC",
        admin=ADMIN, minter=MINTER, pauser=PAUSER, upgrader=UPGRADER,
    )
    return t


@pytest.fixture
def reserve():
    return IDRCReserve(admin=ADMIN, oracle=ORACLE)


@pytest.fixture
def monitor(token, reserve):
    return IDRCMonitor(token, reserve)


# ─── Sync & Basic Stats ───────────────────────────────────────────────────────

class TestMonitorSync:
    def test_sync_with_no_events(self, monitor):
        monitor.sync()
        assert monitor.total_minted() == 0
        assert monitor.total_burned() == 0
        assert monitor.current_supply() == 0
        assert monitor.holder_count() == 0

    def test_sync_after_mint(self, token, monitor):
        token.mint("0xAlice", 1_000 * 10**18, caller=MINTER)
        monitor.sync()
        assert monitor.total_minted() == 1_000 * 10**18
        assert monitor.current_supply() == 1_000 * 10**18
        assert monitor.holder_count() == 1

    def test_sync_after_mint_and_burn(self, token, monitor):
        token.mint("0xAlice", 1_000 * 10**18, caller=MINTER)
        token.burn(400 * 10**18, caller="0xAlice")
        monitor.sync()
        assert monitor.total_minted() == 1_000 * 10**18
        assert monitor.total_burned() == 400 * 10**18
        assert monitor.current_supply() == 600 * 10**18

    def test_transfer_summary(self, token, monitor):
        token.mint("0xAlice", 1_000 * 10**18, caller=MINTER)
        token.transfer("0xBob", 200 * 10**18, caller="0xAlice")
        token.transfer("0xCarol", 300 * 10**18, caller="0xAlice")
        monitor.sync()
        summary = monitor.transfer_summary()
        assert summary.total_transfers == 2
        assert summary.total_volume == 500 * 10**18
        assert summary.largest_transfer == 300 * 10**18

    def test_top_holders(self, token, monitor):
        token.mint("0xRich",  10_000 * 10**18, caller=MINTER)
        token.mint("0xMid",    5_000 * 10**18, caller=MINTER)
        token.mint("0xPoor",   1_000 * 10**18, caller=MINTER)
        monitor.sync()
        top = monitor.top_holders(2)
        assert top[0][0] == "0xRich"
        assert top[1][0] == "0xMid"


# ─── Alert Rules ─────────────────────────────────────────────────────────────

class TestAlertRules:
    def test_no_alerts_normal_operation(self, token, monitor, reserve):
        token.mint("0xUser", 1_000 * 10**18, caller=MINTER)
        reserve.update_fiat_balance(1_000 * 10**18, caller=ORACLE)
        monitor.sync()
        alerts = monitor.run_alert_checks()
        # No CRITICAL or WARNING expected
        serious = [a for a in alerts if a.level in ("CRITICAL", "WARNING")]
        assert not serious

    def test_large_mint_triggers_warning(self, token, monitor):
        # Mint over LARGE_MINT_THRESHOLD (100M IDRC)
        amount = IDRCMonitor.LARGE_MINT_THRESHOLD + 1
        token.mint("0xWhale", amount, caller=MINTER)
        monitor.sync()
        alerts = monitor.run_alert_checks()
        codes = [a.code for a in alerts]
        assert "LARGE_MINT" in codes

    def test_oracle_never_updated_triggers_warning(self, token, monitor):
        monitor.sync()
        alerts = monitor.run_alert_checks()
        codes = [a.code for a in alerts]
        assert "ORACLE_NEVER_UPDATED" in codes

    def test_under_collateralisation_triggers_critical(self, token, monitor, reserve):
        token.mint("0xUser", 2_000 * 10**18, caller=MINTER)
        reserve.update_fiat_balance(500 * 10**18, caller=ORACLE)   # only 25%
        monitor.sync()
        alerts = monitor.run_alert_checks()
        codes = [a.code for a in alerts]
        assert "UNDER_COLLATERALISED" in codes
        assert any(a.level == "CRITICAL" for a in alerts if a.code == "UNDER_COLLATERALISED")

    def test_blacklist_event_generates_info_alert(self, token, monitor):
        token.blacklist("0xBadActor", caller=ADMIN)
        monitor.sync()
        alerts = monitor.run_alert_checks()
        codes = [a.code for a in alerts]
        assert "BLACKLIST_ACTION" in codes


# ─── CSV Export ───────────────────────────────────────────────────────────────

class TestCSVExport:
    def test_export_returns_all_event_types(self, token, monitor):
        token.mint("0xAlice", 1_000 * 10**18, caller=MINTER)
        token.transfer("0xBob", 200 * 10**18, caller="0xAlice")
        token.burn(100 * 10**18, caller="0xAlice")
        monitor.sync()

        rows = monitor.export_csv_rows()
        types = {r["type"] for r in rows}
        assert "MINT" in types
        assert "BURN" in types
        assert "TRANSFER" in types

    def test_export_amounts_in_idrc(self, token, monitor):
        amount = 500 * 10**18
        token.mint("0xAlice", amount, caller=MINTER)
        monitor.sync()
        rows = [r for r in monitor.export_csv_rows() if r["type"] == "MINT"]
        assert rows[0]["amount_idrc"] == pytest.approx(500.0)

    def test_print_dashboard_does_not_raise(self, token, monitor, reserve):
        token.mint("0xAlice", 1_000 * 10**18, caller=MINTER)
        reserve.update_fiat_balance(1_000 * 10**18, caller=ORACLE)
        monitor.sync()
        monitor.print_dashboard()  # should not raise
