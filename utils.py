"""
utils.py
Small shared helpers used across handler modules.
"""

import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

import config

logger = logging.getLogger(__name__)

# Keys used in context.user_data to track "what is the user's next text message for"
STATE_KEY = "awaiting"


def is_admin(user_id: int) -> bool:
    return config.ADMIN_ID is not None and user_id == config.ADMIN_ID


def set_state(context: ContextTypes.DEFAULT_TYPE, state: str, **extra):
    context.user_data[STATE_KEY] = state
    for k, v in extra.items():
        context.user_data[k] = v


def clear_state(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop(STATE_KEY, None)


def get_state(context: ContextTypes.DEFAULT_TYPE):
    return context.user_data.get(STATE_KEY)


def fmt_date(ts: int) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d %b %Y")


def fmt_datetime(ts: int) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d %b %Y, %H:%M UTC")


async def safe_edit_or_send(update: Update, text: str, reply_markup=None, parse_mode=None):
    """Edit the triggering callback message if possible, otherwise send a new message.
    Swallows the harmless 'message is not modified' error."""
    query = update.callback_query
    try:
        if query is not None:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        if "Message is not modified" in str(e):
            return
        logger.debug("safe_edit_or_send fallback to new message due to: %s", e)
        chat = update.effective_chat
        if chat:
            await update.get_bot().send_message(chat.id, text, reply_markup=reply_markup, parse_mode=parse_mode)


def method_emoji(method: str) -> str:
    return "⭐" if method == "STARS" else "🇮🇳" if method == "UPI" else "❔"


def status_emoji(status: str) -> str:
    return {
        "PAID": "✅",
        "PENDING": "⏳",
        "REJECTED": "❌",
        "REFUNDED": "↩️",
        "NONE": "—",
        "REVOKED": "🚫",
    }.get(status, "❔")
