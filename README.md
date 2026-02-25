# tradingAgent

A custom Python agent that monitors sharia-compliant stocks in real time using your [Trading 212](https://www.trading212.com) account. It can either **execute buy/sell orders automatically** or **send Discord notifications** instructing you to act.

---

## What Was Built

This project is a fully autonomous **halal trading agent** written in Python. Here is exactly what it does and what each part is:

### The problem it solves
You want to trade only sharia-compliant (halal) stocks but doing so manually — checking compliance, watching prices, deciding when to buy/sell — is time-consuming. This agent automates the entire loop for you.

### How it works end-to-end

1. **You configure a watchlist** of stock tickers (e.g. `AAPL,MSFT,AMZN`) and point the agent at your Trading 212 account (demo or live) via an API key set in a `.env` file.

2. **Every N seconds** (default: 60) the agent wakes up and, for each ticker in your list:
   - Checks whether the stock is **sharia-compliant**. Non-compliant stocks (conventional banks, insurance, alcohol, tobacco, gambling, weapons, etc.) are silently skipped.
   - Reads the latest price from Trading 212's instrument catalogue.
   - Feeds the price into a **rolling price tracker** (last 20 prices) and generates one of three signals:
     - `BUY` — if the price has dropped ≥ 2% below its recent high (dip-buying strategy).
     - `SELL` — if the price has risen ≥ 3% above its recent low (take-profit strategy).
     - `HOLD` — no action.

3. **When a BUY or SELL signal fires**, the agent does one or both of the following depending on `AGENT_MODE`:
   - **`auto`** — places a market order on Trading 212 immediately (buys up to 10% of available cash, sells the full held position).
   - **`notify`** — sends a colour-coded rich embed to a Discord channel (green for BUY, red for SELL) with the ticker, price, quantity, reason, and whether it was auto-executed.
   - **`both`** — executes the trade *and* sends the Discord message.

### The five source files

| File | What it is |
|---|---|
| `trading212_client.py` | Speaks to the Trading 212 REST API — reads account cash, portfolio positions, the full instruments catalogue, and places or cancels market/limit orders. |
| `sharia_screener.py` | Decides whether a ticker is halal. Uses two layers: (1) a built-in list of excluded sectors/name keywords; (2) the optional [Musaffa API](https://musaffa.com) for a professionally rated halal/haram verdict. Falls back gracefully if the API is unavailable. |
| `discord_notifier.py` | Sends formatted Discord messages via an Incoming Webhook. Covers buy signals, sell signals, general info messages, and error alerts. |
| `trading_agent.py` | The main brain. Wires together the other modules. Contains the `PriceTracker` (rolling window), `SignalGenerator` (threshold logic), and `TradingAgent` (the monitoring loop). |
| `config.py` | Reads all settings from environment variables (or a `.env` file). Nothing is hard-coded. |

### What you need to use it
- A **Trading 212 account** with an API key (free from Settings → API in the app). Start with the **demo** environment.
- A **Discord webhook URL** if you want notifications (free — create one in any Discord server under Integrations → Webhooks).
- Python 3.12+ and two libraries: `requests` and `python-dotenv`.

### What it does NOT do (current limitations)
- It does not use live streaming prices — it polls the Trading 212 instruments endpoint on a timer. True tick-by-tick streaming is not available through the current Trading 212 public API.
- The buy/sell signal strategy is a simple momentum heuristic (% from rolling high/low). It is not a sophisticated quant model.
- Sharia screening via built-in heuristics is a best-effort approximation. Always verify compliance with a qualified Islamic finance scholar.

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

