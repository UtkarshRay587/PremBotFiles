"""
handlers/payments_upi.py
UPI manual-verification flow: screenshot + UTR submitted by the user,
then approved or rejected by the admin. Never auto-marks UPI as paid.
"""

import logging
import time

from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

import config
import database as db
import keyboards as kb
from utils import safe_edit_or_send, set_state, clear_state, get_state, fmt_datetime

logger = logging.getLogger(__name__)

STATE_AWAITING_SCREENSHOT = "awaiting_upi_screenshot"
STATE_AWAITING_UTR = "awaiting_upi_utr"
STATE_AWAITING_REJECT_REASON = "awaiting_reject_reason"


async def _discounted_price(context: ContextTypes.DEFAULT_TYPE) -> tuple[float, str | None]:
    price = await db.get_price_inr()
    coupon_code = context.user_data.get("active_coupon")
    if coupon_code:
        coupon = await db.get_coupon(coupon_code)
        if coupon and db.validate_coupon(coupon):
            return db.apply_discount(price, coupon), coupon_code
        context.user_data.pop("active_coupon", None)
    return price, None


async def buy_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price, coupon_code = await _discounted_price(context)
    upi_id = await db.get_setting("upi_id", config.UPI_ID)
    coupon_note = f"\n🎟️ Coupon applied: {coupon_code}" if coupon_code else ""
    text = (
        "🇮🇳 <b>UPI PAYMENT</b>\n\n"
        f"Amount: ₹{price:g}{coupon_note}\n\n"
        f"UPI ID:\n<code>{upi_id}</code>\n\n"
        "1️⃣ Pay the exact amount.\n"
        "2️⃣ Take a screenshot after payment.\n"
        "3️⃣ Send the screenshot here.\n"
        "4️⃣ Send your UTR / transaction ID.\n\n"
        "Your payment will be manually verified by the admin."
    )
    await safe_edit_or_send(update, text, kb.upi_instructions_keyboard(), parse_mode="HTML")


async def submit_upi_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_state(context, STATE_AWAITING_SCREENSHOT)
    text = "📸 Please send your <b>payment screenshot</b> now."
    await safe_edit_or_send(update, text, kb.back_keyboard("buy_upi"), parse_mode="HTML")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generic photo handler — only acts if the user is in the screenshot-awaiting state."""
    if get_state(context) != STATE_AWAITING_SCREENSHOT:
        return  # not relevant to UPI flow right now

    photo = update.message.photo[-1]
    context.user_data["upi_screenshot_file_id"] = photo.file_id
    set_state(context, STATE_AWAITING_UTR)
    await update.message.reply_text(
        "🔖 Please send your UTR / Transaction ID.",
        reply_markup=kb.back_keyboard("buy_upi"),
    )


async def handle_utr_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generic text handler entry point — only acts if state is awaiting UTR."""
    if get_state(context) != STATE_AWAITING_UTR:
        return False  # let other text handlers process it

    utr = update.message.text.strip()
    user = update.effective_user

    if not utr or len(utr) < 4:
        await update.message.reply_text("That doesn't look like a valid UTR. Please send a valid UTR / transaction ID.")
        return True

    if await db.utr_exists(utr):
        await update.message.reply_text(
            "⚠️ This UTR has already been submitted. If you believe this is an error, contact support."
        )
        return True

    screenshot_file_id = context.user_data.get("upi_screenshot_file_id")
    price, coupon_code = await _discounted_price(context)

    payment_id = await db.create_payment(
        telegram_id=user.id,
        method="UPI",
        amount=price,
        currency="INR",
        status="PENDING",
        utr=utr,
        screenshot_file_id=screenshot_file_id,
        coupon_code=coupon_code,
    )
    clear_state(context)
    context.user_data.pop("upi_screenshot_file_id", None)

    await update.message.reply_text(
        "⏳ <b>PAYMENT SUBMITTED</b>\n\n"
        "Your payment is waiting for verification.\n"
        "You'll receive a notification after the admin reviews it.\n\n"
        "Status: PENDING",
        reply_markup=kb.back_keyboard("home"),
        parse_mode="HTML",
    )

    # Notify admin
    if config.ADMIN_ID:
        caption = (
            "🔔 <b>NEW UPI PAYMENT</b>\n\n"
            f"👤 User: @{user.username or 'N/A'}\n"
            f"🆔 Telegram ID: {user.id}\n\n"
            f"💰 Amount: ₹{price:g}\n"
            f"🔖 UTR: {utr}\n\n"
            f"⏰ Submitted: {fmt_datetime(int(time.time()))}"
        )
        try:
            if screenshot_file_id:
                await context.bot.send_photo(
                    chat_id=config.ADMIN_ID,
                    photo=screenshot_file_id,
                    caption=caption,
                    reply_markup=kb.upi_admin_review_keyboard(payment_id),
                    parse_mode="HTML",
                )
            else:
                await context.bot.send_message(
                    chat_id=config.ADMIN_ID,
                    text=caption + "\n\n(No screenshot was attached.)",
                    reply_markup=kb.upi_admin_review_keyboard(payment_id),
                    parse_mode="HTML",
                )
        except TelegramError as e:
            logger.error("Failed to notify admin of new UPI payment %s: %s", payment_id, e)

    logger.info("UPI payment %s submitted by user %s, UTR=%s", payment_id, user.id, utr)
    return True


async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, payment_id: int):
    query = update.callback_query
    admin_id = update.effective_user.id

    payment = await db.get_payment(payment_id)
    if not payment:
        await query.answer("Payment not found.", show_alert=True)
        return
    if payment["status"] != "PENDING":
        await query.answer(f"Already {payment['status']}.", show_alert=True)
        return

    changed = await db.mark_payment_paid(payment_id, verified_by=admin_id)
    if not changed:
        await query.answer("This payment was already processed by someone else.", show_alert=True)
        return

    await db.set_user_status(payment["telegram_id"], "PAID")
    if payment.get("coupon_code"):
        await db.increment_coupon_usage(payment["coupon_code"])
    await db.log_admin_action(admin_id, "APPROVE_UPI_PAYMENT", f"payment_id={payment_id}")

    await query.answer("Approved ✅")
    try:
        if query.message.photo:
            await query.edit_message_caption(
                caption=(query.message.caption or "") + "\n\n✅ APPROVED",
            )
        else:
            await query.edit_message_text((query.message.text or "") + "\n\n✅ APPROVED")
    except TelegramError:
        pass

    try:
        await context.bot.send_message(
            chat_id=payment["telegram_id"],
            text="✅ <b>PAYMENT VERIFIED</b>\n\nYour premium access has been activated!",
            reply_markup=kb.join_channel_keyboard(),
            parse_mode="HTML",
        )
    except TelegramError as e:
        logger.warning("Could not notify user %s of approval: %s", payment["telegram_id"], e)

    logger.info("Admin %s approved UPI payment %s", admin_id, payment_id)


async def reject_payment_start(update: Update, context: ContextTypes.DEFAULT_TYPE, payment_id: int):
    query = update.callback_query
    payment = await db.get_payment(payment_id)
    if not payment or payment["status"] != "PENDING":
        await query.answer("Payment is not pending.", show_alert=True)
        return
    set_state(context, STATE_AWAITING_REJECT_REASON, reject_payment_id=payment_id)
    await query.answer()
    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text="Enter an optional rejection reason (or send 'skip'):",
        reply_markup=kb.cancel_keyboard("admin_menu"),
    )


async def handle_reject_reason_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if get_state(context) != STATE_AWAITING_REJECT_REASON:
        return False

    admin_id = update.effective_user.id
    payment_id = context.user_data.get("reject_payment_id")
    reason = update.message.text.strip()
    if reason.lower() == "skip":
        reason = "Not specified"

    payment = await db.get_payment(payment_id)
    clear_state(context)
    context.user_data.pop("reject_payment_id", None)

    if not payment or payment["status"] != "PENDING":
        await update.message.reply_text("This payment is no longer pending.")
        return True

    changed = await db.mark_payment_rejected(payment_id, verified_by=admin_id, reason=reason)
    if not changed:
        await update.message.reply_text("This payment was already processed.")
        return True

    await db.log_admin_action(admin_id, "REJECT_UPI_PAYMENT", f"payment_id={payment_id}, reason={reason}")
    await update.message.reply_text(f"❌ Payment #{payment_id} rejected.")

    try:
        await context.bot.send_message(
            chat_id=payment["telegram_id"],
            text=(
                "❌ <b>PAYMENT REJECTED</b>\n\n"
                f"Reason:\n{reason}\n\n"
                "If you believe this was a mistake, contact support."
            ),
            parse_mode="HTML",
        )
    except TelegramError as e:
        logger.warning("Could not notify user %s of rejection: %s", payment["telegram_id"], e)

    logger.info("Admin %s rejected UPI payment %s (reason=%s)", admin_id, payment_id, reason)
    return True
