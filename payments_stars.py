"""
handlers/payments_stars.py
Telegram Stars (XTR) digital-goods payment flow.

Access is granted ONLY after Telegram confirms a successful_payment update —
never merely because the user opened the invoice or tapped pay.
"""

import logging
import secrets

from telegram import Update, LabeledPrice
from telegram.ext import ContextTypes

import config
import database as db
import keyboards as kb

logger = logging.getLogger(__name__)

PAYLOAD_PREFIX = "premium_stars"


async def buy_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a Telegram Stars invoice for the current premium price."""
    user = update.effective_user
    stars_price = await db.get_price_stars()

    coupon_code = context.user_data.get("active_coupon")
    final_price = stars_price
    if coupon_code:
        coupon = await db.get_coupon(coupon_code)
        if coupon and db.validate_coupon(coupon):
            final_price = int(db.apply_discount(stars_price, coupon))
        else:
            context.user_data.pop("active_coupon", None)
            coupon_code = None

    # Unique, unguessable nonce so the payload can't be replayed/forged, plus the
    # user id so we can double-check the payer in successful_payment.
    nonce = secrets.token_hex(8)
    payload = f"{PAYLOAD_PREFIX}:{user.id}:{nonce}"
    context.user_data["stars_payload"] = payload

    title = "Premium Access"
    description = "Lifetime access to the premium channel and all content."

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",  # Not used for Telegram Stars digital goods
        currency=config.STARS_CURRENCY,
        prices=[LabeledPrice(label=title, amount=final_price)],
    )
    logger.info("Sent Stars invoice to user %s for %s XTR (payload=%s)", user.id, final_price, payload)


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Answer Telegram's pre-checkout query. Must respond within 10 seconds."""
    query = update.pre_checkout_query
    payload = query.invoice_payload or ""

    valid = (
        payload.startswith(f"{PAYLOAD_PREFIX}:")
        and payload.split(":")[1].isdigit()
        and int(payload.split(":")[1]) == query.from_user.id
        and query.currency == config.STARS_CURRENCY
        and query.total_amount > 0
    )

    if valid:
        await query.answer(ok=True)
    else:
        logger.warning("Rejected pre-checkout for user %s, payload=%s", query.from_user.id, payload)
        await query.answer(ok=False, error_message="This payment could not be verified. Please try again.")


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Telegram's confirmation that a Stars payment actually succeeded."""
    sp = update.message.successful_payment
    user = update.effective_user

    payload = sp.invoice_payload or ""
    parts = payload.split(":")
    payload_valid = (
        len(parts) == 3
        and parts[0] == PAYLOAD_PREFIX
        and parts[1].isdigit()
        and int(parts[1]) == user.id
    )
    currency_valid = sp.currency == config.STARS_CURRENCY
    amount_valid = sp.total_amount > 0
    charge_id = sp.telegram_payment_charge_id

    if not (payload_valid and currency_valid and amount_valid and charge_id):
        logger.error(
            "REJECTED a successful_payment that failed verification! user=%s payload=%s currency=%s amount=%s",
            user.id, payload, sp.currency, sp.total_amount,
        )
        await update.message.reply_text(
            "⚠️ We couldn't verify this payment automatically. Please contact support with your "
            "payment receipt and we'll resolve it manually."
        )
        return

    # Duplicate-processing protection: telegram_payment_charge_id is unique per payment.
    if await db.transaction_reference_exists(charge_id):
        logger.warning("Duplicate Stars payment charge_id ignored: %s (user %s)", charge_id, user.id)
        await update.message.reply_text("This payment has already been processed. Your access is active.")
        return

    payment_id = await db.create_payment(
        telegram_id=user.id,
        method="STARS",
        amount=sp.total_amount,
        currency=sp.currency,
        status="PAID",
        transaction_reference=charge_id,
    )
    await db.mark_payment_paid(payment_id, verified_by=None, transaction_reference=charge_id)
    await db.set_user_status(user.id, "PAID")
    context.user_data.pop("active_coupon", None)

    logger.info("Stars payment verified for user %s: %s XTR, charge_id=%s", user.id, sp.total_amount, charge_id)

    await update.message.reply_text(
        "✅ <b>PAYMENT VERIFIED!</b>\n\nYour premium access is now active.",
        reply_markup=kb.join_channel_keyboard(),
        parse_mode="HTML",
    )
