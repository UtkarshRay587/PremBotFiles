"""
Main.py
Entry point for the Premium Telegram Sales & Private Channel Access Bot.

Wires together configuration, the database, and all handler modules, then
starts long-polling. Run with:

    python main.py
"""

import logging
import sys

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    ChatJoinRequestHandler,
    ContextTypes,
    filters,
)

import config
import database as db
from utils import is_admin

import user as h_user
import payments_stars as h_stars
import payments_upi as h_upi
import admin as h_admin
import admin_content as h_content
import admin_coupons as h_coupons
import admin_broadcast as h_broadcast
import join_requests as h_join

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Keep noisy libraries quieter
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("premium_bot")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await h_user.start(update, context)


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return
    await h_admin.admin_menu(update, context)


# ---------------------------------------------------------------------------
# Callback query router
# ---------------------------------------------------------------------------

SELF_ANSWERING_ROUTES = {"remove_coupon", "broadcast_confirm", "broadcast_cancel", "join_member_channel"}

ADMIN_ONLY_PREFIXES = (
    "admin_", "content_", "coupon_", "price_change", "channel_change",
    "grant_access", "revoke_access", "approve_payment", "reject_payment",
    "view_user_by_payment", "admin_user_history", "broadcast_",
)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    user_id = update.effective_user.id

    # Centralized admin gate: anything admin-related requires is_admin().
    # "content_list" is the user-facing content screen, not an admin route,
    # so it's explicitly excluded from the "content_" prefix match below.
    is_admin_route = data != "content_list" and data.startswith(ADMIN_ONLY_PREFIXES)
    if is_admin_route and not is_admin(user_id):
        await query.answer("⛔ Not authorized.", show_alert=True)
        return

    try:
        # --- Simple, no-argument routes ---
        simple_routes = {
            "home": h_user.go_home,
            "content_list": h_user.content_list,
            "buy_premium": h_user.buy_premium,
            "my_purchase": h_user.my_purchase,
            "payment_history": h_user.payment_history,
            "verify_access": h_user.verify_access,
            "join_member_channel": h_user.join_member_channel,
            "help": h_user.help_screen,
            "buy_stars": h_stars.buy_stars,
            "buy_upi": h_upi.buy_upi,
            "submit_upi_payment": h_upi.submit_upi_payment,
            "enter_coupon": h_coupons.enter_coupon_start,
            "remove_coupon": h_coupons.remove_coupon,
            "admin_menu": h_admin.admin_menu,
            "admin_price": h_admin.admin_price,
            "price_change_inr": h_admin.price_change_inr_start,
            "price_change_stars": h_admin.price_change_stars_start,
            "admin_stats": h_admin.admin_stats,
            "admin_users": h_admin.admin_users,
            "user_search": h_admin.user_search_start,
            "admin_channels": h_admin.admin_channels,
            "channel_change_verification": h_admin.channel_change_verification_start,
            "channel_change_member": h_admin.channel_change_member_start,
            "admin_messages": h_admin.admin_messages,
            "admin_settings": h_admin.admin_settings,
            "admin_content": h_content.admin_content_menu,
            "content_view": h_content.content_view,
            "content_add": h_content.content_add_start,
            "content_edit_pick": h_content.content_edit_pick,
            "content_delete_pick": h_content.content_delete_pick,
            "content_moveup_pick": h_content.content_moveup_pick,
            "content_movedown_pick": h_content.content_movedown_pick,
            "admin_coupons": h_coupons.admin_coupons_menu,
            "coupon_create": h_coupons.coupon_create_start,
            "coupon_view_all": h_coupons.coupon_view_all,
            "coupon_delete_pick": h_coupons.coupon_delete_pick,
            "coupon_toggle_pick": h_coupons.coupon_toggle_pick,
            "admin_broadcast": h_broadcast.admin_broadcast_start,
            "broadcast_confirm": h_broadcast.broadcast_confirm,
            "broadcast_cancel": h_broadcast.broadcast_cancel,
            "admin_payments": h_admin.admin_stats,  # payments overview folds into stats/pending list
        }
        if data in simple_routes:
            # A few handlers answer the callback query themselves (e.g. to show a
            # custom alert/toast), so we must not pre-answer for those or the
            # user's toast text would be swallowed by our generic ack.
            if data not in SELF_ANSWERING_ROUTES:
                await query.answer()
            await simple_routes[data](update, context)
            return

        # --- Parameterized routes: "action:value" ---
        if ":" in data:
            action, _, value = data.partition(":")

            if action == "approve_payment":
                await h_upi.approve_payment(update, context, int(value))
                return
            if action == "reject_payment":
                await h_upi.reject_payment_start(update, context, int(value))
                return
            if action == "view_user_by_payment":
                payment = await db.get_payment(int(value))
                if payment:
                    await query.answer()
                    await h_admin.view_user_card(update, context, payment["telegram_id"])
                else:
                    await query.answer("Payment not found.", show_alert=True)
                return
            if action == "grant_access":
                await h_admin.grant_access(update, context, int(value))
                return
            if action == "revoke_access":
                await h_admin.revoke_access(update, context, int(value))
                return
            if action == "admin_user_history":
                await query.answer()
                await h_admin.admin_user_history(update, context, int(value))
                return
            if action == "content_edit":
                await query.answer()
                await h_content.content_edit_start(update, context, int(value))
                return
            if action == "content_delete":
                await h_content.content_delete_confirm(update, context, int(value))
                return
            if action == "content_moveup":
                await h_content.content_move(update, context, int(value), "up")
                return
            if action == "content_movedown":
                await h_content.content_move(update, context, int(value), "down")
                return
            if action == "coupon_delete":
                await h_coupons.coupon_delete_confirm(update, context, value)
                return
            if action == "coupon_toggle":
                await h_coupons.coupon_toggle_confirm(update, context, value)
                return

        # Unknown callback
        await query.answer()
    except Exception:
        logger.exception("Error handling callback data=%s from user=%s", data, user_id)
        try:
            await query.answer("⚠️ Something went wrong. Please try again.", show_alert=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Generic text dispatcher — routes free-text input to whichever handler is
# currently "awaiting" it, based on context.user_data state.
# ---------------------------------------------------------------------------

TEXT_HANDLERS_IN_PRIORITY_ORDER = [
    h_upi.handle_utr_text,
    h_upi.handle_reject_reason_text,
    h_admin.handle_price_text,
    h_admin.handle_user_search_text,
    h_admin.handle_channel_text,
    h_admin.handle_welcome_message_text,
    h_content.handle_content_text,
    h_coupons.handle_coupon_wizard_text,
    h_coupons.handle_user_coupon_text,
    h_broadcast.handle_broadcast_text,
]


async def generic_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for handler in TEXT_HANDLERS_IN_PRIORITY_ORDER:
        try:
            handled = await handler(update, context)
        except Exception:
            logger.exception("Error in text handler %s", handler)
            handled = True
            await update.message.reply_text("⚠️ Something went wrong processing that. Please try again.")
        if handled:
            return
    # No active state matched this text — ignore quietly (avoid noisy replies to random chatter).


async def generic_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await h_upi.handle_photo(update, context)
    except Exception:
        logger.exception("Error handling photo from user %s", update.effective_user.id)


# ---------------------------------------------------------------------------
# Global error handler
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception while processing update: %s", update, exc_info=context.error)


# ---------------------------------------------------------------------------
# App bootstrap
# ---------------------------------------------------------------------------

async def post_init(application: Application):
    await db.init_db()
    logger.info("Bot started successfully.")


def main():
    problems = config.validate_config()
    if problems:
        for p in problems:
            logger.error(p)
        sys.exit(1)

    application = ApplicationBuilder().token(config.BOT_TOKEN).post_init(post_init).build()

    # Commands
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("admin", cmd_admin))

    # Callback queries (all inline button presses)
    application.add_handler(CallbackQueryHandler(callback_router))

    # Telegram Stars payments
    application.add_handler(PreCheckoutQueryHandler(h_stars.precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, h_stars.successful_payment_callback))

    # UPI screenshot + free text (must come after successful_payment filter above)
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, generic_photo_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generic_text_handler))

    # Join request protection for the private member channel
    application.add_handler(ChatJoinRequestHandler(h_join.handle_join_request))

    # Errors
    application.add_error_handler(error_handler)

    logger.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
