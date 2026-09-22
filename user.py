"""
handlers/user.py
Core user-facing screens: /start home menu, content list, my purchase,
verify access, and help/FAQ.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

import database as db
import keyboards as kb
from utils import safe_edit_or_send, fmt_date, method_emoji, status_emoji

logger = logging.getLogger(__name__)


async def build_home_text(user_first_name: str) -> str:
    price = await db.get_price_inr()
    welcome_extra = await db.get_setting("welcome_message", "")
    extra = f"\n{welcome_extra}\n" if welcome_extra else ""
    return (
        "🔐 <b>PREMIUM ACCESS</b>\n\n"
        f"Welcome, {user_first_name}! 👋\n\n"
        "💎 Exclusive premium content\n"
        "📦 Regular content updates\n"
        "♾️ Lifetime access\n"
        f"{extra}\n"
        f"💰 Current Price: ₹{price:g}\n\n"
        "Choose an option below:"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.upsert_user(user.id, user.username, user.first_name)
    text = await build_home_text(user.first_name or "there")
    await update.message.reply_text(text, reply_markup=kb.home_keyboard(), parse_mode="HTML")


async def go_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = await build_home_text(user.first_name or "there")
    await safe_edit_or_send(update, text, kb.home_keyboard(), parse_mode="HTML")


async def content_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = await db.get_content_list()
    if items:
        lines = "\n".join(f"{it['position']:02d}. {it['title']}" for it in items)
    else:
        lines = "No content items yet — check back soon!"
    text = f"📦 <b>PREMIUM CONTENT</b>\n\n{lines}\n\nContent is updated regularly."
    await safe_edit_or_send(update, text, kb.content_list_keyboard(), parse_mode="HTML")


async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = await db.get_price_inr()
    coupon_code = context.user_data.get("active_coupon")
    note = ""
    if coupon_code:
        coupon = await db.get_coupon(coupon_code)
        if coupon and db.validate_coupon(coupon):
            discounted = db.apply_discount(price, coupon)
            note = f"\n🎟️ Coupon <b>{coupon_code}</b> applied — ₹{discounted:g} (was ₹{price:g})"
        else:
            context.user_data.pop("active_coupon", None)
            coupon_code = None
    text = f"💎 <b>BUY PREMIUM</b>\n\n💰 Price: ₹{price:g}{note}\n\nChoose a payment method:"
    await safe_edit_or_send(update, text, kb.buy_choice_keyboard(has_active_coupon=bool(coupon_code)), parse_mode="HTML")


async def my_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    payment = await db.get_latest_payment_for_user(user.id)
    user_row = await db.get_user(user.id)
    price = await db.get_price_inr()

    if not payment or (user_row and user_row["status"] not in ("PAID",) and payment["status"] not in ("PENDING",)):
        if not payment:
            text = (
                "👤 <b>MY PURCHASE</b>\n\n"
                "You haven't made a purchase yet.\n\n"
                "Tap 💎 BUY PREMIUM from the home menu to get started."
            )
            await safe_edit_or_send(update, text, kb.back_keyboard("home"), parse_mode="HTML")
            return

    status = payment["status"]
    method = payment["method"]

    if status == "PAID":
        invite_link = None
        member_channel_id = await db.get_member_channel_id()
        if member_channel_id:
            try:
                link_obj = await context.bot.create_chat_invite_link(
                    chat_id=member_channel_id, member_limit=1, creates_join_request=False
                )
                invite_link = link_obj.invite_link
            except TelegramError as e:
                logger.warning("Could not create invite link for user %s: %s", user.id, e)
        text = (
            "👤 <b>MY PURCHASE</b>\n\n"
            "Status: ✅ ACTIVE\n"
            "Plan: 💎 Lifetime Premium\n"
            f"Amount: {'⭐' if method == 'STARS' else '₹'}{payment['amount']:g}\n"
            f"Method: {method_emoji(method)} {'Telegram Stars' if method == 'STARS' else 'UPI'}\n"
            f"Purchased: {fmt_date(payment['verified_at'] or payment['created_at'])}"
        )
        await safe_edit_or_send(
            update, text, kb.my_purchase_keyboard(has_invite=bool(invite_link), invite_link=invite_link),
            parse_mode="HTML",
        )
    elif status == "PENDING":
        text = (
            "👤 <b>MY PURCHASE</b>\n\n"
            "Status: ⏳ PENDING VERIFICATION\n"
            f"Method: {method_emoji(method)} {'UPI' if method == 'UPI' else 'Telegram Stars'}\n"
            f"Amount: ₹{payment['amount']:g}\n"
            f"UTR: {payment.get('utr') or '-'}"
        )
        await safe_edit_or_send(update, text, kb.back_keyboard("home"), parse_mode="HTML")
    elif status == "REJECTED":
        text = (
            "👤 <b>MY PURCHASE</b>\n\n"
            "Status: ❌ REJECTED\n"
            f"Reason: {payment.get('transaction_reference') or 'Not specified'}\n\n"
            "If you believe this was a mistake, contact support, or try again from 💎 BUY PREMIUM."
        )
        await safe_edit_or_send(update, text, kb.back_keyboard("home"), parse_mode="HTML")
    else:
        text = (
            "👤 <b>MY PURCHASE</b>\n\n"
            "You don't have an active purchase yet.\n\n"
            f"💰 Current Price: ₹{price:g}"
        )
        await safe_edit_or_send(update, text, kb.back_keyboard("home"), parse_mode="HTML")


async def join_member_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback for when we couldn't pre-generate an invite link (e.g. channel not
    yet configured, or the bot lacks permission)."""
    user = update.effective_user
    if not await db.is_user_paid(user.id):
        await update.callback_query.answer("You don't have active premium access yet.", show_alert=True)
        return

    member_channel_id = await db.get_member_channel_id()
    if not member_channel_id:
        await update.callback_query.answer("The member channel isn't configured yet. Please contact support.", show_alert=True)
        return

    try:
        link_obj = await context.bot.create_chat_invite_link(
            chat_id=member_channel_id, member_limit=1, creates_join_request=False
        )
        await update.callback_query.answer()
        await context.bot.send_message(
            chat_id=user.id,
            text=f"👥 Here's your one-time invite link:\n{link_obj.invite_link}",
        )
    except TelegramError as e:
        logger.warning("Could not create invite link for user %s: %s", user.id, e)
        await update.callback_query.answer(
            "Couldn't generate an invite link right now. Please contact support.", show_alert=True
        )


async def payment_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    history = await db.get_payment_history(user.id)
    if not history:
        text = "🧾 <b>PAYMENT DETAILS</b>\n\nNo payment records found."
    else:
        lines = []
        for p in history[:10]:
            lines.append(
                f"{status_emoji(p['status'])} {method_emoji(p['method'])} "
                f"₹{p['amount']:g} — {p['status']} ({fmt_date(p['created_at'])})"
            )
        text = "🧾 <b>PAYMENT DETAILS</b>\n\n" + "\n".join(lines)
    await safe_edit_or_send(update, text, kb.back_keyboard("my_purchase"), parse_mode="HTML")


async def verify_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_paid = await db.is_user_paid(user.id)
    verification_channel_id = await db.get_verification_channel_id()

    member_note = ""
    if verification_channel_id:
        try:
            member = await context.bot.get_chat_member(verification_channel_id, user.id)
            in_channel = member.status not in ("left", "kicked")
            member_note = "\n🔔 Verification channel: " + ("✅ Joined" if in_channel else "❌ Not joined")
        except TelegramError:
            member_note = "\n🔔 Verification channel: ⚠️ Unable to check"

    text = (
        "🔐 <b>VERIFY ACCESS</b>\n\n"
        f"Premium status: {'✅ ACTIVE' if is_paid else '❌ NOT ACTIVE'}"
        f"{member_note}"
    )
    await safe_edit_or_send(update, text, kb.back_keyboard("home"), parse_mode="HTML")


async def help_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "❓ <b>HELP</b>\n\n"
        "💳 <b>How do I pay?</b>\n"
        "Tap 💎 BUY PREMIUM and choose Telegram Stars or UPI.\n\n"
        "📦 <b>What do I get?</b>\n"
        "Access to our private premium channel and its full content library.\n\n"
        "⭐ <b>How does Stars payment work?</b>\n"
        "Pay instantly inside Telegram — access is granted automatically once payment is confirmed.\n\n"
        "🇮🇳 <b>How does UPI verification work?</b>\n"
        "Send a screenshot + UTR, then our admin manually confirms it.\n\n"
        "🔐 <b>How do I join the member channel?</b>\n"
        "Once your payment is verified, use the JOIN MEMBER CHANNEL button under 👤 MY PURCHASE.\n\n"
        "⏳ <b>How long does UPI verification take?</b>\n"
        "Usually within a few hours.\n\n"
        "📞 <b>Contact support</b>\n"
        "Message the admin directly if you need help."
    )
    await safe_edit_or_send(update, text, kb.back_keyboard("home"), parse_mode="HTML")
