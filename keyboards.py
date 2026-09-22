"""
keyboards.py
Centralized inline keyboard builders so button layouts stay consistent
and easy to change in one place.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def home_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 CONTENT LIST", callback_data="content_list")],
        [InlineKeyboardButton("💎 BUY PREMIUM", callback_data="buy_premium")],
        [InlineKeyboardButton("👤 MY PURCHASE", callback_data="my_purchase")],
        [InlineKeyboardButton("🔐 VERIFY ACCESS", callback_data="verify_access")],
        [InlineKeyboardButton("❓ HELP", callback_data="help")],
    ])


def back_keyboard(target="home"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK", callback_data=target)]])


def content_list_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 GET PREMIUM", callback_data="buy_premium")],
        [InlineKeyboardButton("🔙 BACK", callback_data="home")],
    ])


def buy_choice_keyboard(has_active_coupon: bool = False):
    rows = [
        [InlineKeyboardButton("⭐ Telegram Stars", callback_data="buy_stars")],
        [InlineKeyboardButton("🇮🇳 UPI", callback_data="buy_upi")],
    ]
    if has_active_coupon:
        rows.append([InlineKeyboardButton("🎟️ Remove Coupon", callback_data="remove_coupon")])
    else:
        rows.append([InlineKeyboardButton("🎟️ Have a Coupon?", callback_data="enter_coupon")])
    rows.append([InlineKeyboardButton("🔙 BACK", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def upi_instructions_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 SUBMIT PAYMENT", callback_data="submit_upi_payment")],
        [InlineKeyboardButton("🔙 BACK", callback_data="buy_premium")],
    ])


def join_channel_keyboard(invite_link: str = None):
    if invite_link:
        return InlineKeyboardMarkup([[InlineKeyboardButton("👥 JOIN MEMBER CHANNEL", url=invite_link)]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("👥 JOIN MEMBER CHANNEL", callback_data="join_member_channel")]])


def my_purchase_keyboard(has_invite: bool = False, invite_link: str = None):
    rows = []
    if has_invite:
        rows.append([InlineKeyboardButton("👥 MEMBER CHANNEL", url=invite_link)] if invite_link
                     else [InlineKeyboardButton("👥 MEMBER CHANNEL", callback_data="join_member_channel")])
    rows.append([InlineKeyboardButton("🧾 PAYMENT DETAILS", callback_data="payment_history")])
    rows.append([InlineKeyboardButton("🔙 BACK", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def upi_admin_review_keyboard(payment_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_payment:{payment_id}"),
            InlineKeyboardButton("❌ REJECT", callback_data=f"reject_payment:{payment_id}"),
        ],
        [InlineKeyboardButton("👤 VIEW USER", callback_data=f"view_user_by_payment:{payment_id}")],
    ])


# --- Admin panel ---

def admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 CONTENT", callback_data="admin_content"),
         InlineKeyboardButton("💰 PRICE", callback_data="admin_price")],
        [InlineKeyboardButton("💳 PAYMENTS", callback_data="admin_payments"),
         InlineKeyboardButton("👥 USERS", callback_data="admin_users")],
        [InlineKeyboardButton("📊 STATISTICS", callback_data="admin_stats"),
         InlineKeyboardButton("🎟️ COUPONS", callback_data="admin_coupons")],
        [InlineKeyboardButton("📢 BROADCAST", callback_data="admin_broadcast"),
         InlineKeyboardButton("🔐 CHANNELS", callback_data="admin_channels")],
        [InlineKeyboardButton("📝 MESSAGES", callback_data="admin_messages"),
         InlineKeyboardButton("🔧 SETTINGS", callback_data="admin_settings")],
    ])


def admin_back_keyboard(target="admin_menu"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK", callback_data=target)]])


def admin_content_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ ADD", callback_data="content_add"),
         InlineKeyboardButton("📋 VIEW", callback_data="content_view")],
        [InlineKeyboardButton("✏️ EDIT", callback_data="content_edit_pick"),
         InlineKeyboardButton("🗑️ DELETE", callback_data="content_delete_pick")],
        [InlineKeyboardButton("🔼 MOVE UP", callback_data="content_moveup_pick"),
         InlineKeyboardButton("🔽 MOVE DOWN", callback_data="content_movedown_pick")],
        [InlineKeyboardButton("🔙 BACK", callback_data="admin_menu")],
    ])


def content_pick_keyboard(items, action_prefix):
    rows = [
        [InlineKeyboardButton(f"{it['position']:02d}. {it['title']}", callback_data=f"{action_prefix}:{it['id']}")]
        for it in items
    ]
    rows.append([InlineKeyboardButton("🔙 BACK", callback_data="admin_content")])
    return InlineKeyboardMarkup(rows)


def admin_price_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 CHANGE INR PRICE", callback_data="price_change_inr")],
        [InlineKeyboardButton("⭐ CHANGE STARS PRICE", callback_data="price_change_stars")],
        [InlineKeyboardButton("🔙 BACK", callback_data="admin_menu")],
    ])


def admin_users_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 SEARCH USER", callback_data="user_search")],
        [InlineKeyboardButton("🔙 BACK", callback_data="admin_menu")],
    ])


def admin_user_actions_keyboard(telegram_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Grant Access", callback_data=f"grant_access:{telegram_id}"),
         InlineKeyboardButton("🚫 Revoke Access", callback_data=f"revoke_access:{telegram_id}")],
        [InlineKeyboardButton("🧾 Payment History", callback_data=f"admin_user_history:{telegram_id}")],
        [InlineKeyboardButton("🔙 BACK", callback_data="admin_users")],
    ])


def admin_coupons_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ CREATE", callback_data="coupon_create"),
         InlineKeyboardButton("📋 VIEW ALL", callback_data="coupon_view_all")],
        [InlineKeyboardButton("🗑️ DELETE", callback_data="coupon_delete_pick"),
         InlineKeyboardButton("🔁 TOGGLE ACTIVE", callback_data="coupon_toggle_pick")],
        [InlineKeyboardButton("🔙 BACK", callback_data="admin_menu")],
    ])


def coupon_pick_keyboard(coupons, action_prefix):
    rows = [
        [InlineKeyboardButton(f"{c['code']} ({'ON' if c['active'] else 'OFF'})",
                               callback_data=f"{action_prefix}:{c['code']}")]
        for c in coupons
    ]
    rows.append([InlineKeyboardButton("🔙 BACK", callback_data="admin_coupons")])
    return InlineKeyboardMarkup(rows)


def admin_channels_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Change Verification Channel", callback_data="channel_change_verification")],
        [InlineKeyboardButton("✏️ Change Member Channel", callback_data="channel_change_member")],
        [InlineKeyboardButton("🔙 BACK", callback_data="admin_menu")],
    ])


def confirm_broadcast_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ SEND", callback_data="broadcast_confirm"),
         InlineKeyboardButton("❌ CANCEL", callback_data="broadcast_cancel")],
    ])


def cancel_keyboard(target="admin_menu"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ CANCEL", callback_data=target)]])
