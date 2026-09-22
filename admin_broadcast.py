"""
handlers/admin_broadcast.py
Send a message to every registered user, with delivery statistics and
graceful handling of blocked/deleted accounts.
"""

import asyncio
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError, Forbidden
from telegram.ext import ContextTypes

import database as db
import keyboards as kb
from utils import safe_edit_or_send, set_state, clear_state, get_state

logger = logging.getLogger(__name__)

STATE_BROADCAST_MESSAGE = "awaiting_broadcast_message"


async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_state(context, STATE_BROADCAST_MESSAGE)
    text = "📢 <b>BROADCAST</b>\n\nSend the message you want to broadcast to all users:"
    await safe_edit_or_send(update, text, kb.cancel_keyboard("admin_menu"), parse_mode="HTML")


async def handle_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if get_state(context) != STATE_BROADCAST_MESSAGE:
        return False

    message_text = update.message.text
    context.user_data["broadcast_text"] = message_text
    clear_state(context)

    await update.message.reply_text(
        f"Preview:\n\n{message_text}\n\nSend this to all users?",
        reply_markup=kb.confirm_broadcast_keyboard(),
    )
    return True


async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    message_text = context.user_data.pop("broadcast_text", None)
    if not message_text:
        await query.answer("Nothing to send.", show_alert=True)
        return

    await query.answer("Sending...")
    await query.edit_message_text("📢 Sending broadcast, please wait...")

    user_ids = await db.get_all_user_ids()
    sent, failed = 0, 0
    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=message_text)
            sent += 1
        except Forbidden:
            failed += 1
        except TelegramError as e:
            logger.warning("Broadcast failed for %s: %s", uid, e)
            failed += 1
        await asyncio.sleep(0.05)  # light rate limiting to avoid hitting Telegram flood limits

    admin_id = update.effective_user.id
    await db.log_admin_action(admin_id, "BROADCAST", f"sent={sent}, failed={failed}")

    await context.bot.send_message(
        chat_id=admin_id,
        text=f"📢 <b>BROADCAST COMPLETE</b>\n\n✅ Sent: {sent}\n❌ Failed: {failed}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb.admin_back_keyboard(),
    )
    logger.info("Broadcast by admin %s: sent=%s failed=%s", admin_id, sent, failed)


async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("broadcast_text", None)
    await update.callback_query.answer("Cancelled")
    await update.callback_query.edit_message_text("📢 Broadcast cancelled.")
