"""
handlers/admin_content.py
Admin management of the premium content list: add, edit, delete, reorder.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import database as db
import keyboards as kb
from utils import safe_edit_or_send, set_state, clear_state, get_state

logger = logging.getLogger(__name__)

STATE_ADD_CONTENT = "awaiting_add_content"
STATE_EDIT_CONTENT = "awaiting_edit_content"


async def admin_content_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_state(context)
    text = "📦 <b>CONTENT MANAGEMENT</b>\n\nChoose an action:"
    await safe_edit_or_send(update, text, kb.admin_content_menu_keyboard(), parse_mode="HTML")


async def content_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = await db.get_content_list()
    if not items:
        text = "📦 <b>PREMIUM CONTENT</b>\n\n(empty)"
    else:
        lines = "\n".join(f"{it['position']:02d}. {it['title']}" for it in items)
        text = f"📦 <b>PREMIUM CONTENT</b>\n\n{lines}"
    await safe_edit_or_send(update, text, kb.admin_back_keyboard("admin_content"), parse_mode="HTML")


async def content_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_state(context, STATE_ADD_CONTENT)
    await safe_edit_or_send(update, "Enter content title:\n\nExample:\n🎬 500+ Premium Presets",
                             kb.cancel_keyboard("admin_content"))


async def content_edit_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = await db.get_content_list()
    if not items:
        await safe_edit_or_send(update, "No content to edit yet.", kb.admin_back_keyboard("admin_content"))
        return
    await safe_edit_or_send(update, "Select an item to edit:", kb.content_pick_keyboard(items, "content_edit"))


async def content_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE, content_id: int):
    set_state(context, STATE_EDIT_CONTENT, edit_content_id=content_id)
    await safe_edit_or_send(update, "Enter the new title for this item:", kb.cancel_keyboard("admin_content"))


async def content_delete_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = await db.get_content_list()
    if not items:
        await safe_edit_or_send(update, "No content to delete.", kb.admin_back_keyboard("admin_content"))
        return
    await safe_edit_or_send(update, "Select an item to delete:", kb.content_pick_keyboard(items, "content_delete"))


async def content_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, content_id: int):
    admin_id = update.effective_user.id
    await db.delete_content(content_id)
    await db.log_admin_action(admin_id, "DELETE_CONTENT", f"id={content_id}")
    await update.callback_query.answer("Deleted 🗑️")
    await admin_content_menu(update, context)


async def content_moveup_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = await db.get_content_list()
    if len(items) < 2:
        await safe_edit_or_send(update, "Need at least 2 items to reorder.", kb.admin_back_keyboard("admin_content"))
        return
    await safe_edit_or_send(update, "Select an item to move up:", kb.content_pick_keyboard(items, "content_moveup"))


async def content_movedown_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = await db.get_content_list()
    if len(items) < 2:
        await safe_edit_or_send(update, "Need at least 2 items to reorder.", kb.admin_back_keyboard("admin_content"))
        return
    await safe_edit_or_send(update, "Select an item to move down:", kb.content_pick_keyboard(items, "content_movedown"))


async def content_move(update: Update, context: ContextTypes.DEFAULT_TYPE, content_id: int, direction: str):
    admin_id = update.effective_user.id
    await db.move_content(content_id, direction)
    await db.log_admin_action(admin_id, f"MOVE_CONTENT_{direction.upper()}", f"id={content_id}")
    await update.callback_query.answer("Moved")
    await admin_content_menu(update, context)


async def handle_content_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    state = get_state(context)
    if state not in (STATE_ADD_CONTENT, STATE_EDIT_CONTENT):
        return False

    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("⚠️ Title can't be empty. Please try again.")
        return True

    admin_id = update.effective_user.id
    if state == STATE_ADD_CONTENT:
        await db.add_content(title)
        await db.log_admin_action(admin_id, "ADD_CONTENT", title)
        await update.message.reply_text(f"✅ Content added: {title}")
    else:
        content_id = context.user_data.get("edit_content_id")
        await db.edit_content(content_id, title)
        await db.log_admin_action(admin_id, "EDIT_CONTENT", f"id={content_id}, new_title={title}")
        await update.message.reply_text(f"✅ Content updated: {title}")
        context.user_data.pop("edit_content_id", None)

    clear_state(context)
    return True
