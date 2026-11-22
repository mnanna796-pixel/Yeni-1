import os
import sqlite3
import asyncio
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
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        reward INTEGER
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS task_completions (
        user_id INTEGER,
        task_id INTEGER,
        PRIMARY KEY (user_id, task_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        link TEXT,
        price INTEGER,
        status TEXT DEFAULT 'pending',
        created_at TEXT
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

# ---------- FSM States ----------
class AdOrder(StatesGroup):
    title = State()
    link = State()
    confirm = State()

class AdminAddCoin(StatesGroup):
    user_id = State()
    amount = State()

class AdminAddTask(StatesGroup):
    title = State()
    reward = State()
    link = State()

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
def main_menu(uid):
    kb = [
        [InlineKeyboardButton(text="📣 Reklam yerləşdir", callback_data="order_ad")],
        [InlineKeyboardButton(text="📋 Tapşırıqlar", callback_data="tasks")],
        [InlineKeyboardButton(text="💰 Balansım", callback_data="balance")],
        [InlineKeyboardButton(text="👥 Referal sistemi", callback_data="referal")],
        [InlineKeyboardButton(text="🎁 Gündəlik bonus", callback_data="bonus")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="stats")],
        [InlineKeyboardButton(text="🆘 Dəstək", url="https://t.me/Sizin_Destek_Username")]
    ]
    if uid == ADMIN_ID:
        kb.append([InlineKeyboardButton(text="👨‍💻 Admin Paneli", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Ümumi Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💰 Coin Əlavə Et", callback_data="admin_add_coin")],
        [InlineKeyboardButton(text="📝 Tapşırıq Əlavə Et", callback_data="admin_add_task")],
        [InlineKeyboardButton(text="🔙 Geri", callback_data="back_main")]
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
        reply_markup=main_menu(uid)
    )

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: CallbackQuery):
    if await is_subscribed(cb.from_user.id):
        await cb.message.edit_text("✅ Təşəkkürlər! İndi botdan istifadə edə bilərsiniz.", reply_markup=main_menu(cb.from_user.id))
    else:
        await cb.answer("❌ Siz hələ kanala abunə olmamısınız!", show_alert=True)

@dp.callback_query(F.data == "back_main")
async def cb_back_main(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Əsas menyu:", reply_markup=main_menu(cb.from_user.id))
    await cb.answer()

# ---------- Balans ----------
@dp.callback_query(F.data == "balance")
async def cb_balance(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    await cb.message.edit_text(f"💰 <b>Balansınız:</b> {u['balance']} coin", reply_markup=main_menu(cb.from_user.id))
    await cb.answer()

# ---------- Referal ----------
@dp.callback_query(F.data == "referal")
async def cb_referal(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{cb.from_user.id}"
    await cb.message.edit_text(
        f"👥 <b>Referal sistemi</b>\n\nSizin linkiniz:\n<code>{link}</code>\n\nDəvət etdiyiniz: {u['referal_count']} nəfər\nHər dəvətə: 5 coin",
        reply_markup=main_menu(cb.from_user.id)
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

    await cb.message.edit_text(f"🎁 <b>Gündəlik bonus alındı!</b>\n+2 coin\n\nBalans: {get_user(uid)['balance']} coin", reply_markup=main_menu(uid))
    await cb.answer("✅ +2 coin")

# ---------- Statistika ----------
@dp.callback_query(F.data == "stats")
async def cb_stats(cb: CallbackQuery):
    conn = db()
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()

    u = get_user(cb.from_user.id)
    await cb.message.edit_text(
        f"📊 <b>Statistika</b>\n\n👤 Sizin referallar: {u['referal_count']}\n💵 Balans: {u['balance']} coin\n🌐 Ümumi istifadəçi: {total_users}",
        reply_markup=main_menu(cb.from_user.id)
    )
    await cb.answer()

# ---------- Tapşırıqlar ----------
@dp.callback_query(F.data == "tasks")
async def cb_tasks(cb: CallbackQuery):
    conn = db()
    tasks = conn.execute("SELECT * FROM tasks").fetchall()
    conn.close()

    if not tasks:
        await cb.answer("Hazırda aktiv tapşırıq yoxdur.", show_alert=True)
        return

    await cb.message.edit_text("📋 <b>Tapşırıqlar</b>\n\nAşağıdakı tapşırıqları yerinə yetirərək coin qazanın:", reply_markup=main_menu(cb.from_user.id))
    
    for t in tasks:
        conn = db()
        completed = conn.execute("SELECT 1 FROM task_completions WHERE user_id=? AND task_id=?", (cb.from_user.id, t['id'])).fetchone()
        conn.close()
        
        if not completed:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🔗 Tapşırığa keç (+{t['reward']} coin)", url="https://t.me/telegram")], # Linki sonra dəyişərik
                [InlineKeyboardButton(text="✅ Yoxla və Al", callback_data=f"check_task_{t['id']}")]
            ])
            await cb.message.answer(f"<b>{t['title']}</b>\nMükafat: {t['reward']} coin", reply_markup=kb)

@dp.callback_query(F.data.startswith("check_task_"))
async def cb_check_task(cb: CallbackQuery):
    task_id = int(cb.data.replace("check_task_", ""))
    uid = cb.from_user.id
    
    conn = db()
    completed = conn.execute("SELECT 1 FROM task_completions WHERE user_id=? AND task_id=?", (uid, task_id)).fetchone()
    if completed:
        conn.close()
        await cb.answer("❌ Bu tapşırığı artıq etmisiniz.", show_alert=True)
        return
    
    task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        await cb.answer("Tapşırıq tapılmadı.", show_alert=True)
        return
        
    conn.execute("INSERT INTO task_completions (user_id, task_id) VALUES (?, ?)", (uid, task_id))
    conn.commit()
    conn.close()
    
    update_balance(uid, task['reward'])
    await cb.message.edit_text(f"✅ Tapşırıq tamamlandı! +{task['reward']} coin.")
    await cb.answer("✅ Təbriklər!")

# ---------- Reklam Sifarişi ----------
@dp.callback_query(F.data == "order_ad")
async def cb_order_ad(cb: CallbackQuery, state: FSMContext):
    u = get_user(cb.from_user.id)
    if u['balance'] < 50:
        await cb.answer("❌ Balansınız kifayət etmir! Minimum 50 coin lazımdır.", show_alert=True)
        return
        
    await state.set_state(AdOrder.title)
    await cb.message.edit_text(
        "📣 <b>Yeni Reklam Sifarişi</b>\n\nReklamınız üçün qısa bir <b>başlıq</b> yazın.\nLəğv etmək üçün /cancel yazın.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Ləğv et", callback_data="cancel_ad")]])
    )
    await cb.answer()

@dp.message(AdOrder.title)
async def process_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AdOrder.link)
    await message.answer("🔗 İndi isə reklamınızın <b>linkini</b> (URL) göndərin:\nLəğv etmək üçün /cancel yazın.")

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
        f"📋 <b>Xülasə:</b>\n\n<b>Başlıq:</b> {data['title']}\n<b>Link:</b> {data['link']}\n<b>Qiymət:</b> 50 coin\n\nTəsdiqləyirsinizmi?",
        reply_markup=kb
    )

@dp.callback_query(F.data == "confirm_ad", AdOrder.confirm)
async def cb_confirm_ad(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = cb.from_user.id
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
    await cb.message.edit_text("✅ Reklam sifarişiniz qəbul edildi! Admin təsdiqlədikdən sonra kanalda paylaşılacaq.", reply_markup=main_menu(uid))
    
    try:
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Təsdiqlə", callback_data=f"approve_{ad_id}")],
            [InlineKeyboardButton(text="❌ Rədd et", callback_data=f"reject_{ad_id}")]
        ])
        await bot.send_message(
            ADMIN_ID,
            f"🔔 <b>Yeni Reklam Sifarişi!</b>\n\n<b>ID:</b> {ad_id}\n<b>İstifadəçi:</b> {cb.from_user.full_name}\n<b>Başlıq:</b> {data['title']}\n<b>Link:</b> {data['link']}",
            reply_markup=admin_kb
        )
    except: pass

@dp.callback_query(F.data == "cancel_ad")
async def cb_cancel_ad(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Reklam sifarişi ləğv edildi.", reply_markup=main_menu(cb.from_user.id))
    await cb.answer()

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Əməliyyat ləğv edildi.", reply_markup=main_menu(message.from_user.id))

# ---------- Admin Təsdiqi ----------
@dp.callback_query(F.data.startswith("approve_"))
async def cb_approve_ad(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
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
    
    try:
        await bot.send_message(CHANNEL_ID, f"📣 <b>Reklam</b>\n\n<b>{ad['title']}</b>\n\n🔗 Ətraflı: {ad['link']}")
        await cb.message.edit_text(f"✅ Reklam (ID: {ad_id}) təsdiqləndi və kanalda paylaşıldı.")
        try: await bot.send_message(ad['user_id'], f"✅ Sizin reklamınız (ID: {ad_id}) təsdiqləndi və kanalda paylaşıldı!")
        except: pass
    except Exception as e:
        await cb.message.edit_text(f"⚠️ Reklam təsdiqləndi, amma kanalda paylaşılarkən xəta: {e}\nBotun kanalda admin olduğuna əmin olun.")
    await cb.answer()

@dp.callback_query(F.data.startswith("reject_"))
async def cb_reject_ad(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
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
    
    update_balance(ad['user_id'], 50)
    await cb.message.edit_text(f"❌ Reklam (ID: {ad_id}) rədd edildi. 50 coin geri qaytarıldı.")
    try: await bot.send_message(ad['user_id'], f"❌ Təəssüf ki, reklamınız (ID: {ad_id}) rədd edildi. 50 coin geri qaytarıldı.")
    except: pass
    await cb.answer()

# ---------- ADMIN PANELİ ----------
@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    await cb.message.edit_text("👨‍💻 <b>Admin Paneli</b>\n\nİdarəetmə üçün seçim edin:", reply_markup=admin_menu())
    await cb.answer()

@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    conn = db()
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    ads = conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM ads WHERE status='pending'").fetchone()[0]
    conn.close()
    await cb.message.edit_text(
        f"📊 <b>Bot Statistikası</b>\n\n👥 İstifadəçilər: {users}\n📣 Reklamlar: {ads}\n⏳ Gözləyən: {pending}",
        reply_markup=admin_menu()
    )
    await cb.answer()

# Admin: Coin əlavə et
@dp.callback_query(F.data == "admin_add_coin")
async def cb_admin_add_coin(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID: return
    await state.set_state(AdminAddCoin.user_id)
    await cb.message.edit_text("👤 İstifadəçinin <b>ID</b> nömrəsini yazın (məsələn: 123456789):")
    await cb.answer()

@dp.message(AdminAddCoin.user_id)
async def admin_coin_uid(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Zəhmət olmasa yalnız rəqəm yazın.")
        return
    await state.update_data(uid=message.text)
    await state.set_state(AdminAddCoin.amount)
    await message.answer("💰 Əlavə etmək istədiyiniz <b>coin</b> miqdarını yazın (məsələn: 100):")

@dp.message(AdminAddCoin.amount)
async def admin_coin_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Zəhmət olmasa yalnız rəqəm yazın.")
        return
    data = await state.get_data()
    target_uid = int(data['uid'])
    amount = int(message.text)
    
    if get_user(target_uid):
        update_balance(target_uid, amount)
        await message.answer(f"✅ İstifadəçiyə (ID: {target_uid}) {amount} coin əlavə edildi.", reply_markup=main_menu(message.from_user.id))
        try: await bot.send_message(target_uid, f"💰 Balansınıza admin tərəfindən {amount} coin əlavə edildi!")
        except: pass
    else:
        await message.answer("❌ Belə bir istifadəçi tapılmadı.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# Admin: Tapşırıq əlavə et
@dp.callback_query(F.data == "admin_add_task")
async def cb_admin_add_task(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID: return
    await state.set_state(AdminAddTask.title)
    await cb.message.edit_text("📝 Tapşırığın <b>başlığını</b> yazın (məsələn: 'Kanala keçid et'):")
    await cb.answer()

@dp.message(AdminAddTask.title)
async def admin_task_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AdminAddTask.reward)
    await message.answer("💰 Tapşırığın <b>mükafatını</b> (coin) yazın (məsələn: 10):")

@dp.message(AdminAddTask.reward)
async def admin_task_reward(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Zəhmət olmasa yalnız rəqəm yazın.")
        return
    data = await state.get_data()
    
    conn = db()
    conn.execute("INSERT INTO tasks (title, reward) VALUES (?, ?)", (data['title'], int(message.text)))
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Tapşırıq yaradıldı!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# ---------- Polling ----------
async def start_polling():
    init_db()
    await dp.start_polling(bot, handle_signals=False)
