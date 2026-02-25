"""
Discord notifier.

Sends trading signal messages to a Discord channel via an Incoming Webhook.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

import requests

logger = logging.getLogger(__name__)

SignalType = Literal["BUY", "SELL", "INFO", "ERROR"]

# Embed colour per signal type
_COLOURS: dict[str, int] = {
    "BUY": 0x2ECC71,   # green
    "SELL": 0xE74C3C,  # red
    "INFO": 0x3498DB,  # blue
    "ERROR": 0xFF8C00, # orange
}

_DEFAULT_TIMEOUT = 10


class DiscordNotifier:
    """Send messages to a Discord channel via an Incoming Webhook."""

    def __init__(self, webhook_url: str) -> None:
        if not webhook_url:
            raise ValueError("webhook_url must not be empty.")
        self._webhook_url = webhook_url
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def send_signal(
        self,
        signal: SignalType,
        ticker: str,
        price: float,
        reason: str = "",
        quantity: float | None = None,
        executed: bool = False,
    ) -> None:
        """Post a trading signal embed to Discord.

        Args:
            signal: 'BUY' or 'SELL'.
            ticker: Stock ticker symbol.
            price: Current price.
            reason: Human-readable reason for the signal.
            quantity: Number of shares involved (if known).
            executed: Whether the trade was auto-executed.
        """
        action = "🟢 BUY" if signal == "BUY" else "🔴 SELL"
        title = f"{action} Signal — {ticker}"

        fields = [
            {"name": "Ticker", "value": ticker, "inline": True},
            {"name": "Price", "value": f"${price:,.4f}", "inline": True},
        ]
        if quantity is not None:
            fields.append(
                {"name": "Quantity", "value": f"{quantity:,.4f}", "inline": True}
            )
        if reason:
            fields.append({"name": "Reason", "value": reason, "inline": False})

        status_text = "✅ Auto-executed" if executed else "⚠️ Manual action required"
        fields.append({"name": "Status", "value": status_text, "inline": False})

        self._send_embed(
            title=title,
            colour=_COLOURS.get(signal, 0xFFFFFF),
            fields=fields,
        )

    def send_info(self, message: str) -> None:
        """Post an informational message."""
        self._send_embed(
            title="ℹ️ Trading Agent — Info",
            colour=_COLOURS["INFO"],
            fields=[{"name": "Message", "value": message, "inline": False}],
        )

    def send_error(self, message: str) -> None:
        """Post an error message."""
        self._send_embed(
            title="⚠️ Trading Agent — Error",
            colour=_COLOURS["ERROR"],
            fields=[{"name": "Error", "value": message, "inline": False}],
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send_embed(self, title: str, colour: int, fields: list[dict]) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        payload = {
            "embeds": [
                {
                    "title": title,
                    "color": colour,
                    "fields": fields,
                    "footer": {"text": "Halal Trading Agent"},
                    "timestamp": timestamp,
                }
            ]
        }
        self._post(payload)

    def _post(self, payload: dict) -> None:
        try:
            response = self._session.post(
                self._webhook_url,
                json=payload,
                timeout=_DEFAULT_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to send Discord notification: %s", exc)
            raise
