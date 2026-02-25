"""
Halal Trading Agent — main orchestrator.

Monitors a watchlist of sharia-compliant stocks using the Trading 212 API.
For each tick it:
  1. Fetches the latest instrument data / current price.
  2. Checks sharia compliance.
  3. Applies a momentum-based signal strategy.
  4. Either executes trades automatically, sends a Discord notification, or both,
     depending on AGENT_MODE.

Usage
-----
    python trading_agent.py
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Literal

from config import Config
from discord_notifier import DiscordNotifier
from sharia_screener import ShariaScreener
from trading212_client import Trading212Client, Trading212Error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Precision divisor for rounding order quantities to 4 decimal places
_QUANTITY_PRECISION = 10_000

Signal = Literal["BUY", "SELL", "HOLD"]


# ---------------------------------------------------------------------------
# Price tracker
# ---------------------------------------------------------------------------

@dataclass
class PriceTracker:
    """Keeps a rolling window of recent prices for a single ticker."""

    ticker: str
    window_size: int = 20
    _prices: list[float] = field(default_factory=list, init=False, repr=False)

    def update(self, price: float) -> None:
        self._prices.append(price)
        if len(self._prices) > self.window_size:
            self._prices.pop(0)

    @property
    def current_price(self) -> float | None:
        return self._prices[-1] if self._prices else None

    @property
    def recent_high(self) -> float | None:
        return max(self._prices) if self._prices else None

    @property
    def recent_low(self) -> float | None:
        return min(self._prices) if self._prices else None

    def pct_from_high(self) -> float | None:
        """Percentage drop from recent high (negative means below high)."""
        if self.recent_high and self.current_price:
            return (self.current_price - self.recent_high) / self.recent_high * 100
        return None

    def pct_from_low(self) -> float | None:
        """Percentage rise from recent low (positive means above low)."""
        if self.recent_low and self.current_price:
            return (self.current_price - self.recent_low) / self.recent_low * 100
        return None

    def has_enough_data(self, min_points: int = 2) -> bool:
        return len(self._prices) >= min_points


# ---------------------------------------------------------------------------
# Signal generator
# ---------------------------------------------------------------------------

class SignalGenerator:
    """Generate BUY / SELL / HOLD signals from price history."""

    def __init__(
        self,
        buy_threshold: float = 2.0,
        sell_threshold: float = 3.0,
    ) -> None:
        self._buy_threshold = buy_threshold
        self._sell_threshold = sell_threshold

    def evaluate(self, tracker: PriceTracker) -> Signal:
        """Return a signal based on the tracker's price history."""
        if not tracker.has_enough_data():
            return "HOLD"

        pct_high = tracker.pct_from_high()
        pct_low = tracker.pct_from_low()

        if pct_high is not None and pct_high <= -self._buy_threshold:
            return "BUY"
        if pct_low is not None and pct_low >= self._sell_threshold:
            return "SELL"
        return "HOLD"


# ---------------------------------------------------------------------------
# Trading Agent
# ---------------------------------------------------------------------------

class TradingAgent:
    """Orchestrates monitoring, screening, signal generation and execution."""

    def __init__(self, config: type[Config] = Config) -> None:
        config.validate()
        self._config = config

        self._client = Trading212Client(
            api_key=config.trading212_api_key,
            base_url=config.trading212_base_url(),
        )
        self._screener = ShariaScreener(musaffa_api_key=config.musaffa_api_key)
        self._notifier = (
            DiscordNotifier(config.discord_webhook_url)
            if config.agent_mode in {"notify", "both"}
            else None
        )
        self._signal_gen = SignalGenerator(
            buy_threshold=config.buy_signal_threshold,
            sell_threshold=config.sell_signal_threshold,
        )

        # ticker -> PriceTracker
        self._trackers: dict[str, PriceTracker] = {}
        # Instrument metadata cache (ticker -> instrument dict)
        self._instruments: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the monitoring loop (blocks indefinitely)."""
        logger.info(
            "Starting Halal Trading Agent — mode=%s, env=%s, watchlist=%s",
            self._config.agent_mode,
            self._config.trading212_env,
            self._config.watchlist,
        )
        self._notify_info("🚀 Halal Trading Agent started.")
        self._refresh_instruments()

        try:
            while True:
                self._tick()
                time.sleep(self._config.monitor_interval)
        except KeyboardInterrupt:
            logger.info("Agent stopped by user.")
            self._notify_info("🛑 Halal Trading Agent stopped.")

    def _tick(self) -> None:
        """One monitoring cycle."""
        try:
            cash_info = self._client.get_account_cash()
            available_cash = float(cash_info.get("free", 0))
        except Trading212Error as exc:
            logger.error("Failed to fetch account cash: %s", exc)
            self._notify_error(f"Failed to fetch account cash: {exc}")
            return

        for ticker in self._config.watchlist:
            try:
                self._process_ticker(ticker, available_cash)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error processing %s: %s", ticker, exc)
                self._notify_error(f"Error processing {ticker}: {exc}")

    # ------------------------------------------------------------------
    # Per-ticker processing
    # ------------------------------------------------------------------

    def _process_ticker(self, ticker: str, available_cash: float) -> None:
        instrument = self._instruments.get(ticker)
        if instrument is None:
            logger.warning("Instrument not found for ticker %s — skipping.", ticker)
            return

        # Sharia compliance check
        if not self._screener.is_compliant(ticker, instrument):
            logger.debug("%s is not sharia-compliant — skipping.", ticker)
            return

        # Fetch current price
        price = self._get_current_price(ticker, instrument)
        if price is None or price <= 0:
            logger.debug("No valid price for %s.", ticker)
            return

        # Update price tracker
        tracker = self._trackers.setdefault(ticker, PriceTracker(ticker=ticker))
        tracker.update(price)

        # Generate signal
        signal = self._signal_gen.evaluate(tracker)
        if signal == "HOLD":
            logger.debug("%s: HOLD (price=%.4f)", ticker, price)
            return

        logger.info("%s: %s signal at %.4f", ticker, signal, price)

        quantity = None
        executed = False

        if self._config.agent_mode in {"auto", "both"}:
            quantity, executed = self._execute_trade(
                ticker, signal, price, available_cash
            )

        if self._config.agent_mode in {"notify", "both"}:
            self._notify_signal(signal, ticker, price, tracker, quantity, executed)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _execute_trade(
        self, ticker: str, signal: Signal, price: float, available_cash: float
    ) -> tuple[float | None, bool]:
        """Place a market order and return (quantity, success)."""
        try:
            if signal == "BUY":
                max_spend = available_cash * self._config.max_position_size
                quantity = math.floor((max_spend / price) * _QUANTITY_PRECISION) / _QUANTITY_PRECISION
                if quantity <= 0:
                    logger.warning(
                        "Insufficient cash to buy %s (available=%.2f)", ticker, available_cash
                    )
                    return None, False
            else:  # SELL
                position = self._client.get_position(ticker)
                if position is None:
                    logger.info("No position in %s to sell.", ticker)
                    return None, False
                quantity = float(position.get("quantity", 0))
                if quantity <= 0:
                    return None, False
                quantity = -quantity  # negative = sell

            order_quantity = abs(quantity)
            self._client.place_market_order(
                ticker=ticker,
                quantity=quantity,
            )
            logger.info("Order placed: %s %s x %.4f", signal, ticker, order_quantity)
            return order_quantity, True

        except Trading212Error as exc:
            logger.error("Trade execution failed for %s: %s", ticker, exc)
            self._notify_error(f"Trade execution failed for {ticker}: {exc}")
            return None, False

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def _notify_signal(
        self,
        signal: Signal,
        ticker: str,
        price: float,
        tracker: PriceTracker,
        quantity: float | None,
        executed: bool,
    ) -> None:
        if self._notifier is None:
            return
        pct_high = tracker.pct_from_high()
        pct_low = tracker.pct_from_low()
        if signal == "BUY" and pct_high is not None:
            reason = f"Price is {abs(pct_high):.2f}% below recent high."
        elif signal == "SELL" and pct_low is not None:
            reason = f"Price is {pct_low:.2f}% above recent low."
        else:
            reason = ""
        try:
            self._notifier.send_signal(
                signal=signal,
                ticker=ticker,
                price=price,
                reason=reason,
                quantity=quantity,
                executed=executed,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Discord notification failed: %s", exc)

    def _notify_info(self, message: str) -> None:
        if self._notifier:
            try:
                self._notifier.send_info(message)
            except Exception as exc:  # noqa: BLE001
                logger.error("Discord info notification failed: %s", exc)

    def _notify_error(self, message: str) -> None:
        if self._notifier:
            try:
                self._notifier.send_error(message)
            except Exception as exc:  # noqa: BLE001
                logger.error("Discord error notification failed: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_instruments(self) -> None:
        """Populate the instruments cache from Trading 212."""
        try:
            instruments = self._client.get_instruments()
            for inst in instruments:
                ticker = inst.get("ticker", "").upper()
                if ticker:
                    self._instruments[ticker] = inst
            logger.info("Loaded %d instruments.", len(self._instruments))
        except Trading212Error as exc:
            logger.error("Failed to load instruments: %s", exc)

    @staticmethod
    def _get_current_price(ticker: str, instrument: dict) -> float | None:
        """Extract the current price from instrument metadata.

        Trading 212 returns 'currentPrice' or 'lastTraded' depending on market hours.
        """
        for key in ("currentPrice", "lastTraded", "askPrice", "bidPrice"):
            val = instrument.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    agent = TradingAgent()
    agent.run()
