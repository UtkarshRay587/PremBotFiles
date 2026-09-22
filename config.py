"""
config.py
Loads configuration from environment variables (.env).
Never hard-code secrets here — everything sensitive comes from the environment.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _get_int_env(name: str, default=None):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "" or raw.strip().startswith("YOUR_"):
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Environment variable %s is not a valid integer, ignoring.", name)
        return default


def _get_str_env(name: str, default=None):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "" or raw.strip().startswith("YOUR_"):
        return default
    return raw.strip()


# --- Required ---
BOT_TOKEN = _get_str_env("BOT_TOKEN")

# --- Admin ---
ADMIN_ID = _get_int_env("ADMIN_ID") or _get_int_env("OWNER_ID")

# --- Channels (can also be changed later at runtime via the admin panel,
# these are just the initial values loaded into the settings table) ---
MEMBER_CHANNEL_ID = _get_int_env("MEMBER_CHANNEL_ID") or _get_int_env("PREMIUM_CHANNEL_ID")
VERIFICATION_CHANNEL_ID = _get_int_env("VERIFICATION_CHANNEL_ID")

# --- UPI ---
UPI_ID = _get_str_env("UPI_ID", "your-upi-id@bank")
UPI_NAME = _get_str_env("UPI_NAME", "Your Name")

# --- Database ---
DB_PATH = _get_str_env("DB_PATH", "bot_database.db")

# --- Defaults (only used the very first time the bot starts, then stored in DB) ---
DEFAULT_PRICE_INR = _get_int_env("DEFAULT_PRICE_INR") or _get_int_env("UPI_PRICE_INR", 30)
DEFAULT_PRICE_STARS = _get_int_env("DEFAULT_PRICE_STARS") or _get_int_env("STARS_PRICE", 25)

# --- Currency for Telegram Stars payments (must be XTR) ---
STARS_CURRENCY = "XTR"


def validate_config():
    """Validate required configuration at startup. Returns a list of problems (empty = OK)."""
    problems = []
    if not BOT_TOKEN:
        problems.append("BOT_TOKEN is missing. Set it in your .env file.")
    if not ADMIN_ID:
        problems.append("ADMIN_ID is missing. Set it in your .env file (your numeric Telegram ID).")
    if not MEMBER_CHANNEL_ID:
        logger.warning("MEMBER_CHANNEL_ID is not set. You can configure it later from /admin -> CHANNELS.")
    if not VERIFICATION_CHANNEL_ID:
        logger.warning("VERIFICATION_CHANNEL_ID is not set. You can configure it later from /admin -> CHANNELS.")
    return problems
