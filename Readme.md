# 🔐 Premium Telegram Sales & Private Channel Access Bot

A production-ready Telegram bot that sells access to a private premium channel,
supporting both **Telegram Stars** (automatic) and **UPI** (manual admin
verification) payments, with a full admin panel, content management,
coupons, broadcast, and automatic join-request protection.

---

## 1. Features

- ⭐ **Telegram Stars** payments — verified automatically via Telegram's payment API
- 🇮🇳 **UPI** payments — user submits screenshot + UTR, admin manually approves/rejects
- 🔐 Verification channel support
- 👥 Private member channel with **join-request protection** (numeric user ID only)
- 📦 Editable content list (add / edit / delete / reorder, all from Telegram)
- 💰 Editable price (INR and Stars), changeable without touching code
- 👑 Full admin panel: content, price, payments, users, statistics, coupons, broadcast, channels, messages, settings
- 🎁 Coupon system (fixed or percentage discounts, expiry, usage limits)
- 📢 Broadcast system with delivery statistics
- 💾 SQLite database (via `aiosqlite`, fully async)
- 🧾 Full payment history per user
- 🔒 Duplicate payment / duplicate UTR protection
- 🪵 Structured logging throughout

---

## 2. Requirements

- Python 3.11+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A private Telegram channel for premium members
- (Optional) A separate verification channel
- (For UPI) A UPI ID to receive payments

---

## 3. Installation

```bash
git clone <this project folder>
cd telegram_premium_bot
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r Requirements.txt
```

---

## 4. BotFather Setup

1. Open [@BotFather](https://t.me/BotFather) on Telegram.
2. Send `/newbot` and follow the prompts to create your bot.
3. Copy the bot token BotFather gives you — you'll need it for `.env`.
4. (Optional) Set a bot description/about text with `/setdescription` and `/setabouttext`.
5. **Enable inline mode is NOT required.** No extra BotFather flags are needed for Telegram Stars — Stars payments work out of the box once your bot is created.

---

## 5. Environment Configuration

Copy `.env` and fill in your real values:

```
BOT_TOKEN=123456:ABC-your-real-bot-token
ADMIN_ID=123456789

MEMBER_CHANNEL_ID=-1001234567890
VERIFICATION_CHANNEL_ID=-1009876543210

UPI_ID=yourname@upi
UPI_NAME=Your Name
```

- `ADMIN_ID` is your **numeric** Telegram user ID (not your username). You can get it from a bot like [@userinfobot](https://t.me/userinfobot).
- `MEMBER_CHANNEL_ID` / `VERIFICATION_CHANNEL_ID` are optional at startup — you can configure or change them later from `/admin → CHANNELS` without restarting the bot (they're stored in the database once set there).
- Never commit your real `.env` file to version control.

---

## 6. SQLite Setup

No manual setup needed. On first run, the bot automatically creates
`bot_database.db` (or the path set in `DB_PATH`) with all required tables
(`users`, `payments`, `content`, `settings`, `coupons`, `admin_actions`) and
seeds a default content list and the initial ₹25 price.

---

## 7. Stars Payment Setup

Telegram Stars payments require **no external payment provider** — Telegram
handles the currency (`XTR`) natively. Requirements:

1. Your bot must be able to send invoices (works automatically once the bot exists).
2. The user pays inside Telegram; the bot listens for `successful_payment` updates.
3. The bot **only** grants access after Telegram confirms the payment — never on button click alone.
4. You can set the Stars price separately from the INR price via `/admin → PRICE → CHANGE STARS PRICE`.

---

## 8. UPI Workflow

1. User taps **🇮🇳 UPI** → sees your UPI ID and the current price.
2. User pays externally (any UPI app), then sends a **screenshot** to the bot.
3. Bot asks for the **UTR / transaction ID**.
4. Bot stores the submission as `PENDING` and notifies the admin with the
   screenshot and **✅ APPROVE / ❌ REJECT** buttons.
5. Admin approves → user's access is activated and they're notified.
   Admin rejects → user is notified with the reason (if given).
6. The same UTR can never be submitted twice.

---

## 9. Admin Setup

1. Set `ADMIN_ID` in `.env` to your numeric Telegram ID.
2. Start the bot and send `/admin` from that account.
3. Only this ID (and no one else) can access admin functions — every admin
   action is re-checked server-side, not just hidden from the menu.

---

## 10. Verification Channel Setup

1. Create a Telegram channel (public or private).
2. Add your bot as an **admin** of that channel.
3. Get the channel's numeric ID (forward a message from it to
   [@userinfobot](https://t.me/userinfobot), or use any "get chat id" bot).
4. Set it via `/admin → CHANNELS → Change Verification Channel`, or in `.env`
   before first run.

---

## 11. Member Channel Setup

1. Create a **private** Telegram channel for paying members.
2. Add your bot as an **admin** with at least:
   - "Add Members" / "Invite Users via Link" permission
   - "Ban Users" permission (needed for revoking access)
3. Set the channel to **require approval for new members** (Join Requests) in
   the channel's permission settings — this is what lets the bot approve/decline
   join requests based on payment status.
4. Set the channel ID via `/admin → CHANNELS → Change Member Channel`, or in `.env`.

---

## 12. Required Telegram Bot Permissions

In the **Member Channel**:
- Admin rights: Add Members, Ban Users, Invite Users via Link
- "Approve new members" must be enabled on the channel so join requests are generated

In the **Verification Channel** (optional):
- Admin rights are only needed if you want the bot to check membership status

---

## 13. Running the Bot

```bash
python main.py
```

You should see log lines confirming the database initialized and the bot
started polling. Send `/start` to your bot to test the user flow, and
`/admin` (from the admin account) to test the admin panel.

---

## 14. Troubleshooting

| Problem | Likely Cause |
|---|---|
| Bot doesn't respond | Wrong `BOT_TOKEN`, or bot not started (`python main.py` not running) |
| `/admin` says "not authorized" | `ADMIN_ID` in `.env` doesn't match your numeric Telegram ID |
| Join requests aren't auto-approved | Bot isn't admin in the channel, or the channel doesn't have "approve new members" enabled, or `MEMBER_CHANNEL_ID` isn't set |
| Stars invoice doesn't appear | Make sure you're testing on a Telegram client that supports Stars (recent Telegram app version) |
| UPI screenshot not saved | Make sure the user sends the **photo before** the UTR message, in that order |
| "Message is not modified" errors in logs | Harmless — happens when re-rendering an identical screen; safely ignored |

---

## 15. Security Notes

- Secrets (bot token, admin ID, channel IDs, UPI details) are loaded only
  from environment variables — never hard-coded.
- Stars payments are verified against payload, currency, amount, and a
  unique `telegram_payment_charge_id` before any access is granted; duplicate
  charge IDs are rejected.
- UPI payments are **never** auto-approved — a human admin must approve
  every single one.
- Join requests are approved/declined using the numeric Telegram user ID
  looked up in the database — never by username, and never simply because
  someone has an invite link.
- All admin actions (`/admin` and every admin button) re-check `ADMIN_ID`
  server-side on every request, not just by hiding menu buttons.
- Admin actions are logged to the `admin_actions` table for auditability.

---

## 16. Customization

- **Content list**: `/admin → CONTENT` — add, edit, delete, reorder.
- **Prices**: `/admin → PRICE` — separate INR and Stars prices.
- **Welcome text**: `/admin → MESSAGES` — appends extra text to the `/start` screen.
- **Coupons**: `/admin → COUPONS` — fixed or percentage discounts, with
  optional expiry and usage limits.
- **Channels**: `/admin → CHANNELS` — change member/verification channels
  without restarting the bot.
- To change branding/emojis/copy, edit the text strings in `handlers/user.py`
  and `keyboards.py` — no database or logic changes required.

---

## Project Structure

```
telegram_premium_bot/
├── Main.py                  # Entry point — wires everything together
├── config.py                # Environment variable loading & validation
├── database.py               # All SQLite access (async, via aiosqlite)
├── keyboards.py               # Inline keyboard builders
├── utils.py                   # Shared helpers (admin check, formatting, state)
├── handlers/
│   ├── user.py                 # /start, content list, my purchase, verify, help
│   ├── payments_stars.py       # Telegram Stars invoice + verification
│   ├── payments_upi.py         # UPI screenshot/UTR flow + admin approve/reject
│   ├── join_requests.py        # Private channel join-request protection
│   ├── admin.py                 # Admin menu, price, stats, users, channels, messages
│   ├── admin_content.py        # Content list CRUD + reordering
│   ├── admin_coupons.py        # Coupon CRUD + user coupon entry
│   └── admin_broadcast.py      # Broadcast to all users
├── Requirements.txt
├── .env                        # Your real secrets go here (never commit this)
└── Readme.md
```


## Configuration fix
The project now uses `OWNER_ID`, `PREMIUM_CHANNEL_ID`, `VERIFICATION_CHANNEL_ID`,
`UPI_ID`, `UPI_PRICE_INR`, and `STARS_PRICE`. The `.env` contains a placeholder
for the bot token; generate a new token with BotFather because the previous token
was exposed. Dynamic UPI QR generation should use the current `UPI_PRICE_INR`.
