import os
import sqlite3
from datetime import datetime, date
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@alqisatqielanazerbaycan") # Kanalınızın username-i

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
        title TEXT,
        link TEXT,
        price INTEGER,
        status TEXT DEFAULT 'pending', -- pending, approved, rejected
        views INTEGER DEFAULT 0,
        created_at TEXT
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

def update_balance(uid, amount):
    conn = db()
    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
    conn.commit()
    conn.close()

# ---------- Bot ----------
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------- Məcburi Abunəlik Yoxlaması ----------
async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        print(f"Abunəlik yoxlanılarkən xəta: {e}")
        return False

def sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanala Abunə Ol", url="https://t.me/alqisatqielanazerbaycan")],
        [InlineKeyboardButton(text="✅ Yoxla", callback_data="check_sub")]
    ])

# ---------- Klaviaturalar ----------
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📣 Reklam yerləşdir", callback_data="order_ad")],
        [InlineKeyboardButton(text="💰 Balansım", callback_data="balance")],
        [InlineKeyboardButton(text="👥 Referal sistemi", callback_data="referal")],
        [InlineKeyboardButton(text="🎁 Gündəlik bonus", callback_data="bonus")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="stats")],
        [InlineKeyboardButton(text="🆘 Dəstək", url="https://t.me/Sizin_Destek_Username")]
    ])

# ---------- /start ----------
@dp.message(CommandStart())
async def start(message: Message):
    uid = message.from_user.id
    
    # Abunəlik yoxlaması
    if not await is_subscribed(uid):
        await message.answer(
            "Botdan istifadə etmək üçün əvvəlcə kanalımıza abunə olmalısınız! 👇",
            reply_markup=sub_keyboard()
        )
        return

    args = message.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1].replace("ref_", ""))
        except ValueError:
            ref_id = None

    user = get_user(uid)
    if user is None:
        conn = db()
        conn.execute(
            "INSERT INTO users (user_id, full_name, referal_id) VALUES (?, ?, ?)",
            (uid, message.from_user.full_name, ref_id)
        )
        conn.commit()
        conn.close()

        # Referala bonus (5 coin)
        if ref_id and ref_id != uid and get_user(ref_id):
            update_balance(ref_id, 5)
            conn = db()
            conn.execute("UPDATE users SET referal_count = referal_count + 1 WHERE user_id=?", (ref_id,))
            conn.commit()
            conn.close()

    await message.answer(
        f"Salam, {html.bold(message.from_user.full_name)}! 👋\n\n"
        f"Azərbaycan Alqı-Satqı Reklam Botuna xoş gəldiniz. Aşağıdakı menyudan seçin:",
        reply_markup=main_menu()
    )

# ---------- Abunəliyi Yoxla (Callback) ----------
@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: CallbackQuery):
    if await is_subscribed(cb.from_user.id):
        await cb.message.edit_text(
            "✅ Təşəkkürlər! İndi botdan istifadə edə bilərsiniz.",
            reply_markup=main_menu()
        )
    else:
        await cb.answer("❌ Siz hələ kanala abunə olmamısınız!", show_alert=True)

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
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{cb.from_user.id}"
    await cb.message.edit_text(
        f"👥 <b>Referal sistemi</b>\n\n"
        f"Sizin linkiniz:\n<code>{link}</code>\n\n"
        f"Dəvət etdiyiniz: {u['referal_count']} nəfər\n"
        f"Hər dəvətə: 5 coin",
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
    conn.execute("UPDATE users SET balance = balance + 2, last_bonus = ? WHERE user_id=?", (today, uid))
    conn.commit()
    conn.close()

    await cb.message.edit_text(
        f"🎁 <b>Gündəlik bonus alındı!</b>\n+2 coin\n\nBalans: {get_user(uid)['balance']} coin",
        reply_markup=main_menu()
    )
    await cb.answer("✅ +2 coin")

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

# ---------- Reklam Sifarişi ----------
@dp.callback_query(F.data == "order_ad")
async def cb_order_ad(cb: CallbackQuery):
    await cb.message.edit_text(
        "📣 <b>Yeni Reklam Sifarişi</b>\n\n"
        "Zəhmət olmasa reklamınız üçün qısa bir <b>başlıq</b> yazın (məsələn: 'Yeni telefonlar satılır').\n\n"
        "Ləğv etmək üçün /cancel yazın.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Ləğv et", callback_data="cancel")]])
    )
    await cb.answer()

# Reklam başlığını qəbul et
@dp.message(F.text & ~F.text.startswith('/'))
async def process_ad_title(message: Message):
    uid = message.from_user.id
    # Yoxlayaq ki, istifadəçi həqiqətən reklam yerləşdirir (sadə mətn yazmayıb)
    # Bunun üçün sadə bir keş (cache) və ya DB-də status saxlaya bilərik. 
    # Sadəlik üçün bizə ayrıca state lazımdır, amma aiogram FSM istifadə etmədən bunu belə həll edirik:
    # İstifadəçi /start yazmayıbsa və mətn gəlirsə, deməli reklam başlığıdır.
    # Daha yaxşısı FSM (State) istifadə etməkdir. 
    pass # FSM olmadan bu hissə qarışıq olacaq, aşağıda düzgün FSM-li versiyanı verəcəm.
