"""
database.py
All database access for the bot. Uses aiosqlite so calls don't block the
asyncio event loop that python-telegram-bot runs on.
"""

import logging
import time
from typing import Optional, List, Dict, Any

import aiosqlite

import config

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    status TEXT NOT NULL DEFAULT 'NONE',   -- NONE, PAID, PENDING, REVOKED
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    method TEXT NOT NULL,                  -- STARS, UPI
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, PAID, REJECTED, REFUNDED
    utr TEXT,
    screenshot_file_id TEXT,
    transaction_reference TEXT,
    coupon_code TEXT,
    created_at INTEGER NOT NULL,
    verified_at INTEGER,
    verified_by INTEGER
);

CREATE TABLE IF NOT EXISTS content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    position INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS coupons (
    code TEXT PRIMARY KEY,
    discount_type TEXT NOT NULL,   -- FIXED, PERCENT
    discount_value REAL NOT NULL,
    expiry INTEGER,                -- unix timestamp, NULL = never
    usage_limit INTEGER,           -- NULL = unlimited
    used_count INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    created_at INTEGER NOT NULL
);
"""

DEFAULT_CONTENT = [
    "🎨 Editing Resources",
    "🎬 Premium Presets",
    "🖼️ Graphics Pack",
    "🎵 Music Resources",
    "📚 Exclusive Tutorials",
    "🔥 New Drops",
]


async def init_db():
    """Create tables if they don't exist and seed default settings/content."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

        # Seed settings only if not present
        defaults = {
            "price_inr": str(config.DEFAULT_PRICE_INR),
            "price_stars": str(config.DEFAULT_PRICE_STARS),
            "member_channel_id": str(config.MEMBER_CHANNEL_ID or ""),
            "verification_channel_id": str(config.VERIFICATION_CHANNEL_ID or ""),
            "upi_id": config.UPI_ID,
            "upi_name": config.UPI_NAME,
            "welcome_message": "",
        }
        for key, value in defaults.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
            )
        await db.commit()

        # Seed default content list if empty
        cursor = await db.execute("SELECT COUNT(*) FROM content")
        (count,) = await cursor.fetchone()
        if count == 0:
            now = int(time.time())
            for idx, title in enumerate(DEFAULT_CONTENT, start=1):
                await db.execute(
                    "INSERT INTO content (title, position, created_at) VALUES (?, ?, ?)",
                    (title, idx, now),
                )
            await db.commit()
    logger.info("Database initialized at %s", config.DB_PATH)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

async def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        if row is None or row[0] is None:
            return default
        return row[0]


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()


async def get_price_inr() -> float:
    val = await get_setting("price_inr", str(config.DEFAULT_PRICE_INR))
    try:
        return float(val)
    except (TypeError, ValueError):
        return float(config.DEFAULT_PRICE_INR)


async def get_price_stars() -> int:
    val = await get_setting("price_stars", str(config.DEFAULT_PRICE_STARS))
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return int(config.DEFAULT_PRICE_STARS)


async def get_member_channel_id() -> Optional[int]:
    val = await get_setting("member_channel_id")
    try:
        return int(val) if val else None
    except ValueError:
        return None


async def get_verification_channel_id() -> Optional[int]:
    val = await get_setting("verification_channel_id")
    try:
        return int(val) if val else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def upsert_user(telegram_id: int, username: Optional[str], first_name: Optional[str]):
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO users (telegram_id, username, first_name, status, created_at) "
                "VALUES (?, ?, ?, 'NONE', ?)",
                (telegram_id, username, first_name, int(time.time())),
            )
            logger.info("Registered new user %s (@%s)", telegram_id, username)
        else:
            await db.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE telegram_id = ?",
                (username, first_name, telegram_id),
            )
        await db.commit()


async def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_user_status(telegram_id: int, status: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE users SET status = ? WHERE telegram_id = ?", (status, telegram_id)
        )
        await db.commit()


async def is_user_paid(telegram_id: int) -> bool:
    user = await get_user(telegram_id)
    return bool(user and user["status"] == "PAID")


async def find_users(query: str) -> List[Dict[str, Any]]:
    """Search by numeric telegram_id or username substring."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if query.isdigit():
            cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (int(query),))
        else:
            like = f"%{query.lstrip('@')}%"
            cursor = await db.execute("SELECT * FROM users WHERE username LIKE ? LIMIT 20", (like,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_all_user_ids() -> List[int]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT telegram_id FROM users")
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def count_users() -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        (n,) = await cursor.fetchone()
        return n


async def count_users_since(ts: int) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (ts,))
        (n,) = await cursor.fetchone()
        return n


async def count_paid_users() -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE status = 'PAID'")
        (n,) = await cursor.fetchone()
        return n


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

async def create_payment(
    telegram_id: int,
    method: str,
    amount: float,
    currency: str,
    status: str = "PENDING",
    utr: Optional[str] = None,
    screenshot_file_id: Optional[str] = None,
    transaction_reference: Optional[str] = None,
    coupon_code: Optional[str] = None,
) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO payments "
            "(telegram_id, method, amount, currency, status, utr, screenshot_file_id, "
            "transaction_reference, coupon_code, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                telegram_id, method, amount, currency, status, utr, screenshot_file_id,
                transaction_reference, coupon_code, int(time.time()),
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_payment(payment_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def utr_exists(utr: str) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM payments WHERE utr = ? AND status != 'REJECTED' LIMIT 1", (utr,)
        )
        row = await cursor.fetchone()
        return row is not None


async def transaction_reference_exists(ref: str) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM payments WHERE transaction_reference = ? AND status = 'PAID' LIMIT 1",
            (ref,),
        )
        row = await cursor.fetchone()
        return row is not None


async def mark_payment_paid(payment_id: int, verified_by: Optional[int], transaction_reference: Optional[str] = None) -> bool:
    """Marks a payment PAID only if it is currently PENDING. Returns True if it changed."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE payments SET status = 'PAID', verified_at = ?, verified_by = ?, "
            "transaction_reference = COALESCE(?, transaction_reference) "
            "WHERE payment_id = ? AND status = 'PENDING'",
            (int(time.time()), verified_by, transaction_reference, payment_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def mark_payment_rejected(payment_id: int, verified_by: Optional[int], reason: Optional[str] = None) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE payments SET status = 'REJECTED', verified_at = ?, verified_by = ?, "
            "transaction_reference = ? WHERE payment_id = ? AND status = 'PENDING'",
            (int(time.time()), verified_by, reason, payment_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_latest_payment_for_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM payments WHERE telegram_id = ? ORDER BY created_at DESC LIMIT 1",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_payment_history(telegram_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM payments WHERE telegram_id = ? ORDER BY created_at DESC", (telegram_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def count_sales_by_method(method: str) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM payments WHERE method = ? AND status = 'PAID'", (method,)
        )
        (n,) = await cursor.fetchone()
        return n


async def total_revenue_inr() -> float:
    """Sums UPI revenue directly; Stars revenue is tracked in Stars units, converted upstream if needed."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'PAID' AND method = 'UPI'"
        )
        (upi_total,) = await cursor.fetchone()
        return upi_total


async def count_pending_upi() -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM payments WHERE method = 'UPI' AND status = 'PENDING'"
        )
        (n,) = await cursor.fetchone()
        return n


async def count_sales_since(ts: int) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM payments WHERE status = 'PAID' AND created_at >= ?", (ts,)
        )
        (n,) = await cursor.fetchone()
        return n


async def revenue_since_inr(ts: int) -> float:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'PAID' AND method = 'UPI' AND created_at >= ?",
            (ts,),
        )
        (n,) = await cursor.fetchone()
        return n


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

async def get_content_list() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM content ORDER BY position ASC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def add_content(title: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT COALESCE(MAX(position), 0) FROM content")
        (max_pos,) = await cursor.fetchone()
        await db.execute(
            "INSERT INTO content (title, position, created_at) VALUES (?, ?, ?)",
            (title, max_pos + 1, int(time.time())),
        )
        await db.commit()


async def edit_content(content_id: int, new_title: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE content SET title = ? WHERE id = ?", (new_title, content_id))
        await db.commit()


async def delete_content(content_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM content WHERE id = ?", (content_id,))
        await db.commit()


async def move_content(content_id: int, direction: str):
    """direction: 'up' or 'down'"""
    items = await get_content_list()
    idx = next((i for i, it in enumerate(items) if it["id"] == content_id), None)
    if idx is None:
        return
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if swap_idx < 0 or swap_idx >= len(items):
        return
    a, b = items[idx], items[swap_idx]
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE content SET position = ? WHERE id = ?", (b["position"], a["id"]))
        await db.execute("UPDATE content SET position = ? WHERE id = ?", (a["position"], b["id"]))
        await db.commit()


# ---------------------------------------------------------------------------
# Coupons
# ---------------------------------------------------------------------------

async def create_coupon(code: str, discount_type: str, discount_value: float,
                         expiry: Optional[int], usage_limit: Optional[int]):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO coupons (code, discount_type, discount_value, expiry, usage_limit, "
            "used_count, active, created_at) VALUES (?, ?, ?, ?, ?, 0, 1, ?)",
            (code.upper(), discount_type, discount_value, expiry, usage_limit, int(time.time())),
        )
        await db.commit()


async def get_coupon(code: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM coupons WHERE code = ?", (code.upper(),))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_coupons() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM coupons ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_coupon(code: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM coupons WHERE code = ?", (code.upper(),))
        await db.commit()


async def set_coupon_active(code: str, active: bool):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE coupons SET active = ? WHERE code = ?", (1 if active else 0, code.upper())
        )
        await db.commit()


async def increment_coupon_usage(code: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE coupons SET used_count = used_count + 1 WHERE code = ?", (code.upper(),)
        )
        await db.commit()


def validate_coupon(coupon: Dict[str, Any]) -> bool:
    """Pure validation logic (no DB access) so it's easy to test/reuse."""
    if not coupon or not coupon.get("active"):
        return False
    if coupon.get("expiry") and int(time.time()) > coupon["expiry"]:
        return False
    if coupon.get("usage_limit") is not None and coupon["used_count"] >= coupon["usage_limit"]:
        return False
    return True


def apply_discount(amount: float, coupon: Dict[str, Any]) -> float:
    if coupon["discount_type"] == "PERCENT":
        result = amount - (amount * coupon["discount_value"] / 100.0)
    else:  # FIXED
        result = amount - coupon["discount_value"]
    return max(round(result, 2), 1)


# ---------------------------------------------------------------------------
# Admin actions log
# ---------------------------------------------------------------------------

async def log_admin_action(admin_id: int, action: str, details: str = ""):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO admin_actions (admin_id, action, details, created_at) VALUES (?, ?, ?, ?)",
            (admin_id, action, details, int(time.time())),
        )
        await db.commit()
