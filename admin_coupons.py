"""
handlers/admin_coupons.py
Admin coupon management (create/edit/delete/view) plus the user-facing
"enter a coupon code" flow used on the Buy Premium screen.
"""

import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

import database as db
import keyboards as kb
from utils import safe_edit_or_send, set_state, clear_state, get_state, fmt_date

logger = logging.getLogger(__name__)

STATE_COUPON_CODE = "awaiting_coupon_code"
STATE_COUPON_TYPE = "awaiting_coupon_type"
STATE_COUPON_VALUE = "awaiting_coupon_value"
STATE_COUPON_EXPIRY = "awaiting_coupon_expiry"
STATE_COUPON_LIMIT = "awaiting_coupon_limit"
STATE_USER_ENTER_COUPON = "awaiting_user_coupon_entry"


# --- Admin: create coupon (simple multi-step wizard using free text) ---

async def admin_coupons_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_state(context)
    text = "🎟️ <b>COUPONS</b>\n\nChoose an action:"
    await safe_edit_or_send(update, text, kb.admin_coupons_keyboard(), parse_mode="HTML")


async def coupon_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_state(context, STATE_COUPON_CODE, new_coupon={})
    await safe_edit_or_send(update, "Enter the new coupon code (e.g. PREMIUM10):", kb.cancel_keyboard("admin_coupons"))


async def coupon_view_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coupons = await db.get_all_coupons()
    if not coupons:
        text = "🎟️ <b>COUPONS</b>\n\nNo coupons yet."
    else:
        lines = []
        for c in coupons:
            value = f"{c['discount_value']:g}%" if c["discount_type"] == "PERCENT" else f"₹{c['discount_value']:g}"
            expiry = fmt_date(c["expiry"]) if c["expiry"] else "Never"
            limit = c["usage_limit"] if c["usage_limit"] is not None else "∞"
            lines.append(
                f"<b>{c['code']}</b> — {value} OFF | {'ON' if c['active'] else 'OFF'} | "
                f"Used {c['used_count']}/{limit} | Expires: {expiry}"
            )
        text = "🎟️ <b>COUPONS</b>\n\n" + "\n\n".join(lines)
    await safe_edit_or_send(update, text, kb.admin_back_keyboard("admin_coupons"), parse_mode="HTML")


async def coupon_delete_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coupons = await db.get_all_coupons()
    if not coupons:
        await safe_edit_or_send(update, "No coupons to delete.", kb.admin_back_keyboard("admin_coupons"))
        return
    await safe_edit_or_send(update, "Select a coupon to delete:", kb.coupon_pick_keyboard(coupons, "coupon_delete"))


async def coupon_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    admin_id = update.effective_user.id
    await db.delete_coupon(code)
    await db.log_admin_action(admin_id, "DELETE_COUPON", code)
    await update.callback_query.answer("Deleted 🗑️")
    await admin_coupons_menu(update, context)


async def coupon_toggle_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coupons = await db.get_all_coupons()
    if not coupons:
        await safe_edit_or_send(update, "No coupons yet.", kb.admin_back_keyboard("admin_coupons"))
        return
    await safe_edit_or_send(update, "Select a coupon to toggle active/inactive:", kb.coupon_pick_keyboard(coupons, "coupon_toggle"))


async def coupon_toggle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    admin_id = update.effective_user.id
    coupon = await db.get_coupon(code)
    if not coupon:
        await update.callback_query.answer("Coupon not found.", show_alert=True)
        return
    new_state = not bool(coupon["active"])
    await db.set_coupon_active(code, new_state)
    await db.log_admin_action(admin_id, "TOGGLE_COUPON", f"{code} -> {'ON' if new_state else 'OFF'}")
    await update.callback_query.answer(f"{code} is now {'ON' if new_state else 'OFF'}")
    await admin_coupons_menu(update, context)


async def handle_coupon_wizard_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    state = get_state(context)
    if state not in (STATE_COUPON_CODE, STATE_COUPON_TYPE, STATE_COUPON_VALUE,
                      STATE_COUPON_EXPIRY, STATE_COUPON_LIMIT):
        return False

    text = update.message.text.strip()
    new_coupon = context.user_data.setdefault("new_coupon", {})

    if state == STATE_COUPON_CODE:
        if not text or " " in text:
            await update.message.reply_text("⚠️ Invalid code. Use letters/numbers with no spaces.")
            return True
        existing = await db.get_coupon(text)
        if existing:
            await update.message.reply_text("⚠️ A coupon with this code already exists. Try a different code.")
            return True
        new_coupon["code"] = text.upper()
        set_state(context, STATE_COUPON_TYPE, new_coupon=new_coupon)
        await update.message.reply_text("Enter discount type: FIXED or PERCENT")
        return True

    if state == STATE_COUPON_TYPE:
        if text.upper() not in ("FIXED", "PERCENT"):
            await update.message.reply_text("⚠️ Please enter exactly 'FIXED' or 'PERCENT'.")
            return True
        new_coupon["discount_type"] = text.upper()
        set_state(context, STATE_COUPON_VALUE, new_coupon=new_coupon)
        await update.message.reply_text("Enter the discount value (number only, e.g. 10):")
        return True

    if state == STATE_COUPON_VALUE:
        try:
            value = float(text)
            if value <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Enter a positive number.")
            return True
        new_coupon["discount_value"] = value
        set_state(context, STATE_COUPON_EXPIRY, new_coupon=new_coupon)
        await update.message.reply_text("Enter expiry in days from now (or 'none' for no expiry):")
        return True

    if state == STATE_COUPON_EXPIRY:
        if text.lower() == "none":
            new_coupon["expiry"] = None
        else:
            try:
                days = int(text)
                new_coupon["expiry"] = int(time.time()) + days * 86400
            except ValueError:
                await update.message.reply_text("⚠️ Enter a whole number of days, or 'none'.")
                return True
        set_state(context, STATE_COUPON_LIMIT, new_coupon=new_coupon)
        await update.message.reply_text("Enter usage limit (or 'none' for unlimited):")
        return True

    if state == STATE_COUPON_LIMIT:
        if text.lower() == "none":
            new_coupon["usage_limit"] = None
        else:
            try:
                new_coupon["usage_limit"] = int(text)
            except ValueError:
                await update.message.reply_text("⚠️ Enter a whole number, or 'none'.")
                return True

        admin_id = update.effective_user.id
        await db.create_coupon(
            code=new_coupon["code"],
            discount_type=new_coupon["discount_type"],
            discount_value=new_coupon["discount_value"],
            expiry=new_coupon["expiry"],
            usage_limit=new_coupon["usage_limit"],
        )
        await db.log_admin_action(admin_id, "CREATE_COUPON", new_coupon["code"])
        await update.message.reply_text(f"✅ Coupon {new_coupon['code']} created!")
        clear_state(context)
        context.user_data.pop("new_coupon", None)
        return True

    return False


# --- User-facing: enter a coupon on the Buy Premium screen ---

async def enter_coupon_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_state(context, STATE_USER_ENTER_COUPON)
    await safe_edit_or_send(update, "Enter your coupon code:", kb.cancel_keyboard("buy_premium"))


async def remove_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("active_coupon", None)
    await update.callback_query.answer("Coupon removed.")
    price = await db.get_price_inr()
    text = f"💎 <b>BUY PREMIUM</b>\n\n💰 Price: ₹{price:g}\n\nChoose a payment method:"
    await safe_edit_or_send(update, text, kb.buy_choice_keyboard(has_active_coupon=False), parse_mode="HTML")


async def handle_user_coupon_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if get_state(context) != STATE_USER_ENTER_COUPON:
        return False

    code = update.message.text.strip().upper()
    coupon = await db.get_coupon(code)
    clear_state(context)

    if not coupon or not db.validate_coupon(coupon):
        await update.message.reply_text("⚠️ Invalid or expired coupon code.")
        return True

    context.user_data["active_coupon"] = code
    price = await db.get_price_inr()
    discounted = db.apply_discount(price, coupon)
    await update.message.reply_text(
        f"🎟️ Coupon <b>{code}</b> applied!\n\n💰 New price: ₹{discounted:g} (was ₹{price:g})",
        reply_markup=kb.buy_choice_keyboard(has_active_coupon=True),
        parse_mode="HTML",
    )
    return True
