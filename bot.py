import os
import sqlite3
from datetime import datetime, date
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@alqisatqielanazerbaycan")
CHANNEL_URL = "https://t.me/alqisatqielanazerbaycan"

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
        status TEXT DEFAULT 'pending',
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

# ---------- FSM (Reklam Sifarişi üçün) ----------
class AdOrder(StatesGroup):
    title = State()
    link = State()
    confirm = State()

# ---------- Məcburi Abunəlik ----------
async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception:
        return False

def sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanala Abunə Ol", url=CHANNEL_URL)],
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
async def start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    
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

        if ref_id and ref_id != uid and get_user(ref_id):
            update_balance(ref_id, 5)
            conn = db()
            conn.execute("UPDATE users SET referal_count = referal_count + 1 WHERE user_id=?", (ref_id,))
            conn.commit()
            conn.close()

    await message.answer(
        f"Salam, {html.bold(message.from_user.full_name)}! 👋\n\n"
        f"Azərbaycan Alqı-Satqı Reklam Botuna xoş gəldiniz.",
        reply_markup=main_menu()
    )

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: CallbackQuery):
    if await is_subscribed(cb.from_user.id):
        await cb.message.edit_text("✅ Təşəkkürlər! İndi botdan istifadə edə bilərsiniz.", reply_markup=main_menu())
    else:
        await cb.answer("❌ Siz hələ kanala abunə olmamısınız!", show_alert=True)

# ---------- Balans ----------
@dp.callback_query(F.data == "balance")
async def cb_balance(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    await cb.message.edit_text(f"💰 <b>Balansınız:</b> {u['balance']} coin", reply_markup=main_menu())
    await cb.answer()

# ---------- Referal ----------
@dp.callback_query(F.data == "referal")
async def cb_referal(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{cb.from_user.id}"
    await cb.message.edit_text(
        f"👥 <b>Referal sistemi</b>\n\nSizin linkiniz:\n<code>{link}</code>\n\nDəvət etdiyiniz: {u['referal_count']} nəfər\nHər dəvətə: 5 coin",
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

    await cb.message.edit_text(f"🎁 <b>Gündəlik bonus alındı!</b>\n+2 coin\n\nBalans: {get_user(uid)['balance']} coin", reply_markup=main_menu())
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
        f"📊 <b>Statistika</b>\n\n👤 Sizin referallar: {u['referal_count']}\n👀 İzlədiyiniz reklamlar: {views}\n💵 Balans: {u['balance']} coin\n🌐 Ümumi istifadəçi: {total_users}",
        reply_markup=main_menu()
    )
    await cb.answer()

# ---------- Reklam Sifarişi (FSM) ----------
@dp.callback_query(F.data == "order_ad")
async def cb_order_ad(cb: CallbackQuery, state: FSMContext):
    u = get_user(cb.from_user.id)
    if u['balance'] < 50:
        await cb.answer("❌ Balansınız kifayət etmir! Minimum 50 coin lazımdır.", show_alert=True)
        return
        
    await state.set_state(AdOrder.title)
    await cb.message.edit_text(
        "📣 <b>Yeni Reklam Sifarişi</b>\n\n"
        "Zəhmət olmasa reklamınız üçün qısa bir <b>başlıq</b> yazın.\n\n"
        "Ləğv etmək üçün /cancel yazın.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Ləğv et", callback_data="cancel_ad")]])
    )
    await cb.answer()

@dp.message(AdOrder.title)
async def process_title(message: Message, state: FSMContext):
    if len(message.text) > 100:
        await message.answer("Başlıq çox uzundur. Zəhmət olmasa 100 simvoldan qısa yazın.")
        return
    await state.update_data(title=message.text)
    await state.set_state(AdOrder.link)
    await message.answer("🔗 İndi isə reklamınızın <b>linkini</b> (URL) göndərin:\n\nLəğv etmək üçün /cancel yazın.")

@dp.message(AdOrder.link)
async def process_link(message: Message, state: FSMContext):
    if not message.text.startswith("http"):
        await message.answer("Zəhmət olmasa düzgün link (http ilə başlayan) göndərin.")
        return
    await state.update_data(link=message.text)
    data = await state.get_data()
    
    await state.set_state(AdOrder.confirm)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Təsdiqlə və Göndər", callback_data="confirm_ad")],
        [InlineKeyboardButton(text="❌ Ləğv et", callback_data="cancel_ad")]
    ])
    await message.answer(
        f"📋 <b>Reklamınızın xülasəsi:</b>\n\n"
        f"<b>Başlıq:</b> {data['title']}\n"
        f"<b>Link:</b> {data['link']}\n"
        f"<b>Qiymət:</b> 50 coin\n\n"
        f"Təsdiqləyirsinizmi?",
        reply_markup=kb
    )

@dp.callback_query(F.data == "confirm_ad", AdOrder.confirm)
async def cb_confirm_ad(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = cb.from_user.id
    
    # Balansdan 50 coin çıxırıq
    update_balance(uid, -50)
    
    conn = db()
    conn.execute(
        "INSERT INTO ads (user_id, title, link, price, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
        (uid, data['title'], data['link'], 50, datetime.now().isoformat())
    )
    ad_id = conn.lastrowid
    conn.commit()
    conn.close()
    
    await state.clear()
    await cb.message.edit_text(
        "✅ Reklam sifarişiniz qəbul edildi! Admin təsdiqlədikdən sonra kanalda paylaşılacaq.",
        reply_markup=main_menu()
    )
    
    # Adminə bildiriş
    try:
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Təsdiqlə", callback_data=f"approve_{ad_id}")],
            [InlineKeyboardButton(text="❌ Rədd et", callback_data=f"reject_{ad_id}")]
        ])
        await bot.send_message(
            ADMIN_ID,
            f"🔔 <b>Yeni Reklam Sifarişi!</b>\n\n"
            f"<b>ID:</b> {ad_id}\n"
            f"<b>İstifadəçi:</b> {cb.from_user.full_name} (<code>{uid}</code>)\n"
            f"<b>Başlıq:</b> {data['title']}\n"
            f"<b>Link:</b> {data['link']}\n"
            f"<b>Qiymət:</b> 50 coin",
            reply_markup=admin_kb
        )
    except Exception as e:
        print(f"Adminə mesaj getmədi: {e}")

@dp.callback_query(F.data == "cancel_ad")
async def cb_cancel_ad(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Reklam sifarişi ləğv edildi.", reply_markup=main_menu())
    await cb.answer()

# ---------- Admin Təsdiqi ----------
@dp.callback_query(F.data.startswith("approve_"))
async def cb_approve_ad(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("❌ Sizin buna icazəniz yoxdur.", show_alert=True)
        return
        
    ad_id = int(cb.data.replace("approve_", ""))
    conn = db()
    ad = conn.execute("SELECT * FROM ads WHERE id=?", (ad_id,)).fetchone()
    if not ad or ad['status'] != 'pending':
        conn.close()
        await cb.answer("Bu reklam artıq emal edilib.", show_alert=True)
        return
        
    conn.execute("UPDATE ads SET status='approved' WHERE id=?", (ad_id,))
    conn.commit()
    conn.close()
    
    # Kanalda paylaş
    try:
        await bot.send_message(
            CHANNEL_ID,
            f"📣 <b>Reklam</b>\n\n"
            f"<b>{ad['title']}</b>\n\n"
            f"🔗 Ətraflı: {ad['link']}"
        )
        await cb.message.edit_text(f"✅ Reklam (ID: {ad_id}) təsdiqləndi və kanalda paylaşıldı.")
        
        # İstifadəçiyə bildiriş
        try:
            await bot.send_message(ad['user_id'], f"✅ Sizin reklamınız (ID: {ad_id}) admin tərəfindən təsdiqləndi və kanalda paylaşıldı!")
        except: pass
        
    except Exception as e:
        await cb.message.edit_text(f"⚠️ Reklam təsdiqləndi, amma kanalda paylaşılarkən xəta baş verdi: {e}\n\nBotun kanalda admin olduğuna əmin olun.")
        
    await cb.answer()

@dp.callback_query(F.data.startswith("reject_"))
async def cb_reject_ad(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("❌ Sizin buna icazəniz yoxdur.", show_alert=True)
        return
        
    ad_id = int(cb.data.replace("reject_", ""))
    conn = db()
    ad = conn.execute("SELECT * FROM ads WHERE id=?", (ad_id,)).fetchone()
    if not ad or ad['status'] != 'pending':
        conn.close()
        await cb.answer("Bu reklam artıq emal edilib.", show_alert=True)
        return
        
    conn.execute("UPDATE ads SET status='rejected' WHERE id=?", (ad_id,))
    conn.commit()
    conn.close()
    
    # Balansı geri qaytar (50 coin)
    update_balance(ad['user_id'], 50)
    
    await cb.message.edit_text(f"❌ Reklam (ID: {ad_id}) rədd edildi. İstifadəçinin balansına 50 coin geri qaytarıldı.")
    
    try:
        await bot.send_message(ad['user_id'], f"❌ Təəssüf ki, reklamınız (ID: {ad_id}) admin tərəfindən rədd edildi. 50 coin balansınıza geri qaytarıldı.")
    except: pass
    
    await cb.answer()

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Əməliyyat ləğv edildi.", reply_markup=main_menu())

# ---------- Polling ----------
async def start_polling():
    init_db()
    await dp.start_polling(bot, handle_signals=False)
