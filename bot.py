import os
import sqlite3
import asyncio
from datetime import datetime, date, timedelta
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
        user_id INTEGER PRIMARY KEY, full_name TEXT, balance INTEGER DEFAULT 0,
        referal_id INTEGER, referal_count INTEGER DEFAULT 0, last_bonus TEXT
    )""")
    # Bot Reklamı (Tapşırıqlar)
    c.execute("""CREATE TABLE IF NOT EXISTS bot_ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT, link TEXT, 
        reward INTEGER, max_users INTEGER, current_users INTEGER DEFAULT 0, 
        status TEXT DEFAULT 'pending', created_at TEXT
    )""")
    # Kanal Reklamı
    c.execute("""CREATE TABLE IF NOT EXISTS channel_ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, content TEXT, 
        price INTEGER, duration_hours INTEGER, status TEXT DEFAULT 'pending', 
        created_at TEXT, expire_at TEXT, channel_message_id INTEGER
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS task_completions (
        user_id INTEGER, ad_id INTEGER, PRIMARY KEY (user_id, ad_id)
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
    choose_pkg = State()
    title = State()
    link = State()
    confirm = State()

class ChannelAd(StatesGroup):
    choose_pkg = State()
    content = State()

class SupportTicket(StatesGroup):
    message = State()

class AdminReply(StatesGroup):
    user_id = State()
    message = State()

class AdminAddTask(StatesGroup):
    title = State()
    link = State()
    reward = State()
    limit = State()

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
        [InlineKeyboardButton(text="💰 Balansım", callback_data="balance")],
        [InlineKeyboardButton(text="📋 Tapşırıqlar", callback_data="tasks")],
        [InlineKeyboardButton(text="📢 Kanal Reklamı", callback_data="channel_ad")],
        [InlineKeyboardButton(text="🤖 Bot Reklamı (Tapşırıq yerləşdir)", callback_data="bot_ad")],
        [InlineKeyboardButton(text="👥 Referal sistemi", callback_data="referal")],
        [InlineKeyboardButton(text="🎁 Gündəlik bonus", callback_data="bonus")],
        [InlineKeyboardButton(text="💬 Dəstək xidməti", callback_data="support")],
        [InlineKeyboardButton(text="📜 Qaydalar", callback_data="rules")]
    ]
    if uid == ADMIN_ID:
        kb.append([InlineKeyboardButton(text="👨‍💻 Admin Paneli", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Ümumi Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💰 Coin Əlavə Et", callback_data="admin_add_coin")],
        [InlineKeyboardButton(text="💬 Dəstək Müraciətləri", callback_data="admin_support")],
        [InlineKeyboardButton(text="🔙 Geri", callback_data="back_main")]
    ])

# ---------- /start ----------
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    
    if not await is_subscribed(uid):
        await message.answer("Botdan istifadə etmək üçün əvvəlcə kanalımıza abunə olmalısınız! 👇", reply_markup=sub_keyboard())
        return

    args = message.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try: ref_id = int(args[1].replace("ref_", ""))
        except ValueError: ref_id = None

    user = get_user(uid)
    if user is None:
        conn = db()
        conn.execute("INSERT INTO users (user_id, full_name, referal_id) VALUES (?, ?, ?)", (uid, message.from_user.full_name, ref_id))
        conn.commit()
        conn.close()

        if ref_id and ref_id != uid and get_user(ref_id):
            update_balance(ref_id, 5)
            conn = db()
            conn.execute("UPDATE users SET referal_count = referal_count + 1 WHERE user_id=?", (ref_id,))
            conn.commit()
            conn.close()

    await message.answer(f"Salam, {html.bold(message.from_user.full_name)}! 👋\n\nRəsmi Reklam Botuna xoş gəldiniz.", reply_markup=main_menu(uid))

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

# ---------- Balans, Referal, Bonus, Qaydalar ----------
@dp.callback_query(F.data == "balance")
async def cb_balance(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    await cb.message.edit_text(f"💰 <b>Balansınız:</b> {u['balance']} coin", reply_markup=main_menu(cb.from_user.id))
    await cb.answer()

@dp.callback_query(F.data == "referal")
async def cb_referal(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{cb.from_user.id}"
    await cb.message.edit_text(f"👥 <b>Referal sistemi</b>\n\nSizin linkiniz:\n<code>{link}</code>\n\nDəvət etdiyiniz: {u['referal_count']} nəfər\nHər dəvətə: 5 coin", reply_markup=main_menu(cb.from_user.id))
    await cb.answer()

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

@dp.callback_query(F.data == "rules")
async def cb_rules(cb: CallbackQuery):
    await cb.message.edit_text("📜 <b>Qaydalar</b>\n\n1. Saxta hesablar qadağandır.\n2. Özünə referal göndərmək olmaz.\n3. Reklamlar admin tərəfindən yoxlanılır.", reply_markup=main_menu(cb.from_user.id))
    await cb.answer()

# ---------- BOT REKLAMI (Tapşırıq formasında) ----------
@dp.callback_query(F.data == "bot_ad")
async def cb_bot_ad(cb: CallbackQuery, state: FSMContext):
    u = get_user(cb.from_user.id)
    if u['balance'] < 15:
        await cb.answer("❌ Balansınız kifayət etmir! Minimum 15 coin lazımdır.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="3 nəfər (15 coin)", callback_data="botad_3_15_3")],
        [InlineKeyboardButton(text="5 nəfər (25 coin)", callback_data="botad_5_25_3")],
        [InlineKeyboardButton(text="10 nəfər (50 coin)", callback_data="botad_10_50_3")],
        [InlineKeyboardButton(text="❌ Ləğv et", callback_data="back_main")]
    ])
    await cb.message.edit_text("🤖 <b>Bot Reklamı (Tapşırıq)</b>\n\nReklamınızın neçə nəfərə göstərilməsini seçin.\n(İstifadəçilər tapşırığı yerinə yetirəndə 3 coin qazanacaqlar)", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("botad_"))
async def cb_botad_pkg(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split("_")
    max_users = int(parts[1])
    price = int(parts[2])
    reward = int(parts[3])
    
    await state.update_data(max_users=max_users, price=price, reward=reward)
    await state.set_state(AdOrder.title)
    await cb.message.edit_text("📝 Tapşırığın <b>başlığını</b> yazın (məs: 'Yeni kanala qoşul'):\nLəğv etmək üçün /cancel yazın.")
    await cb.answer()

@dp.message(AdOrder.title)
async def process_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AdOrder.link)
    await message.answer("🔗 Kanala/qrupa qoşulmaq üçün <b>linki</b> göndərin:")

@dp.message(AdOrder.link)
async def process_link(message: Message, state: FSMContext):
    if not message.text.startswith("http"):
        return await message.answer("Zəhmət olmasa düzgün link göndərin.")
    await state.update_data(link=message.text)
    data = await state.get_data()
    await state.set_state(AdOrder.confirm)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Təsdiqlə və Göndər", callback_data="confirm_bot_ad")],
        [InlineKeyboardButton(text="❌ Ləğv et", callback_data="back_main")]
    ])
    await message.answer(f"📋 <b>Xülasə:</b>\n\n<b>Başlıq:</b> {data['title']}\n<b>Link:</b> {data['link']}\n<b>İştirakçı:</b> {data['max_users']} nəfər\n<b>Hər nəfərə:</b> {data['reward']} coin\n<b>Ümumi xərc:</b> {data['price']} coin\n\nTəsdiqləyirsinizmi?", reply_markup=kb)

@dp.callback_query(F.data == "confirm_bot_ad", AdOrder.confirm)
async def cb_confirm_bot_ad(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = cb.from_user.id
    
    update_balance(uid, -data['price'])
    conn = db()
    conn.execute("INSERT INTO bot_ads (user_id, title, link, reward, max_users, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)", 
                 (uid, data['title'], data['link'], data['reward'], data['max_users'], datetime.now().isoformat()))
    ad_id = conn.lastrowid
    conn.commit()
    conn.close()
    
    await state.clear()
    await cb.message.edit_text("✅ Reklam sifarişiniz qəbul edildi! Admin təsdiqlədikdən sonra "Tapşırıqlar" bölməsində yayımlanacaq.", reply_markup=main_menu(uid))
    
    try:
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Təsdiqlə", callback_data=f"app_botad_{ad_id}")],
            [InlineKeyboardButton(text="❌ Rədd et", callback_data=f"rej_botad_{ad_id}")]
        ])
        await bot.send_message(ADMIN_ID, f"🔔 <b>Yeni Bot Reklamı!</b>\n\n<b>ID:</b> {ad_id}\n<b>Başlıq:</b> {data['title']}\n<b>Limit:</b> {data['max_users']} nəfər\n<b>Mükafat:</b> {data['reward']} coin", reply_markup=admin_kb)
    except: pass

# ---------- KANAL REKLAMI ----------
@dp.callback_query(F.data == "channel_ad")
async def cb_channel_ad(cb: CallbackQuery, state: FSMContext):
    u = get_user(cb.from_user.id)
    if u['balance'] < 10:
        await cb.answer("❌ Balansınız kifayət etmir! Minimum 10 coin lazımdır.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 saat - 10 coin", callback_data="chad_10_1")],
        [InlineKeyboardButton(text="3 saat - 15 coin", callback_data="chad_15_3")],
        [InlineKeyboardButton(text="10 saat - 25 coin", callback_data="chad_25_10")],
        [InlineKeyboardButton(text="❌ Ləğv et", callback_data="back_main")]
    ])
    await cb.message.edit_text("📢 <b>Kanal Reklamı</b>\n\nReklamınızın əsas kanalda nə qədər qalmasını seçin:", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("chad_"))
async def cb_chad_pkg(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split("_")
    price = int(parts[1])
    duration = int(parts[2])
    
    await state.update_data(price=price, duration=duration)
    await state.set_state(ChannelAd.content)
    await cb.message.edit_text("✍️ Reklam üçün <b>mətni</b>, <b>linki</b> və ya <b>şəkli</b> göndərin:\nLəğv etmək üçün /cancel yazın.")
    await cb.answer()

@dp.message(ChannelAd.content)
async def process_chad_content(message: Message, state: FSMContext):
    data = await state.get_data()
    uid = message.from_user.id
    
    # Mətni və ya medianı götürürük
    content = message.text if message.text else message.caption
    if not content: 
        return await message.answer("Zəhmət olmasa mətn və ya şəkil göndərin.")
        
    update_balance(uid, -data['price'])
    
    conn = db()
    conn.execute("INSERT INTO channel_ads (user_id, content, price, duration_hours, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)", 
                 (uid, content, data['price'], data['duration'], datetime.now().isoformat()))
    ad_id = conn.lastrowid
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer("✅ Reklam sifarişiniz qəbul edildi! Admin təsdiqlədikdən sonra kanalda paylaşılacaq.", reply_markup=main_menu(uid))
    
    try:
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Təsdiqlə və Kanalda Paylaş", callback_data=f"app_chad_{ad_id}")],
            [InlineKeyboardButton(text="❌ Rədd et (Pulu qaytar)", callback_data=f"rej_chad_{ad_id}")]
        ])
        await bot.send_message(ADMIN_ID, f"🔔 <b>Yeni Kanal Reklamı!</b>\n\n<b>ID:</b> {ad_id}\n<b>Müddət:</b> {data['duration']} saat\n<b>Mətn:</b> {content}", reply_markup=admin_kb)
    except: pass

# ---------- TAPŞIRIQLAR ----------
@dp.callback_query(F.data == "tasks")
async def cb_tasks(cb: CallbackQuery):
    conn = db()
    tasks = conn.execute("SELECT * FROM bot_ads WHERE status='approved' AND current_users < max_users").fetchall()
    conn.close()
    
    if not tasks:
        await cb.answer("Hazırda aktiv tapşırıq yoxdur.", show_alert=True)
        return
        
    await cb.message.edit_text("📋 <b>Tapşırıqlar</b>\n\nTapşırıqları yerinə yetirərək coin qazanın:", reply_markup=main_menu(cb.from_user.id))
    
    for t in tasks:
        conn = db()
        completed = conn.execute("SELECT 1 FROM task_completions WHERE user_id=? AND ad_id=?", (cb.from_user.id, t['id'])).fetchone()
        conn.close()
        if not completed:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Kanala Qoşul", url=t['link'])],
                [InlineKeyboardButton(text="✅ Yoxla və Coin Qazan", callback_data=f"chk_task_{t['id']}")]
            ])
            await cb.message.answer(f"<b>{t['title']}</b>\nMükafat: {t['reward']} coin\nQalan yer: {t['max_users'] - t['current_users']}", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("chk_task_"))
async def cb_chk_task(cb: CallbackQuery):
    task_id = int(cb.data.replace("chk_task_", ""))
    uid = cb.from_user.id
    conn = db()
    
    task = conn.execute("SELECT * FROM bot_ads WHERE id=?", (task_id,)).fetchone()
    if not task or task['current_users'] >= task['max_users']:
        conn.close()
        return await cb.answer("❌ Tapşırıq artıq dolub.", show_alert=True)
        
    completed = conn.execute("SELECT 1 FROM task_completions WHERE user_id=? AND ad_id=?", (uid, task_id)).fetchone()
    if completed:
        conn.close()
        return await cb.answer("❌ Bu tapşırığı artıq etmisiniz.", show_alert=True)
        
    # Qeydiyyat və balans artırma
    conn.execute("INSERT INTO task_completions (user_id, ad_id) VALUES (?, ?)", (uid, task_id))
    conn.execute("UPDATE bot_ads SET current_users = current_users + 1 WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    
    update_balance(uid, task['reward'])
    
    # Əgər limit dolubsa, tapşırığı bağlayırıq
    if task['current_users'] + 1 >= task['max_users']:
        conn = db()
        conn.execute("UPDATE bot_ads SET status='completed' WHERE id=?", (task_id,))
        conn.commit()
        conn.close()
        
    await cb.message.edit_text(f"✅ Tapşırıq tamamlandı! +{task['reward']} coin hesabınıza əlavə edildi.")
    await cb.answer("✅ Təbriklər!")

# ---------- DƏSTƏK SİSTEMİ ----------
@dp.callback_query(F.data == "support")
async def cb_support(cb: CallbackQuery, state: FSMContext):
    await state.set_state(SupportTicket.message)
    await cb.message.edit_text("💬 <b>Dəstək Xidməti</b>\n\nZəhmət olmasa sualınızı və ya probleminizi yazın. Admin tezliklə cavab verəcək.\nLəğv etmək üçün /cancel yazın.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Geri", callback_data="back_main")]]))
    await cb.answer()

@dp.message(SupportTicket.message)
async def process_support_message(message: Message, state: FSMContext):
    uid = message.from_user.id
    text = message.text or message.caption or "Media fayl"
    
    await state.clear()
    await message.answer("✅ Mesajınız adminə göndərildi. Tezliklə cavab alacaqsınız.", reply_markup=main_menu(uid))
    
    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Cavab yaz", callback_data=f"reply_{uid}")]])
        await bot.send_message(ADMIN_ID, f"💬 <b>Dəstək Müraciəti</b>\n\n<b>İstifadəçi:</b> {message.from_user.full_name}\n<b>ID:</b> <code>{uid}</code>\n\n<b>Mesaj:</b> {text}", reply_markup=kb)
    except: pass

# ---------- ADMIN PANEL ----------
@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    await cb.message.edit_text("👨‍💻 <b>Admin Paneli</b>", reply_markup=admin_menu())
    await cb.answer()

@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    conn = db()
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    bot_ads = conn.execute("SELECT COUNT(*) FROM bot_ads WHERE status='pending'").fetchone()[0]
    ch_ads = conn.execute("SELECT COUNT(*) FROM channel_ads WHERE status='pending'").fetchone()[0]
    conn.close()
    await cb.message.edit_text(f"📊 <b>Statistika</b>\n\n👥 İstifadəçi: {users}\n⏳ Gözləyən Tapşırıq Reklamı: {bot_ads}\n⏳ Gözləyən Kanal Reklamı: {ch_ads}", reply_markup=admin_menu())
    await cb.answer()

# Admin: Coin Əlavə Et
@dp.callback_query(F.data == "admin_add_coin")
async def cb_admin_add_coin(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID: return
    await state.set_state(AdminAddTask.title) # Müvəqqəti istifadə
    await cb.message.edit_text("👤 İstifadəçinin <b>ID</b> nömrəsini yazın:")
    await cb.answer()

# (Admin Cavab Yaratma)
@dp.callback_query(F.data.startswith("reply_"))
async def cb_admin_reply(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID: return
    target_uid = int(cb.data.replace("reply_", ""))
    await state.update_data(target_uid=target_uid)
    await state.set_state(AdminReply.message)
    await cb.message.answer("✍️ İstifadəçiyə cavabınızı yazın:")
    await cb.answer()

@dp.message(AdminReply.message)
async def process_admin_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    target_uid = data['target_uid']
    await state.clear()
    
    try:
        await bot.send_message(target_uid, f"💬 <b>Admin Cavabı:</b>\n\n{message.text}")
        await message.answer("✅ Cavab istifadəçiyə göndərildi.", reply_markup=main_menu(message.from_user.id))
    except:
        await message.answer("❌ İstifadəçiyə mesaj getmədi (botu bloklayıb).", reply_markup=main_menu(message.from_user.id))

# Admin Təsdiqləmə (Bot Reklamı)
@dp.callback_query(F.data.startswith("app_botad_"))
async def cb_app_botad(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    ad_id = int(cb.data.replace("app_botad_", ""))
    conn = db()
    conn.execute("UPDATE bot_ads SET status='approved' WHERE id=?", (ad_id,))
    conn.commit()
    conn.close()
    await cb.message.edit_text(f"✅ Tapşırıq reklamı (ID: {ad_id}) təsdiqləndi və "Tapşırıqlar" bölməsinə əlavə edildi.")
    await cb.answer()

# Admin Rədd Etmə (Bot Reklamı - Pulu qaytar)
@dp.callback_query(F.data.startswith("rej_botad_"))
async def cb_rej_botad(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    ad_id = int(cb.data.replace("rej_botad_", ""))
    conn = db()
    ad = conn.execute("SELECT * FROM bot_ads WHERE id=?", (ad_id,)).fetchone()
    if ad:
        conn.execute("UPDATE bot_ads SET status='rejected' WHERE id=?", (ad_id,))
        conn.commit()
        update_balance(ad['user_id'], ad['max_users'] * 5) # 5 coin qaytarılır
        await cb.message.edit_text(f"❌ Reklam rədd edildi, pul istifadəçiyə qaytarıldı.")
    conn.close()
    await cb.answer()

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Əməliyyat ləğv edildi.", reply_markup=main_menu(message.from_user.id))

# ---------- AVTOMATİK TƏMİZLƏYİCİ (Kanal Reklamı üçün) ----------
async def cleaner_worker():
    while True:
        try:
            conn = db()
            ads = conn.execute("SELECT * FROM channel_ads WHERE status='approved'").fetchall()
            now = datetime.now()
            for ad in ads:
                if ad['expire_at']:
                    expire = datetime.fromisoformat(ad['expire_at'])
                    if now >= expire:
                        # Vaxt bitib, kanaldan sil
                        try:
                            await bot.delete_message(chat_id=CHANNEL_ID, message_id=ad['channel_message_id'])
                        except: pass
                        conn.execute("UPDATE channel_ads SET status='expired' WHERE id=?", (ad['id'],))
                        conn.commit()
            conn.close()
        except Exception as e:
            print(f"Təmizləyici xətası: {e}")
        await asyncio.sleep(60) # Hər dəqiqə yoxla

# ---------- Polling ----------
async def start_polling():
    init_db()
    asyncio.create_task(cleaner_worker()) # Arxa planda təmizləyicini başlat
    await dp.start_polling(bot, handle_signals=False)
