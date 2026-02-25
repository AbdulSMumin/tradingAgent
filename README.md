# tradingAgent

A custom Python agent that monitors sharia-compliant stocks in real time using your [Trading 212](https://www.trading212.com) account. It can either **execute buy/sell orders automatically** or **send Discord notifications** instructing you to act.

---

## Features

| Feature | Detail |
|---|---|
| 🕌 Sharia screening | Built-in sector/name heuristics + optional [Musaffa](https://musaffa.com) API |
| 📈 Real-time monitoring | Configurable polling interval via Trading 212 API |
| 🤖 Auto-trading | Places market orders directly via Trading 212 REST API |
| 💬 Discord notifications | Rich embeds sent to any Discord channel via webhook |
| ⚙️ Flexible mode | `auto` (trade only), `notify` (Discord only), `both` |

---

## Architecture

```
trading212_client.py   — Trading 212 REST API wrapper (account, portfolio, orders)
sharia_screener.py     — Sharia compliance checker (sectors, names, Musaffa API)
discord_notifier.py    — Discord webhook notifier
trading_agent.py       — Main orchestrator (monitoring loop, signals, execution)
config.py              — Loads all settings from environment variables
```

The agent runs a monitoring loop every `MONITOR_INTERVAL` seconds. On each tick it:

1. Fetches available cash from your Trading 212 account.
2. For each ticker in the watchlist it checks sharia compliance.
3. Tracks prices in a rolling window and generates **BUY** (price dropped `BUY_SIGNAL_THRESHOLD`% below recent high) or **SELL** (price rose `SELL_SIGNAL_THRESHOLD`% above recent low) signals.
4. Depending on `AGENT_MODE`, it places a market order and/or sends a Discord notification.

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/AbdulSMumin/tradingAgent.git
cd tradingAgent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your values
```

| Variable | Required | Description |
|---|---|---|
| `TRADING212_API_KEY` | ✅ | API key from Trading 212 app → Settings → API |
| `TRADING212_ENV` | ✅ | `demo` or `live` |
| `DISCORD_WEBHOOK_URL` | When mode ≠ `auto` | Discord channel webhook URL |
| `AGENT_MODE` | ✅ | `auto`, `notify`, or `both` |
| `WATCHLIST` | ✅ | Comma-separated tickers, e.g. `AAPL,MSFT,AMZN` |
| `MONITOR_INTERVAL` | | Seconds between checks (default `60`) |
| `MUSAFFA_API_KEY` | | Optional — enables Musaffa sharia screening |
| `BUY_SIGNAL_THRESHOLD` | | % drop from recent high to trigger BUY (default `2.0`) |
| `SELL_SIGNAL_THRESHOLD` | | % rise from recent low to trigger SELL (default `3.0`) |
| `MAX_POSITION_SIZE` | | Max fraction of cash per order (default `0.1` = 10%) |

### 3. Get a Trading 212 API key

1. Open Trading 212 (web or mobile app).
2. Go to **Settings → API** and generate a key.
3. Use the **Demo** environment first for testing.

### 4. Create a Discord webhook

1. Open your Discord server → **Edit Server → Integrations → Webhooks → New Webhook**.
2. Copy the webhook URL and paste it into `.env`.

### 5. Run

```bash
python trading_agent.py
```

---

## Sharia Screening

The agent uses a two-tier approach:

1. **Musaffa API** (if `MUSAFFA_API_KEY` is set): fetches the official halal/haram rating for each ticker.
2. **Built-in heuristics** (always active as a fallback): excludes sectors such as conventional banking, alcohol, tobacco, gambling, and checks for non-compliant keywords in company names.

Tickers rated **doubtful** or **unknown** are excluded from trading by default.

---

## Running Tests

```bash
pip install pytest responses
python -m pytest tests/ -v
```

---

## Disclaimer

This software is for educational purposes only and does not constitute financial or religious advice. Always verify sharia compliance with a qualified Islamic finance scholar before investing.

