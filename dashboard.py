"""
Rich terminal dashboard for the Halal Trading Agent.

Provides a live-updating terminal UI showing:
  - Agent status (mode, environment, available cash, tick timing)
  - Per-ticker watchlist table (halal status, price, rolling high/low,
    % from recent high, last signal)
  - Scrolling activity log

Usage
-----
    python dashboard.py
"""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime, timezone

from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from config import Config
from trading_agent import PriceTracker, TradingAgent
from trading212_client import Trading212Error

logger = logging.getLogger(__name__)


class DashboardAgent(TradingAgent):
    """TradingAgent subclass that renders a live Rich terminal dashboard."""

    _MAX_LOG_LINES = 20

    def __init__(self, config: type[Config] = Config) -> None:
        # Initialise dashboard state before calling super so the attributes
        # exist if any parent __init__ code triggers a log.
        self._dash_log: deque[str] = deque(maxlen=self._MAX_LOG_LINES)
        self._ticker_rows: dict[str, dict] = {}
        self._available_cash: float = 0.0
        self._tick_count: int = 0
        self._last_tick_time: str = "—"
        self._next_tick_in: int = 0
        super().__init__(config)

    # ------------------------------------------------------------------
    # Dashboard helpers
    # ------------------------------------------------------------------

    def _add_log(self, message: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._dash_log.appendleft(f"[{ts}] {message}")

    # ------------------------------------------------------------------
    # Lifecycle — override to wrap in Live display
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the agent with a live terminal dashboard."""
        with Live(self._render(), refresh_per_second=2, screen=True) as live:
            self._add_log("🚀 Halal Trading Agent started.")
            self._notify_info("🚀 Halal Trading Agent started.")
            self._refresh_instruments()
            try:
                while True:
                    self._tick()
                    self._tick_count += 1
                    self._last_tick_time = datetime.now(timezone.utc).strftime(
                        "%H:%M:%S UTC"
                    )
                    self._add_log(
                        f"✔ Tick #{self._tick_count} — "
                        f"{len(self._config.watchlist)} tickers checked"
                    )
                    live.update(self._render())

                    # Sleep in 0.5 s increments so the countdown refreshes
                    remaining = float(self._config.monitor_interval)
                    while remaining > 0:
                        self._next_tick_in = max(0, int(remaining))
                        live.update(self._render())
                        sleep_time = min(0.5, remaining)
                        time.sleep(sleep_time)
                        remaining -= sleep_time
            except KeyboardInterrupt:
                self._add_log("🛑 Stopped by user.")
                live.update(self._render())
                self._notify_info("🛑 Halal Trading Agent stopped.")

    # ------------------------------------------------------------------
    # Per-ticker override — capture state for the display
    # ------------------------------------------------------------------

    def _process_ticker(self, ticker: str, available_cash: float) -> None:
        # Capture cash for the header display
        self._available_cash = available_cash

        instrument = self._instruments.get(ticker)
        if instrument is None:
            self._ticker_rows[ticker] = {"halal": None, "price": None, "signal": "?"}
            logger.warning("Instrument not found for ticker %s — skipping.", ticker)
            return

        halal = self._screener.is_compliant(ticker, instrument)
        row: dict = {"halal": halal}

        if not halal:
            row.update({"price": None, "signal": "—"})
            self._ticker_rows[ticker] = row
            logger.debug("%s is not sharia-compliant — skipping.", ticker)
            return

        price = self._get_current_price(ticker, instrument)
        if price is None or price <= 0:
            row.update({"price": None, "signal": "—"})
            self._ticker_rows[ticker] = row
            logger.debug("No valid price for %s.", ticker)
            return

        tracker = self._trackers.setdefault(ticker, PriceTracker(ticker=ticker))
        tracker.update(price)
        signal = self._signal_gen.evaluate(tracker)

        row.update(
            {
                "price": price,
                "high": tracker.recent_high,
                "low": tracker.recent_low,
                "pct_high": tracker.pct_from_high(),
                "signal": signal,
            }
        )
        self._ticker_rows[ticker] = row

        if signal == "HOLD":
            logger.debug("%s: HOLD (price=%.4f)", ticker, price)
            return

        logger.info("%s: %s signal at %.4f", ticker, signal, price)
        self._add_log(
            f"{'🟢' if signal == 'BUY' else '🔴'} {ticker}: {signal} @ ${price:,.4f}"
        )

        quantity = None
        executed = False
        if self._config.agent_mode in {"auto", "both"}:
            quantity, executed = self._execute_trade(ticker, signal, price, available_cash)
            if executed:
                self._add_log(
                    f"✅ Trade placed: {signal} {ticker} × {quantity:.4f}"
                )
        if self._config.agent_mode in {"notify", "both"}:
            self._notify_signal(signal, ticker, price, tracker, quantity, executed)

    # ------------------------------------------------------------------
    # Rich rendering
    # ------------------------------------------------------------------

    def _render(self) -> Layout:
        """Build the full dashboard layout."""
        layout = Layout()
        layout.split_column(
            Layout(self._build_header(), name="header", size=4),
            Layout(self._build_watchlist_table(), name="watchlist"),
            Layout(
                self._build_log_panel(),
                name="log",
                size=min(self._MAX_LOG_LINES + 2, 12),
            ),
        )
        return layout

    def _build_header(self) -> Panel:
        mode = self._config.agent_mode.upper()
        env = self._config.trading212_env.upper()
        cash = f"${self._available_cash:,.2f}"
        line1 = (
            f"[bold cyan]🕌 Halal Trading Agent[/]  │  "
            f"Mode: [bold]{mode}[/]  │  "
            f"Env: [bold]{env}[/]  │  "
            f"Cash: [bold green]{cash}[/]"
        )
        line2 = (
            f"Last tick: [dim]{self._last_tick_time}[/]  │  "
            f"Next tick in: [bold]{self._next_tick_in}s[/]  │  "
            f"Ticks completed: [dim]{self._tick_count}[/]"
        )
        return Panel(f"{line1}\n{line2}", title="[bold]Dashboard[/]")

    def _build_watchlist_table(self) -> Panel:
        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column("Ticker", style="bold", width=8)
        table.add_column("Halal", justify="center", width=6)
        table.add_column("Price", justify="right", width=12)
        table.add_column("High (20)", justify="right", width=12)
        table.add_column("Low (20)", justify="right", width=12)
        table.add_column("From High", justify="right", width=10)
        table.add_column("Signal", justify="center", width=10)

        for ticker in self._config.watchlist:
            row = self._ticker_rows.get(ticker)
            if row is None:
                table.add_row(ticker, "…", "—", "—", "—", "—", "[dim]waiting…[/]")
                continue

            if row.get("halal") is True:
                halal_cell = "[green]✅[/]"
            elif row.get("halal") is False:
                halal_cell = "[red]❌[/]"
            else:
                halal_cell = "[yellow]?[/]"

            price = row.get("price")
            high = row.get("high")
            low = row.get("low")
            pct_high = row.get("pct_high")
            signal = row.get("signal", "—")

            price_str = f"${price:,.4f}" if price is not None else "—"
            high_str = f"${high:,.4f}" if high is not None else "—"
            low_str = f"${low:,.4f}" if low is not None else "—"

            if pct_high is not None:
                pct_str = f"{pct_high:+.2f}%"
                pct_cell = (
                    f"[green]{pct_str}[/]"
                    if pct_high >= 0
                    else f"[red]{pct_str}[/]"
                )
            else:
                pct_cell = "—"

            if signal == "BUY":
                signal_cell = "[bold green]🟢 BUY[/]"
            elif signal == "SELL":
                signal_cell = "[bold red]🔴 SELL[/]"
            elif signal == "HOLD":
                signal_cell = "[dim]HOLD[/]"
            else:
                signal_cell = f"[dim]{signal}[/]"

            table.add_row(
                ticker,
                halal_cell,
                price_str,
                high_str,
                low_str,
                pct_cell,
                signal_cell,
            )

        return Panel(table, title="[bold]Watchlist[/]")

    def _build_log_panel(self) -> Panel:
        lines = list(self._dash_log) or ["[dim]No activity yet…[/]"]
        return Panel("\n".join(lines), title="[bold]Activity Log[/]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    agent = DashboardAgent()
    agent.run()
