"""
handlers/admin.py
Admin panel: main menu, price management, statistics, user management,
channel configuration, and welcome-message settings.

Every function here must be reached only after an is_admin() check —
enforced centrally in main.py's callback router and the /admin command.
"""

import logging
import time

from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

import database as db
import keyboards as kb
from utils import safe_edit_or_send, set_state, clear_state, get_state, fmt_date, method_emoji, status_emoji

logger = logging.getLogger(__name__)

STATE_PRICE_INR = "awaiting_price_inr"
STATE_PRICE_STARS = "awaiting_price_stars"
STATE_USER_SEARCH = "awaiting_user_search"
STATE_CHANNEL_VERIFICATION = "awaiting_channel_verification"
STATE_CHANNEL_MEMBER = "awaiting_channel_member"
STATE_WELCOME_MESSAGE = "awaiting_welcome_message"


async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_state(context)
    text = "⚙️ <b>ADMIN PANEL</b>\n\nSelect a section:"
    await safe_edit_or_send(update, text, kb.admin_menu_keyboard(), parse_mode="HTML")


# ---------------------------------------------------------------------------
# Price
# ---------------------------------------------------------------------------

async def admin_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price_inr = await db.get_price_inr()
    price_stars = await db.get_price_stars()
    text = (
        "💰 <b>PRICE MANAGEMENT</b>\n\n"
        f"Current INR price: ₹{price_inr:g}\n"
        f"Current Stars price: ⭐{price_stars}\n\n"
        "Choose what to change:"
    )
    await safe_edit_or_send(update, text, kb.admin_price_keyboard(), parse_mode="HTML")


async def price_change_inr_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = await db.get_price_inr()
    set_state(context, STATE_PRICE_INR)
    await safe_edit_or_send(
        update, f"Current price: ₹{price:g}\n\nEnter new price (numbers only):",
        kb.cancel_keyboard("admin_price"),
    )


async def price_change_stars_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = await db.get_price_stars()
    set_state(context, STATE_PRICE_STARS)
    await safe_edit_or_send(
        update, f"Current Stars price: ⭐{price}\n\nEnter new Stars price (whole number):",
        kb.cancel_keyboard("admin_price"),
    )


async def handle_price_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    state = get_state(context)
    if state not in (STATE_PRICE_INR, STATE_PRICE_STARS):
        return False

    raw = update.message.text.strip().replace("₹", "").replace(",", "")
    try:
        value = float(raw)
        if value <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Invalid price. Please enter a positive number.")
        return True

    admin_id = update.effective_user.id
    if state == STATE_PRICE_INR:
        await db.set_setting("price_inr", str(value if value != int(value) else int(value)))
        await db.log_admin_action(admin_id, "CHANGE_PRICE_INR", str(value))
        await update.message.reply_text(f"✅ INR price updated to ₹{value:g}")
    else:
        await db.set_setting("price_stars", str(int(value)))
        await db.log_admin_action(admin_id, "CHANGE_PRICE_STARS", str(int(value)))
        await update.message.reply_text(f"✅ Stars price updated to ⭐{int(value)}")

    clear_state(context)
    return True


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = await db.count_users()
    paid_users = await db.count_paid_users()
    stars_sales = await db.count_sales_by_method("STARS")
    upi_sales = await db.count_sales_by_method("UPI")
    total_revenue = await db.total_revenue_inr()
    pending_upi = await db.count_pending_upi()

    midnight_ts = int(time.time()) - (int(time.time()) % 86400)
    new_users_today = await db.count_users_since(midnight_ts)
    sales_today = await db.count_sales_since(midnight_ts)
    revenue_today = await db.revenue_since_inr(midnight_ts)

    text = (
        "📊 <b>STATISTICS</b>\n\n"
        f"👥 Total Users: {total_users}\n"
        f"💎 Premium Users: {paid_users}\n\n"
        f"⭐ Stars Sales: {stars_sales}\n"
        f"🇮🇳 UPI Sales: {upi_sales}\n\n"
        f"💰 Total Revenue (UPI): ₹{total_revenue:g}\n\n"
        f"⏳ Pending UPI: {pending_upi}\n\n"
        "📅 <b>Today:</b>\n"
        f"New Users: {new_users_today}\n"
        f"Sales: {sales_today}\n"
        f"Revenue: ₹{revenue_today:g}"
    )
    await safe_edit_or_send(update, text, kb.admin_back_keyboard(), parse_mode="HTML")


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "👥 <b>USERS</b>\n\nSearch by Telegram ID or username."
    await safe_edit_or_send(update, text, kb.admin_users_keyboard(), parse_mode="HTML")


async def user_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_state(context, STATE_USER_SEARCH)
    await safe_edit_or_send(
        update, "Enter a Telegram ID or username to search:", kb.cancel_keyboard("admin_users")
    )


def _format_user_card(user_row) -> str:
    return (
        "👤 <b>USER</b>\n\n"
        f"Username: @{user_row['username'] or 'N/A'}\n"
        f"Telegram ID: {user_row['telegram_id']}\n"
        f"Status: {status_emoji(user_row['status'])} {user_row['status']}\n"
        f"Joined: {fmt_date(user_row['created_at'])}"
    )


async def handle_user_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if get_state(context) != STATE_USER_SEARCH:
        return False

    query = update.message.text.strip()
    clear_state(context)
    results = await db.find_users(query)
    if not results:
        await update.message.reply_text("No matching users found.", reply_markup=kb.admin_back_keyboard("admin_users"))
        return True

    if len(results) == 1:
        u = results[0]
        await update.message.reply_text(
            _format_user_card(u), reply_markup=kb.admin_user_actions_keyboard(u["telegram_id"]), parse_mode="HTML"
        )
    else:
        lines = [f"@{u['username'] or 'N/A'} — {u['telegram_id']}" for u in results]
        await update.message.reply_text(
            "Multiple matches found:\n\n" + "\n".join(lines) + "\n\nSearch again with the exact Telegram ID.",
            reply_markup=kb.admin_back_keyboard("admin_users"),
        )
    return True


async def view_user_card(update: Update, context: ContextTypes.DEFAULT_TYPE, telegram_id: int):
    user_row = await db.get_user(telegram_id)
    if not user_row:
        await safe_edit_or_send(update, "⚠️ User not found.", kb.admin_back_keyboard("admin_users"))
        return
    await safe_edit_or_send(
        update, _format_user_card(user_row), kb.admin_user_actions_keyboard(telegram_id), parse_mode="HTML"
    )


async def grant_access(update: Update, context: ContextTypes.DEFAULT_TYPE, telegram_id: int):
    admin_id = update.effective_user.id
    await db.set_user_status(telegram_id, "PAID")
    await db.log_admin_action(admin_id, "GRANT_ACCESS", f"telegram_id={telegram_id}")
    await update.callback_query.answer("Access granted ✅")
    await view_user_card(update, context, telegram_id)
    try:
        await context.bot.send_message(
            telegram_id, "✅ Your premium access has been granted by an admin.",
            reply_markup=kb.join_channel_keyboard(),
        )
    except TelegramError:
        pass
    logger.info("Admin %s granted access to user %s", admin_id, telegram_id)


async def revoke_access(update: Update, context: ContextTypes.DEFAULT_TYPE, telegram_id: int):
    admin_id = update.effective_user.id
    await db.set_user_status(telegram_id, "REVOKED")
    await db.log_admin_action(admin_id, "REVOKE_ACCESS", f"telegram_id={telegram_id}")

    member_channel_id = await db.get_member_channel_id()
    if member_channel_id:
        try:
            await context.bot.ban_chat_member(member_channel_id, telegram_id)
            await context.bot.unban_chat_member(member_channel_id, telegram_id, only_if_banned=True)
        except TelegramError as e:
            logger.warning("Could not remove user %s from member channel: %s", telegram_id, e)

    await update.callback_query.answer("Access revoked 🚫")
    await view_user_card(update, context, telegram_id)
    try:
        await context.bot.send_message(telegram_id, "🚫 Your premium access has been revoked by an admin.")
    except TelegramError:
        pass
    logger.info("Admin %s revoked access for user %s", admin_id, telegram_id)


async def admin_user_history(update: Update, context: ContextTypes.DEFAULT_TYPE, telegram_id: int):
    history = await db.get_payment_history(telegram_id)
    if not history:
        text = "🧾 No payment history for this user."
    else:
        lines = [
            f"{status_emoji(p['status'])} {method_emoji(p['method'])} ₹{p['amount']:g} "
            f"— {p['status']} ({fmt_date(p['created_at'])})"
            for p in history[:15]
        ]
        text = "🧾 <b>PAYMENT HISTORY</b>\n\n" + "\n".join(lines)
    await safe_edit_or_send(update, text, kb.admin_user_actions_keyboard(telegram_id), parse_mode="HTML")


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

async def admin_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await db.get_member_channel_id()
    verification = await db.get_verification_channel_id()
    text = (
        "🔐 <b>CHANNELS</b>\n\n"
        f"Member Channel ID: <code>{member or 'Not set'}</code>\n"
        f"Verification Channel ID: <code>{verification or 'Not set'}</code>"
    )
    await safe_edit_or_send(update, text, kb.admin_channels_keyboard(), parse_mode="HTML")


async def channel_change_verification_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_state(context, STATE_CHANNEL_VERIFICATION)
    await safe_edit_or_send(
        update,
        "Send the new Verification Channel ID (e.g. -1001234567890).\n"
        "Make sure the bot is an admin in that channel.",
        kb.cancel_keyboard("admin_channels"),
    )


async def channel_change_member_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_state(context, STATE_CHANNEL_MEMBER)
    await safe_edit_or_send(
        update,
        "Send the new Member Channel ID (e.g. -1001234567890).\n"
        "Make sure the bot is an admin in that channel with 'Add Members' / 'Invite via link' permission.",
        kb.cancel_keyboard("admin_channels"),
    )


async def handle_channel_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    state = get_state(context)
    if state not in (STATE_CHANNEL_VERIFICATION, STATE_CHANNEL_MEMBER):
        return False

    raw = update.message.text.strip()
    try:
        channel_id = int(raw)
    except ValueError:
        await update.message.reply_text("⚠️ Invalid channel ID. It should be a number like -1001234567890.")
        return True

    admin_id = update.effective_user.id
    if state == STATE_CHANNEL_VERIFICATION:
        await db.set_setting("verification_channel_id", str(channel_id))
        await db.log_admin_action(admin_id, "CHANGE_VERIFICATION_CHANNEL", str(channel_id))
        await update.message.reply_text("✅ Verification channel updated.")
    else:
        await db.set_setting("member_channel_id", str(channel_id))
        await db.log_admin_action(admin_id, "CHANGE_MEMBER_CHANNEL", str(channel_id))
        await update.message.reply_text("✅ Member channel updated.")

    clear_state(context)
    return True


# ---------------------------------------------------------------------------
# Messages / Settings (welcome message customization)
# ---------------------------------------------------------------------------

async def admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = await db.get_setting("welcome_message", "")
    text = (
        "📝 <b>MESSAGES</b>\n\n"
        f"Current extra welcome text:\n{current or '(none)'}\n\n"
        "Send new text to replace it, or send 'clear' to remove it."
    )
    set_state(context, STATE_WELCOME_MESSAGE)
    await safe_edit_or_send(update, text, kb.cancel_keyboard("admin_menu"), parse_mode="HTML")


async def handle_welcome_message_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if get_state(context) != STATE_WELCOME_MESSAGE:
        return False
    text = update.message.text.strip()
    admin_id = update.effective_user.id
    if text.lower() == "clear":
        await db.set_setting("welcome_message", "")
        await update.message.reply_text("✅ Welcome message cleared.")
    else:
        await db.set_setting("welcome_message", text)
        await update.message.reply_text("✅ Welcome message updated.")
    await db.log_admin_action(admin_id, "UPDATE_WELCOME_MESSAGE", text)
    clear_state(context)
    return True


async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔧 <b>SETTINGS</b>\n\n"
        f"Database: <code>configured</code>\n"
        f"Admin ID: <code>{update.effective_user.id}</code>\n\n"
        "Use PRICE, CHANNELS and MESSAGES sections to configure the bot further."
    )
    await safe_edit_or_send(update, text, kb.admin_back_keyboard(), parse_mode="HTML")
