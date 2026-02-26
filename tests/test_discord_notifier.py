"""Tests for discord_notifier.py"""

import json

import pytest
import responses

from discord_notifier import DiscordNotifier

WEBHOOK_URL = "https://discord.com/api/webhooks/123/abc"


@pytest.fixture
def notifier():
    return DiscordNotifier(WEBHOOK_URL)


def test_init_empty_url_raises():
    with pytest.raises(ValueError):
        DiscordNotifier("")


@responses.activate
def test_send_buy_signal(notifier):
    responses.add(responses.POST, WEBHOOK_URL, status=204)
    notifier.send_signal("BUY", "AAPL", 150.25, reason="Price dropped 2%", quantity=5)

    assert len(responses.calls) == 1
    body = json.loads(responses.calls[0].request.body)
    embed = body["embeds"][0]
    assert "BUY" in embed["title"]
    assert "AAPL" in embed["title"]
    # Verify fields contain ticker and price
    field_names = {f["name"] for f in embed["fields"]}
    assert "Ticker" in field_names
    assert "Price" in field_names
    assert "Quantity" in field_names
    assert "Reason" in field_names


@responses.activate
def test_send_sell_signal(notifier):
    responses.add(responses.POST, WEBHOOK_URL, status=204)
    notifier.send_signal("SELL", "MSFT", 300.0, executed=True, quantity=3)

    body = json.loads(responses.calls[0].request.body)
    embed = body["embeds"][0]
    assert "SELL" in embed["title"]
    # Check executed status
    status_field = next(f for f in embed["fields"] if f["name"] == "Status")
    assert "Auto-executed" in status_field["value"]


@responses.activate
def test_send_signal_manual_action(notifier):
    responses.add(responses.POST, WEBHOOK_URL, status=204)
    notifier.send_signal("BUY", "TSLA", 200.0, executed=False)

    body = json.loads(responses.calls[0].request.body)
    embed = body["embeds"][0]
    status_field = next(f for f in embed["fields"] if f["name"] == "Status")
    assert "Manual action required" in status_field["value"]


@responses.activate
def test_send_info(notifier):
    responses.add(responses.POST, WEBHOOK_URL, status=204)
    notifier.send_info("Agent started.")

    body = json.loads(responses.calls[0].request.body)
    embed = body["embeds"][0]
    assert "Info" in embed["title"]


@responses.activate
def test_send_error(notifier):
    responses.add(responses.POST, WEBHOOK_URL, status=204)
    notifier.send_error("Something went wrong.")

    body = json.loads(responses.calls[0].request.body)
    embed = body["embeds"][0]
    assert "Error" in embed["title"]


@responses.activate
def test_embed_has_footer(notifier):
    responses.add(responses.POST, WEBHOOK_URL, status=204)
    notifier.send_info("test")

    body = json.loads(responses.calls[0].request.body)
    assert body["embeds"][0]["footer"]["text"] == "Halal Trading Agent"


@responses.activate
def test_discord_http_error_raises(notifier):
    responses.add(responses.POST, WEBHOOK_URL, status=400)
    with pytest.raises(Exception):
        notifier.send_info("test")


@responses.activate
def test_buy_signal_colour(notifier):
    responses.add(responses.POST, WEBHOOK_URL, status=204)
    notifier.send_signal("BUY", "AAPL", 150.0)
    body = json.loads(responses.calls[0].request.body)
    # BUY colour is green (0x2ECC71 = 3066993)
    assert body["embeds"][0]["color"] == 0x2ECC71


@responses.activate
def test_sell_signal_colour(notifier):
    responses.add(responses.POST, WEBHOOK_URL, status=204)
    notifier.send_signal("SELL", "AAPL", 150.0)
    body = json.loads(responses.calls[0].request.body)
    # SELL colour is red (0xE74C3C)
    assert body["embeds"][0]["color"] == 0xE74C3C
