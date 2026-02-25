"""Tests for trading212_client.py"""

import pytest
import requests
import responses

from trading212_client import Trading212Client, Trading212Error

BASE_URL = "https://demo.trading212.com/api/v0"


@pytest.fixture
def client():
    return Trading212Client(api_key="test-key", base_url=BASE_URL)


@responses.activate
def test_get_account_info(client):
    expected = {"id": "acc-1", "currencyCode": "GBP"}
    responses.add(
        responses.GET,
        f"{BASE_URL}/equity/account/info",
        json=expected,
        status=200,
    )
    result = client.get_account_info()
    assert result == expected


@responses.activate
def test_get_account_cash(client):
    expected = {"free": 500.0, "invested": 1000.0}
    responses.add(
        responses.GET,
        f"{BASE_URL}/equity/account/cash",
        json=expected,
        status=200,
    )
    result = client.get_account_cash()
    assert result == expected


@responses.activate
def test_get_portfolio(client):
    expected = [{"ticker": "AAPL", "quantity": 10}]
    responses.add(
        responses.GET,
        f"{BASE_URL}/equity/portfolio",
        json=expected,
        status=200,
    )
    result = client.get_portfolio()
    assert result == expected


@responses.activate
def test_get_position_found(client):
    expected = {"ticker": "AAPL", "quantity": 5}
    responses.add(
        responses.GET,
        f"{BASE_URL}/equity/portfolio/AAPL",
        json=expected,
        status=200,
    )
    result = client.get_position("AAPL")
    assert result == expected


@responses.activate
def test_get_position_not_found(client):
    responses.add(
        responses.GET,
        f"{BASE_URL}/equity/portfolio/AAPL",
        json={"errorCode": "NOT_FOUND"},
        status=404,
    )
    result = client.get_position("AAPL")
    assert result is None


@responses.activate
def test_get_instruments(client):
    instruments = [{"ticker": "AAPL", "name": "Apple Inc."}]
    responses.add(
        responses.GET,
        f"{BASE_URL}/equity/instruments",
        json=instruments,
        status=200,
    )
    result = client.get_instruments()
    assert result == instruments


@responses.activate
def test_find_instrument_found(client):
    instruments = [
        {"ticker": "AAPL", "name": "Apple Inc."},
        {"ticker": "MSFT", "name": "Microsoft"},
    ]
    responses.add(
        responses.GET,
        f"{BASE_URL}/equity/instruments",
        json=instruments,
        status=200,
    )
    result = client.find_instrument("aapl")
    assert result is not None
    assert result["ticker"] == "AAPL"


@responses.activate
def test_find_instrument_not_found(client):
    responses.add(
        responses.GET,
        f"{BASE_URL}/equity/instruments",
        json=[],
        status=200,
    )
    result = client.find_instrument("XYZ")
    assert result is None


@responses.activate
def test_place_market_order(client):
    expected = {"id": 1, "ticker": "AAPL", "quantity": 5}
    responses.add(
        responses.POST,
        f"{BASE_URL}/equity/orders/market",
        json=expected,
        status=200,
    )
    result = client.place_market_order("AAPL", 5)
    assert result == expected
    assert responses.calls[0].request.body is not None


@responses.activate
def test_place_limit_order(client):
    expected = {"id": 2, "ticker": "MSFT", "quantity": 3}
    responses.add(
        responses.POST,
        f"{BASE_URL}/equity/orders/limit",
        json=expected,
        status=200,
    )
    result = client.place_limit_order("MSFT", 3, 250.0)
    assert result == expected


@responses.activate
def test_cancel_order(client):
    responses.add(
        responses.DELETE,
        f"{BASE_URL}/equity/orders/42",
        json={},
        status=200,
    )
    result = client.cancel_order(42)
    assert result == {}


@responses.activate
def test_api_error_raises(client):
    responses.add(
        responses.GET,
        f"{BASE_URL}/equity/account/info",
        json={"message": "Unauthorized"},
        status=401,
    )
    with pytest.raises(Trading212Error):
        client.get_account_info()


@responses.activate
def test_authorization_header(client):
    responses.add(
        responses.GET,
        f"{BASE_URL}/equity/account/info",
        json={},
        status=200,
    )
    client.get_account_info()
    assert responses.calls[0].request.headers["Authorization"] == "test-key"
