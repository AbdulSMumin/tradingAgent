"""Tests for sharia_screener.py"""

import pytest
import responses as resp_lib

from sharia_screener import ShariaScreener, _MUSAFFA_BASE_URL


@pytest.fixture
def screener():
    return ShariaScreener()


@pytest.fixture
def screener_with_musaffa():
    return ShariaScreener(musaffa_api_key="test-musaffa-key")


# ---------------------------------------------------------------------------
# Heuristic / metadata checks
# ---------------------------------------------------------------------------

def test_technology_sector_compliant(screener):
    instrument = {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"}
    assert screener.is_compliant("AAPL", instrument) is True


def test_banking_sector_non_compliant(screener):
    instrument = {"ticker": "JPM", "name": "JPMorgan Chase", "sector": "Banks"}
    assert screener.is_compliant("JPM", instrument) is False


def test_alcohol_name_non_compliant(screener):
    instrument = {"ticker": "BUD", "name": "Anheuser-Busch InBev (Alcohol)", "sector": "Consumer"}
    assert screener.is_compliant("BUD", instrument) is False


def test_tobacco_sector_non_compliant(screener):
    instrument = {"ticker": "MO", "name": "Altria Group", "sector": "Tobacco"}
    assert screener.is_compliant("MO", instrument) is False


def test_gambling_sector_non_compliant(screener):
    instrument = {"ticker": "MGM", "name": "MGM Resorts", "sector": "Casinos & Gaming"}
    assert screener.is_compliant("MGM", instrument) is False


def test_casino_name_non_compliant(screener):
    instrument = {"ticker": "LVS", "name": "Las Vegas Sands Casino", "sector": "Leisure"}
    assert screener.is_compliant("LVS", instrument) is False


def test_unknown_sector_is_doubtful(screener):
    instrument = {"ticker": "XYZ", "name": "Unknown Corp", "sector": "Conglomerate"}
    status = screener.get_compliance_status("XYZ", instrument)
    assert status == "doubtful"


def test_no_instrument_returns_unknown(screener):
    status = screener.get_compliance_status("XYZ", None)
    assert status == "unknown"


def test_software_sector_compliant(screener):
    instrument = {"ticker": "MSFT", "name": "Microsoft", "sector": "Software"}
    assert screener.is_compliant("MSFT", instrument) is True


def test_healthcare_sector_compliant(screener):
    instrument = {"ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare"}
    assert screener.is_compliant("JNJ", instrument) is True


# ---------------------------------------------------------------------------
# Filter helper
# ---------------------------------------------------------------------------

def test_filter_compliant(screener):
    instruments = {
        "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
        "JPM": {"name": "JPMorgan Chase", "sector": "Banks"},
        "MSFT": {"name": "Microsoft", "sector": "Software"},
    }
    result = screener.filter_compliant(["AAPL", "JPM", "MSFT"], instruments)
    assert "AAPL" in result
    assert "MSFT" in result
    assert "JPM" not in result


def test_filter_compliant_empty(screener):
    assert screener.filter_compliant([]) == []


# ---------------------------------------------------------------------------
# Musaffa API integration
# ---------------------------------------------------------------------------

@resp_lib.activate
def test_musaffa_halal(screener_with_musaffa):
    resp_lib.add(
        resp_lib.GET,
        f"{_MUSAFFA_BASE_URL}/instruments/AAPL/compliance",
        json={"shariahCompliance": {"status": "Halal"}},
        status=200,
    )
    status = screener_with_musaffa.get_compliance_status("AAPL")
    assert status == "compliant"


@resp_lib.activate
def test_musaffa_haram(screener_with_musaffa):
    resp_lib.add(
        resp_lib.GET,
        f"{_MUSAFFA_BASE_URL}/instruments/BUD/compliance",
        json={"shariahCompliance": {"status": "Haram"}},
        status=200,
    )
    status = screener_with_musaffa.get_compliance_status("BUD")
    assert status == "non_compliant"


@resp_lib.activate
def test_musaffa_not_found_falls_back_to_instrument(screener_with_musaffa):
    resp_lib.add(
        resp_lib.GET,
        f"{_MUSAFFA_BASE_URL}/instruments/XYZ/compliance",
        status=404,
    )
    instrument = {"name": "XYZ Corp", "sector": "Technology"}
    status = screener_with_musaffa.get_compliance_status("XYZ", instrument)
    assert status == "compliant"


@resp_lib.activate
def test_musaffa_error_falls_back_to_instrument(screener_with_musaffa):
    resp_lib.add(
        resp_lib.GET,
        f"{_MUSAFFA_BASE_URL}/instruments/AAPL/compliance",
        body=Exception("Connection error"),
    )
    instrument = {"name": "Apple Inc.", "sector": "Technology"}
    status = screener_with_musaffa.get_compliance_status("AAPL", instrument)
    assert status == "compliant"
