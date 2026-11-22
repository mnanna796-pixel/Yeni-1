import os
import sqlite3
from datetime import datetime, date
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ---------- Verilənlər bazası ----------
def db():
    conn = sqlite3.connect("bot.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        full_name TEXT,
        balance INTEGER DEFAULT 0,
        referal_id INTEGER,
        referal_count INTEGER DEFAULT 0,
        last_bonus TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        link TEXT,
        price INTEGER,
        status TEXT DEFAULT 'pending',
        views INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS ad_views (
        user_id INTEGER,
        ad_id INTEGER,
        PRIMARY KEY (user_id, ad_id)
    )""")
    conn.commit()
    conn.close()

def get_user(uid):
    conn = db()
    u = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    return u

def add_balance(uid, amount):
    conn = db()
    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
    conn.commit()
    conn.close()

# ---------- Bot ----------
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------- Klaviaturalar ----------
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Balansım", callback_data="balance")],
        [InlineKeyboardButton(text="👥 Referal sistemi", callback_data="referal")],
        [InlineKeyboardButton(text="🎁 Gündəlik bonus", callback_data="bonus")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="stats")],
        [InlineKeyboardButton(text="📣 Reklam izlə", callback_data="watch_ad")],
    ])

# ---------- /start ----------
@dp.message(CommandStart())
async def start(message: Message):
    args = message.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1].replace("ref_", ""))
        except ValueError:
            ref_id = None

    uid = message.from_user.id
    user = get_user(uid)

    if user is None:
        conn = db()
        conn.execute(
            "INSERT INTO users (user_id, full_name, referal_id) VALUES (?, ?, ?)",
            (uid, message.from_user.full_name, ref_id)
        )
        conn.commit()
        conn.close()

        # Referala bonus
        if ref_id and ref_id != uid and get_user(ref_id):
            add_balance(ref_id, 10)
            conn = db()
            conn.execute("UPDATE users SET referal_count = referal_count + 1 WHERE user_id=?", (ref_id,))
            conn.commit()
            conn.close()

    await message.answer(
        f"Salam, {html.bold(message.from_user.full_name)}! 👋\n\n"
        f"Reklam botuna xoş gəldiniz. Aşağıdakı menyudan seçin:",
        reply_markup=main_menu()
    )

# ---------- Balans ----------
@dp.callback_query(F.data == "balance")
async def cb_balance(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    await cb.message.edit_text(
        f"💰 <b>Balansınız:</b> {u['balance']} coin",
        reply_markup=main_menu()
    )
    await cb.answer()

# ---------- Referal ----------
@dp.callback_query(F.data == "referal")
async def cb_referal(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    link = f"https://t.me/{(await bot.get_me()).username}?start=ref_{cb.from_user.id}"
    await cb.message.edit_text(
        f"👥 <b>Referal sistemi</b>\n\n"
        f"Sizin linkiniz:\n<code>{link}</code>\n\n"
        f"Dəvət etdiyiniz: {u['referal_count']} nəfər\n"
        f"Hər dəvətə: 10 coin",
        reply_markup=main_menu()
    )
    await cb.answer()

# ---------- Gündəlik bonus ----------
@dp.callback_query(F.data == "bonus")
async def cb_bonus(cb: CallbackQuery):
    uid = cb.from_user.id
    u = get_user(uid)
    today = date.today().isoformat()

    if u["last_bonus"] == today:
        await cb.answer("❌ Bu gün artıq bonus almısınız!", show_alert=True)
        return

    conn = db()
    conn.execute("UPDATE users SET balance = balance + 5, last_bonus = ? WHERE user_id=?", (today, uid))
    conn.commit()
    conn.close()

    await cb.message.edit_text(
        f"🎁 <b>Gündəlik bonus alındı!</b>\n+5 coin\n\nBalans: {get_user(uid)['balance']} coin",
        reply_markup=main_menu()
    )
    await cb.answer("✅ +5 coin")

# ---------- Statistika ----------
@dp.callback_query(F.data == "stats")
async def cb_stats(cb: CallbackQuery):
    conn = db()
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    views = conn.execute("SELECT COUNT(*) FROM ad_views WHERE user_id=?", (cb.from_user.id,)).fetchone()[0]
    conn.close()

    u = get_user(cb.from_user.id)
    await cb.message.edit_text(
        f"📊 <b>Statistika</b>\n\n"
        f"👤 Sizin referallar: {u['referal_count']}\n"
        f"👀 İzlədiyiniz reklamlar: {views}\n"
        f"💵 Balans: {u['balance']} coin\n"
        f"🌐 Ümumi istifadəçi: {total_users}",
        reply_markup=main_menu()
    )
    await cb.answer()

# ---------- Reklam izlə ----------
@dp.callback_query(F.data == "watch_ad")
async def cb_watch_ad(cb: CallbackQuery):
    conn = db()
    ad = conn.execute("""
        SELECT * FROM ads 
        WHERE status='approved' 
        AND id NOT IN (SELECT ad_id FROM ad_views WHERE user_id=?)
        LIMIT 1
    """, (cb.from_user.id,)).fetchone()
    conn.close()

    if not ad:
        await cb.answer("😔 Hazırda izləyəcək reklam yoxdur", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Reklama bax", url=ad["link"])],
        [InlineKeyboardButton(text="✅ Təsdiqlə", callback_data=f"confirm_{ad['id']}")],
    ])
    await cb.message.edit_text(
        f"📣 <b>Reklam</b>\n\n"
        f"Linkə baxın, sonra təsdiqləyin.\n"
        f"Mükafat: +{ad['price']} coin",
        reply_markup=kb
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("confirm_"))
async def cb_confirm(cb: CallbackQuery):
    ad_id = int(cb.data.replace("confirm_", ""))
    uid = cb.from_user.id

    conn = db()
    already = conn.execute("SELECT 1 FROM ad_views WHERE user_id=? AND ad_id=?", (uid, ad_id)).fetchone()
    if already:
        conn.close()
        await cb.answer("❌ Artıq bu reklamı izləmisiniz", show_alert=True)
        return

    ad = conn.execute("SELECT * FROM ads WHERE id=?", (ad_id,)).fetchone()
    if not ad:
        conn.close()
        await cb.answer("Reklam tapılmadı", show_alert=True)
        return

    conn.execute("INSERT INTO ad_views (user_id, ad_id) VALUES (?, ?)", (uid, ad_id))
    conn.execute("UPDATE ads SET views = views + 1 WHERE id=?", (ad_id,))
    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (ad["price"], uid))
    conn.commit()
    conn.close()

    await cb.message.edit_text(
        f"✅ Təsdiqləndi! +{ad['price']} coin\n\nBalans: {get_user(uid)['balance']} coin",
        reply_markup=main_menu()
    )
    await cb.answer("✅ Bonus verildi")

# ---------- Admin: reklam əlavə et ----------
@dp.message(Command("add_ad"))
async def cmd_add_ad(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("İstifadə: /add_ad <qiymət> <link>")
        return
    price = int(parts[1])
    link = parts[2]

    conn = db()
    conn.execute("INSERT INTO ads (user_id, link, price, status) VALUES (?, ?, ?, 'approved')",
                 (message.from_user.id, link, price))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Reklam əlavə edildi: {link}")

# ---------- Polling ----------
async def start_polling():
    init_db()
    await dp.start_polling(bot)
