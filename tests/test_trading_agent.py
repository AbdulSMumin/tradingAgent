"""Tests for trading_agent.py — PriceTracker, SignalGenerator, and TradingAgent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from trading_agent import PriceTracker, SignalGenerator, TradingAgent


# ---------------------------------------------------------------------------
# PriceTracker
# ---------------------------------------------------------------------------

class TestPriceTracker:
    def test_initial_state(self):
        t = PriceTracker(ticker="AAPL")
        assert t.current_price is None
        assert t.recent_high is None
        assert t.recent_low is None
        assert not t.has_enough_data()

    def test_single_update(self):
        t = PriceTracker(ticker="AAPL")
        t.update(100.0)
        assert t.current_price == 100.0
        assert t.recent_high == 100.0
        assert t.recent_low == 100.0

    def test_multiple_updates_high_low(self):
        t = PriceTracker(ticker="AAPL")
        for price in [100.0, 105.0, 95.0, 102.0]:
            t.update(price)
        assert t.current_price == 102.0
        assert t.recent_high == 105.0
        assert t.recent_low == 95.0

    def test_window_size_respected(self):
        t = PriceTracker(ticker="AAPL", window_size=3)
        for price in [100.0, 110.0, 90.0, 120.0]:
            t.update(price)
        # Window should only contain last 3: [110, 90, 120]
        assert t.recent_high == 120.0
        assert t.recent_low == 90.0
        assert t.current_price == 120.0

    def test_pct_from_high(self):
        t = PriceTracker(ticker="AAPL")
        t.update(100.0)
        t.update(90.0)
        pct = t.pct_from_high()
        assert pct == pytest.approx(-10.0)

    def test_pct_from_low(self):
        t = PriceTracker(ticker="AAPL")
        t.update(80.0)
        t.update(100.0)
        pct = t.pct_from_low()
        assert pct == pytest.approx(25.0)

    def test_has_enough_data_min_two(self):
        t = PriceTracker(ticker="AAPL")
        t.update(100.0)
        assert not t.has_enough_data(2)
        t.update(101.0)
        assert t.has_enough_data(2)


# ---------------------------------------------------------------------------
# SignalGenerator
# ---------------------------------------------------------------------------

class TestSignalGenerator:
    def setup_method(self):
        self.gen = SignalGenerator(buy_threshold=2.0, sell_threshold=3.0)

    def _tracker_with_prices(self, prices):
        t = PriceTracker(ticker="TEST")
        for p in prices:
            t.update(p)
        return t

    def test_hold_insufficient_data(self):
        t = PriceTracker(ticker="TEST")
        t.update(100.0)
        assert self.gen.evaluate(t) == "HOLD"

    def test_buy_signal_on_drop(self):
        # High = 100, current = 97 → drop of 3% > threshold 2%
        t = self._tracker_with_prices([100.0, 97.0])
        assert self.gen.evaluate(t) == "BUY"

    def test_sell_signal_on_rise(self):
        # Low = 90, current = 94 → rise of ~4.4% > threshold 3%
        t = self._tracker_with_prices([90.0, 94.0])
        assert self.gen.evaluate(t) == "SELL"

    def test_hold_when_within_thresholds(self):
        # Drop 1% below high — below buy threshold
        t = self._tracker_with_prices([100.0, 99.0])
        assert self.gen.evaluate(t) == "HOLD"

    def test_buy_signal_exact_threshold(self):
        # Exactly 2% drop
        t = self._tracker_with_prices([100.0, 98.0])
        assert self.gen.evaluate(t) == "BUY"


# ---------------------------------------------------------------------------
# TradingAgent
# ---------------------------------------------------------------------------

def _make_mock_config(
    mode="notify",
    watchlist=None,
    buy_threshold=2.0,
    sell_threshold=3.0,
    max_position=0.1,
):
    cfg = MagicMock()
    cfg.trading212_api_key = "key"
    cfg.trading212_env = "demo"
    cfg.trading212_base_url.return_value = "https://demo.trading212.com/api/v0"
    cfg.agent_mode = mode
    cfg.watchlist = watchlist or ["AAPL"]
    cfg.monitor_interval = 60
    cfg.musaffa_api_key = ""
    cfg.discord_webhook_url = "https://discord.com/api/webhooks/123/abc"
    cfg.buy_signal_threshold = buy_threshold
    cfg.sell_signal_threshold = sell_threshold
    cfg.max_position_size = max_position
    cfg.validate = MagicMock()
    return cfg


@pytest.fixture
def mock_config():
    return _make_mock_config()


def test_agent_initialises_without_error(mock_config):
    with (
        patch("trading_agent.Trading212Client"),
        patch("trading_agent.ShariaScreener"),
        patch("trading_agent.DiscordNotifier"),
    ):
        agent = TradingAgent(config=mock_config)
        assert agent is not None


def test_agent_auto_mode_no_notifier(mock_config):
    mock_config.agent_mode = "auto"
    with (
        patch("trading_agent.Trading212Client"),
        patch("trading_agent.ShariaScreener"),
        patch("trading_agent.DiscordNotifier") as mock_discord,
    ):
        TradingAgent(config=mock_config)
        mock_discord.assert_not_called()


def test_agent_notify_mode_creates_notifier(mock_config):
    mock_config.agent_mode = "notify"
    with (
        patch("trading_agent.Trading212Client"),
        patch("trading_agent.ShariaScreener"),
        patch("trading_agent.DiscordNotifier") as mock_discord,
    ):
        TradingAgent(config=mock_config)
        mock_discord.assert_called_once()


def test_agent_skips_non_compliant_ticker(mock_config):
    with (
        patch("trading_agent.Trading212Client") as mock_client_cls,
        patch("trading_agent.ShariaScreener") as mock_screener_cls,
        patch("trading_agent.DiscordNotifier"),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.get_instruments.return_value = [
            {"ticker": "AAPL", "name": "Apple", "sector": "Banks"}
        ]
        mock_client.get_account_cash.return_value = {"free": 1000.0}

        mock_screener = mock_screener_cls.return_value
        mock_screener.is_compliant.return_value = False

        agent = TradingAgent(config=mock_config)
        agent._instruments = {"AAPL": {"ticker": "AAPL", "name": "Apple", "sector": "Banks"}}
        agent._tick()

        mock_client.place_market_order.assert_not_called()


def test_agent_buy_signal_notify_only(mock_config):
    mock_config.agent_mode = "notify"
    with (
        patch("trading_agent.Trading212Client") as mock_client_cls,
        patch("trading_agent.ShariaScreener") as mock_screener_cls,
        patch("trading_agent.DiscordNotifier") as mock_discord_cls,
    ):
        mock_client = mock_client_cls.return_value
        mock_client.get_account_cash.return_value = {"free": 1000.0}

        mock_screener = mock_screener_cls.return_value
        mock_screener.is_compliant.return_value = True

        mock_notifier = mock_discord_cls.return_value

        # Apple tech instrument with a price
        aapl = {"ticker": "AAPL", "name": "Apple", "sector": "Technology", "currentPrice": 97.0}
        agent = TradingAgent(config=mock_config)
        agent._instruments = {"AAPL": aapl}

        # Seed tracker so a BUY signal is generated
        # High = 100, then price drops to 97 → 3% drop > 2% threshold
        tracker = PriceTracker(ticker="AAPL")
        tracker.update(100.0)
        agent._trackers["AAPL"] = tracker

        agent._tick()

        # In notify mode, no order should be placed but Discord should be notified
        mock_client.place_market_order.assert_not_called()
        mock_notifier.send_signal.assert_called_once()
        args = mock_notifier.send_signal.call_args
        assert args.kwargs["signal"] == "BUY"


def test_agent_handles_missing_instrument(mock_config):
    with (
        patch("trading_agent.Trading212Client") as mock_client_cls,
        patch("trading_agent.ShariaScreener"),
        patch("trading_agent.DiscordNotifier"),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.get_account_cash.return_value = {"free": 1000.0}

        agent = TradingAgent(config=mock_config)
        agent._instruments = {}  # No instruments loaded
        agent._tick()  # Should not raise

        mock_client.place_market_order.assert_not_called()


def test_get_current_price_extracts_current_price():
    instrument = {"currentPrice": 150.5}
    price = TradingAgent._get_current_price("AAPL", instrument)
    assert price == 150.5


def test_get_current_price_falls_back_to_last_traded():
    instrument = {"lastTraded": 148.0}
    price = TradingAgent._get_current_price("AAPL", instrument)
    assert price == 148.0


def test_get_current_price_returns_none_if_no_price():
    price = TradingAgent._get_current_price("AAPL", {})
    assert price is None
