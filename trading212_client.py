"""
Trading 212 REST API client.

Docs: https://t212public-api-docs.redoc.ly/
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 15  # seconds


class Trading212Error(Exception):
    """Raised when the Trading 212 API returns an error."""


class Trading212Client:
    """Thin wrapper around the Trading 212 v0 REST API."""

    def __init__(self, api_key: str, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": api_key,
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self._base_url}{path}"
        response = self._session.get(url, params=params, timeout=_DEFAULT_TIMEOUT)
        self._raise_for_status(response)
        return response.json()

    def _post(self, path: str, payload: dict) -> Any:
        url = f"{self._base_url}{path}"
        response = self._session.post(url, json=payload, timeout=_DEFAULT_TIMEOUT)
        self._raise_for_status(response)
        return response.json()

    def _delete(self, path: str) -> Any:
        url = f"{self._base_url}{path}"
        response = self._session.delete(url, timeout=_DEFAULT_TIMEOUT)
        self._raise_for_status(response)
        return response.json() if response.content else {}

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        if not response.ok:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise Trading212Error(
                f"Trading 212 API error {response.status_code}: {detail}"
            )

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_account_info(self) -> dict:
        """Return account metadata (currency, ID, etc.)."""
        return self._get("/equity/account/info")

    def get_account_cash(self) -> dict:
        """Return available cash and investment amounts."""
        return self._get("/equity/account/cash")

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    def get_portfolio(self) -> list[dict]:
        """Return all open positions."""
        return self._get("/equity/portfolio")

    def get_position(self, ticker: str) -> dict | None:
        """Return the open position for *ticker*, or None if not held."""
        try:
            return self._get(f"/equity/portfolio/{ticker}")
        except Trading212Error as exc:
            if "404" in str(exc) or "not found" in str(exc).lower():
                return None
            raise

    # ------------------------------------------------------------------
    # Instruments
    # ------------------------------------------------------------------

    def get_instruments(self) -> list[dict]:
        """Return all tradeable instruments."""
        return self._get("/equity/instruments")

    def find_instrument(self, ticker: str) -> dict | None:
        """Return instrument metadata for *ticker*, or None if not found."""
        instruments = self.get_instruments()
        ticker_upper = ticker.upper()
        for instrument in instruments:
            if instrument.get("ticker", "").upper() == ticker_upper:
                return instrument
        return None

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def place_market_order(self, ticker: str, quantity: float) -> dict:
        """Place a market order.

        Args:
            ticker: Instrument ticker symbol.
            quantity: Number of shares (positive = buy, negative = sell).
        """
        payload = {"ticker": ticker, "quantity": quantity}
        logger.info("Placing market order: %s x %.4f", ticker, quantity)
        return self._post("/equity/orders/market", payload)

    def place_limit_order(
        self,
        ticker: str,
        quantity: float,
        limit_price: float,
        time_validity: str = "DAY",
    ) -> dict:
        """Place a limit order.

        Args:
            ticker: Instrument ticker symbol.
            quantity: Number of shares (positive = buy, negative = sell).
            limit_price: Limit price.
            time_validity: 'DAY' or 'GOOD_TILL_CANCEL'.
        """
        payload = {
            "ticker": ticker,
            "quantity": quantity,
            "limitPrice": limit_price,
            "timeValidity": time_validity,
        }
        logger.info(
            "Placing limit order: %s x %.4f @ %.4f", ticker, quantity, limit_price
        )
        return self._post("/equity/orders/limit", payload)

    def cancel_order(self, order_id: int) -> dict:
        """Cancel an open order by ID."""
        logger.info("Cancelling order %s", order_id)
        return self._delete(f"/equity/orders/{order_id}")

    def get_orders(self) -> list[dict]:
        """Return all open/pending orders."""
        return self._get("/equity/orders")

    def get_order(self, order_id: int) -> dict:
        """Return a specific order by ID."""
        return self._get(f"/equity/orders/{order_id}")
