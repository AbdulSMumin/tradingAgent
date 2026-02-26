"""Tests for dashboard.py — DashboardAgent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dashboard import DashboardAgent
from rich.layout import Layout
from trading_agent import PriceTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_config(mode="notify", watchlist=None):
    cfg = MagicMock()
    cfg.trading212_api_key = "key"
    cfg.trading212_env = "demo"
    cfg.trading212_base_url.return_value = "https://demo.trading212.com/api/v0"
    cfg.agent_mode = mode
    cfg.watchlist = watchlist or ["AAPL"]
    cfg.monitor_interval = 60
    cfg.musaffa_api_key = ""
    cfg.discord_webhook_url = "https://discord.com/api/webhooks/123/abc"
    cfg.buy_signal_threshold = 2.0
    cfg.sell_signal_threshold = 3.0
    cfg.max_position_size = 0.1
    cfg.validate = MagicMock()
    return cfg


@pytest.fixture
def agent():
    cfg = _make_mock_config()
    with (
        patch("trading_agent.Trading212Client"),
        patch("trading_agent.ShariaScreener"),
        patch("trading_agent.DiscordNotifier"),
    ):
        return DashboardAgent(config=cfg)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_dashboard_agent_initialises(agent):
    assert agent._tick_count == 0
    assert agent._available_cash == 0.0
    assert len(agent._dash_log) == 0
    assert agent._ticker_rows == {}
    assert agent._last_tick_time == "—"
    assert agent._next_tick_in == 0


# ---------------------------------------------------------------------------
# _add_log
# ---------------------------------------------------------------------------

def test_add_log_appends_entry(agent):
    agent._add_log("Test message")
    assert len(agent._dash_log) == 1
    assert "Test message" in agent._dash_log[0]


def test_add_log_prepends_timestamp(agent):
    agent._add_log("Hello")
    entry = agent._dash_log[0]
    # Entry should look like "[HH:MM:SS] Hello"
    assert entry.startswith("[")
    assert "Hello" in entry


def test_add_log_most_recent_first(agent):
    agent._add_log("first")
    agent._add_log("second")
    # deque uses appendleft so index 0 is most recent
    assert "second" in agent._dash_log[0]
    assert "first" in agent._dash_log[1]


def test_add_log_respects_max_size(agent):
    for i in range(agent._MAX_LOG_LINES + 5):
        agent._add_log(f"msg {i}")
    assert len(agent._dash_log) == agent._MAX_LOG_LINES


# ---------------------------------------------------------------------------
# _process_ticker
# ---------------------------------------------------------------------------

def test_process_ticker_missing_instrument_marks_unknown(agent):
    agent._instruments = {}
    agent._process_ticker("AAPL", 1000.0)
    assert agent._ticker_rows["AAPL"]["halal"] is None


def test_process_ticker_non_compliant_marks_false(agent):
    agent._instruments = {"AAPL": {"ticker": "AAPL", "sector": "banking"}}
    agent._screener.is_compliant.return_value = False
    agent._process_ticker("AAPL", 1000.0)
    row = agent._ticker_rows["AAPL"]
    assert row["halal"] is False
    assert row["price"] is None


def test_process_ticker_no_valid_price(agent):
    agent._instruments = {"AAPL": {"ticker": "AAPL"}}  # no price keys
    agent._screener.is_compliant.return_value = True
    agent._process_ticker("AAPL", 1000.0)
    row = agent._ticker_rows["AAPL"]
    assert row["halal"] is True
    assert row["price"] is None


def test_process_ticker_hold_signal_populates_row(agent):
    agent._instruments = {"AAPL": {"ticker": "AAPL", "currentPrice": 100.0}}
    agent._screener.is_compliant.return_value = True
    # Seed tracker with one price so there is not yet enough data for a signal
    tracker = PriceTracker(ticker="AAPL")
    tracker.update(100.0)
    agent._trackers["AAPL"] = tracker

    agent._process_ticker("AAPL", 1500.0)

    row = agent._ticker_rows["AAPL"]
    assert row["halal"] is True
    assert row["price"] == 100.0
    assert row["signal"] == "HOLD"
    assert agent._available_cash == 1500.0


def test_process_ticker_buy_signal_logs_activity(agent):
    agent._config.agent_mode = "notify"
    agent._instruments = {"AAPL": {"ticker": "AAPL", "currentPrice": 97.0}}
    agent._screener.is_compliant.return_value = True
    # High = 100, current price = 97 → 3% drop → BUY (threshold is 2%)
    tracker = PriceTracker(ticker="AAPL")
    tracker.update(100.0)
    agent._trackers["AAPL"] = tracker

    agent._process_ticker("AAPL", 1000.0)

    row = agent._ticker_rows["AAPL"]
    assert row["signal"] == "BUY"
    assert any("BUY" in entry for entry in agent._dash_log)


def test_process_ticker_sell_signal_logs_activity(agent):
    agent._config.agent_mode = "notify"
    agent._instruments = {"AAPL": {"ticker": "AAPL", "currentPrice": 94.0}}
    agent._screener.is_compliant.return_value = True
    # Low = 90, current = 94 → rise of ~4.4% > 3% threshold → SELL
    tracker = PriceTracker(ticker="AAPL")
    tracker.update(90.0)
    agent._trackers["AAPL"] = tracker

    agent._process_ticker("AAPL", 1000.0)

    row = agent._ticker_rows["AAPL"]
    assert row["signal"] == "SELL"
    assert any("SELL" in entry for entry in agent._dash_log)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def test_render_returns_layout(agent):
    layout = agent._render()
    assert isinstance(layout, Layout)


def test_render_with_no_ticker_rows(agent):
    """_render() must not raise when no rows are populated yet."""
    layout = agent._render()
    assert layout is not None


def test_render_with_populated_ticker_rows(agent):
    agent._ticker_rows["AAPL"] = {
        "halal": True,
        "price": 150.0,
        "high": 155.0,
        "low": 145.0,
        "pct_high": -3.23,
        "signal": "BUY",
    }
    agent._available_cash = 2500.0
    agent._tick_count = 3
    layout = agent._render()
    assert layout is not None


def test_render_with_non_compliant_ticker(agent):
    agent._ticker_rows["AAPL"] = {"halal": False, "price": None, "signal": "—"}
    layout = agent._render()
    assert layout is not None


def test_render_with_unknown_halal_status(agent):
    agent._ticker_rows["AAPL"] = {"halal": None, "price": None, "signal": "?"}
    layout = agent._render()
    assert layout is not None


def test_render_sell_signal(agent):
    agent._ticker_rows["AAPL"] = {
        "halal": True,
        "price": 94.0,
        "high": 94.0,
        "low": 90.0,
        "pct_high": 0.0,
        "signal": "SELL",
    }
    layout = agent._render()
    assert layout is not None


def test_render_log_panel_shows_placeholder_when_empty(agent):
    panel = agent._build_log_panel()
    assert "No activity yet" in panel.renderable


def test_render_log_panel_shows_entries(agent):
    agent._add_log("Something happened")
    panel = agent._build_log_panel()
    assert "Something happened" in panel.renderable


def test_multiple_tickers_rendered(agent):
    agent._config.watchlist = ["AAPL", "MSFT", "AMZN"]
    agent._ticker_rows = {
        "AAPL": {"halal": True, "price": 150.0, "high": 155.0, "low": 145.0,
                 "pct_high": -3.2, "signal": "BUY"},
        "MSFT": {"halal": True, "price": 380.0, "high": 385.0, "low": 370.0,
                 "pct_high": -1.3, "signal": "HOLD"},
        # AMZN has no row yet — should render as "waiting"
    }
    layout = agent._render()
    assert layout is not None
