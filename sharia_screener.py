"""
Sharia compliance screener.

Checks whether a stock is sharia-compliant using:
1. Built-in sector/industry exclusion list.
2. Optional Musaffa API (https://musaffa.com) when an API key is provided.

A ticker is treated as **compliant** only when it passes *all* checks.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

import requests

logger = logging.getLogger(__name__)

ComplianceStatus = Literal["compliant", "non_compliant", "doubtful", "unknown"]

# Sectors / industries that are categorically non-compliant under AAOIFI standards
_NON_COMPLIANT_SECTORS: set[str] = {
    # Conventional finance
    "banks",
    "banking",
    "insurance",
    "financial services",
    "diversified financials",
    "consumer finance",
    "thrifts & mortgage finance",
    "capital markets",
    # Alcohol
    "beverages - brewers",
    "beverages - wineries & distilleries",
    "alcoholic beverages",
    # Tobacco
    "tobacco",
    # Gambling
    "gambling",
    "casinos & gaming",
    "resorts & casinos",
    # Weapons / defence (controversial – some scholars permit)
    "aerospace & defense",
    # Pork
    "packaged foods & meats",  # broad – caught below via name check
    # Adult entertainment
    "entertainment",  # broad – refined below via name check
    # Conventional REITs that hold prohibited assets
}

# Specific company name fragments that signal non-compliance
_NON_COMPLIANT_NAME_FRAGMENTS: frozenset[str] = frozenset(
    {
        "alcohol",
        "spirits",
        "brewery",
        "breweries",
        "distillery",
        "wine",
        "casino",
        "gambling",
        "tobacco",
        "cigarette",
        "porn",
        "adult",
        "pork",
        "ham",
        "bacon",
        "weapons",
        "ammunition",
    }
)

_MUSAFFA_BASE_URL = "https://api.musaffa.com/v1"
_DEFAULT_TIMEOUT = 10

# Sectors / industries considered clean for sharia compliance
_CLEAN_SECTORS: frozenset[str] = frozenset(
    {
        "technology",
        "software",
        "healthcare",
        "pharmaceuticals",
        "consumer electronics",
        "semiconductors",
        "retail",
        "e-commerce",
        "industrials",
        "utilities",
        "telecommunications",
        "real estate",  # depends – mark doubtful by default; kept here as best-effort
    }
)


class ShariaScreener:
    """Checks sharia compliance for a given stock ticker."""

    def __init__(self, musaffa_api_key: str = "") -> None:
        self._musaffa_api_key = musaffa_api_key
        self._session = requests.Session()
        if musaffa_api_key:
            self._session.headers.update({"Authorization": f"Bearer {musaffa_api_key}"})

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_compliant(self, ticker: str, instrument: dict | None = None) -> bool:
        """Return True if the ticker is considered sharia-compliant."""
        status = self.get_compliance_status(ticker, instrument)
        return status == "compliant"

    def get_compliance_status(
        self, ticker: str, instrument: dict | None = None
    ) -> ComplianceStatus:
        """Return the detailed compliance status for *ticker*.

        Resolution order:
        1. Musaffa API (if API key is set).
        2. Built-in sector / name heuristics derived from *instrument* metadata.
        3. 'unknown' if no information is available.
        """
        if self._musaffa_api_key:
            musaffa_status = self._check_musaffa(ticker)
            if musaffa_status != "unknown":
                return musaffa_status

        if instrument:
            return self._check_instrument_metadata(instrument)

        return "unknown"

    # ------------------------------------------------------------------
    # Musaffa API
    # ------------------------------------------------------------------

    @lru_cache(maxsize=512)
    def _check_musaffa(self, ticker: str) -> ComplianceStatus:
        """Query the Musaffa API for *ticker*."""
        try:
            response = self._session.get(
                f"{_MUSAFFA_BASE_URL}/instruments/{ticker}/compliance",
                timeout=_DEFAULT_TIMEOUT,
            )
            if response.status_code == 404:
                return "unknown"
            response.raise_for_status()
            data = response.json()
            rating = data.get("shariahCompliance", {}).get("status", "").lower()
            mapping = {
                "halal": "compliant",
                "haram": "non_compliant",
                "questionable": "doubtful",
                "not covered": "unknown",
            }
            return mapping.get(rating, "unknown")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Musaffa API check failed for %s: %s", ticker, exc)
            return "unknown"

    # ------------------------------------------------------------------
    # Heuristic / metadata check
    # ------------------------------------------------------------------

    @staticmethod
    def _check_instrument_metadata(instrument: dict) -> ComplianceStatus:
        """Use instrument name and sector to make a best-effort assessment."""
        sector = (instrument.get("sector") or instrument.get("type") or "").lower()
        name = (instrument.get("name") or "").lower()

        # Check sector exclusion list
        for excluded in _NON_COMPLIANT_SECTORS:
            if excluded in sector:
                logger.debug("Sector '%s' is non-compliant", sector)
                return "non_compliant"

        # Check company name for obvious red flags
        for fragment in _NON_COMPLIANT_NAME_FRAGMENTS:
            if fragment in name:
                logger.debug(
                    "Name fragment '%s' detected in '%s' – marking non-compliant",
                    fragment,
                    name,
                )
                return "non_compliant"

        # Not enough information to confirm compliance; treat as doubtful
        # unless the sector is known-clean
        for clean in _CLEAN_SECTORS:
            if clean in sector:
                return "compliant"

        return "doubtful"

    # ------------------------------------------------------------------
    # Batch helper
    # ------------------------------------------------------------------

    def filter_compliant(
        self, tickers: list[str], instruments: dict[str, dict] | None = None
    ) -> list[str]:
        """Return the subset of *tickers* that are sharia-compliant.

        Args:
            tickers: List of ticker symbols.
            instruments: Optional mapping of ticker -> instrument metadata.
        """
        if instruments is None:
            instruments = {}
        result = []
        for ticker in tickers:
            status = self.get_compliance_status(ticker, instruments.get(ticker))
            if status == "compliant":
                result.append(ticker)
            else:
                logger.info(
                    "Ticker %s excluded from watchlist (status: %s)", ticker, status
                )
        return result
