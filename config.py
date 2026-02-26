"""
Configuration loader.

All settings are read from environment variables (or a .env file).
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _optional(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


class Config:
    """Centralised configuration.

    All values are read lazily from environment variables so that the module
    can be imported in tests without every variable being set.
    Call ``Config.validate()`` before starting the agent to enforce required
    fields.
    """

    # Trading 212
    trading212_api_key: str = _optional("TRADING212_API_KEY")
    trading212_env: str = _optional("TRADING212_ENV", "demo").lower()

    # Discord
    discord_webhook_url: str = _optional("DISCORD_WEBHOOK_URL")

    # Agent behaviour
    agent_mode: str = _optional("AGENT_MODE", "notify").lower()  # auto | notify | both
    monitor_interval: int = _int("MONITOR_INTERVAL", 60)

    # Optional Musaffa API key for sharia screening
    musaffa_api_key: str = _optional("MUSAFFA_API_KEY")

    # Watchlist
    watchlist: list[str] = [
        t.strip().upper()
        for t in _optional("WATCHLIST", "").split(",")
        if t.strip()
    ]

    # Signal thresholds (percent)
    buy_signal_threshold: float = _float("BUY_SIGNAL_THRESHOLD", 2.0)
    sell_signal_threshold: float = _float("SELL_SIGNAL_THRESHOLD", 3.0)

    # Max fraction of cash per order
    max_position_size: float = _float("MAX_POSITION_SIZE", 0.1)

    @classmethod
    def trading212_base_url(cls) -> str:
        if cls.trading212_env == "live":
            return "https://live.trading212.com/api/v0"
        return "https://demo.trading212.com/api/v0"

    @classmethod
    def validate(cls) -> None:
        """Raise if mandatory settings are missing or invalid."""
        if not cls.trading212_api_key:
            raise ValueError("Required environment variable 'TRADING212_API_KEY' is not set.")
        valid_modes = {"auto", "notify", "both"}
        if cls.agent_mode not in valid_modes:
            raise ValueError(
                f"AGENT_MODE must be one of {valid_modes}, got '{cls.agent_mode}'"
            )
        if cls.agent_mode in {"notify", "both"} and not cls.discord_webhook_url:
            raise ValueError(
                "DISCORD_WEBHOOK_URL must be set when AGENT_MODE is 'notify' or 'both'."
            )
        if not cls.watchlist:
            raise ValueError("WATCHLIST must contain at least one ticker symbol.")
