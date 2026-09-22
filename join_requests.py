"""
handlers/join_requests.py
Handles Telegram ChatJoinRequest updates for the private Member Channel.

CRITICAL: approval is based solely on the numeric Telegram user ID's PAID
status in our database — never on username, and never just because someone
has an invite link. A forwarded link must not let an unpaid user in.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

import database as db

logger = logging.getLogger(__name__)


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request = update.chat_join_request
    if request is None:
        return

    chat_id = request.chat.id
    user = request.from_user

    member_channel_id = await db.get_member_channel_id()
    if member_channel_id is None or chat_id != member_channel_id:
        # Not the channel we manage access for — ignore (could be verification channel etc.)
        return

    is_paid = await db.is_user_paid(user.id)

    try:
        if is_paid:
            await context.bot.approve_chat_join_request(chat_id=chat_id, user_id=user.id)
            logger.info("Approved join request for PAID user %s in channel %s", user.id, chat_id)
            try:
                await context.bot.send_message(
                    chat_id=user.id,
                    text="✅ Your join request was approved. Welcome to the premium channel!",
                )
            except TelegramError:
                pass
        else:
            await context.bot.decline_chat_join_request(chat_id=chat_id, user_id=user.id)
            logger.info("Declined join request for non-paid user %s in channel %s", user.id, chat_id)
            try:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=(
                        "❌ Your join request was declined because we couldn't find an active "
                        "premium purchase for your account. Tap 💎 BUY PREMIUM in the bot to get access."
                    ),
                )
            except TelegramError:
                pass
    except TelegramError as e:
        logger.error("Error handling join request for user %s in channel %s: %s", user.id, chat_id, e)
