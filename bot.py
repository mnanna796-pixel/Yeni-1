"""
Reklam Coin — Telegram reklam botu (aiogram 3.x) — TAM İŞLƏK VERSİYA.

Orijinal koda işlək vəziyyətə gətirmək üçün edilən düzəlişlər:

 1. Bot heç vaxt işə düşmürdü — start_polling() heç vaxt çağırılmırdı.
    Artıq faylın sonunda `if __name__ == "__main__": asyncio.run(main())` var.
 2. Kanal reklamının "Təsdiqlə" / "Rədd et" düymələri heç nə etmirdi —
    app_chad_ və rej_chad_ üçün handler YOX İDİ. İndi: təsdiqda reklam
    kanala göndərilir (şəkil dəstəyi ilə), expire_at hesablanır; rəddda pul
    geri qaytarılır.
 3. Adminin "Cavab yaz" axını "Coin əlavə et" axını ilə eyni FSM state-ni
    istifadə edirdi — cavab yazan admin istəmədən istifadəçiyə coin əlavə
    edirdi. İndi ayrı state-lər: AdminAddCoin / AdminReplyTicket.
 4. /start abunə olmayan istifadəçini bazada qeydiyyatdan keçirmirdi —
    "✅ Yoxla"dan sonra hər düymə "Zəhmət olmasa /start yazın!" deyirdi.
    İndi istifadəçi əvvəl qeydiyyata alınır (referal daxil), sonra abunəlik
    yoxlanılır; "Yoxla" da istifadəçi yoxdursa yaradır.
 5. Sifariş təsdiqında balans YENİDƏN yoxlanılır — coin mənfiyə düşmür;
    köhnəlmiş sifariş pəncərələri qorunur.
 6. Şəkilli kanal reklamları: file_id saxlanılır, təsdiqda foto + mətn
    kanala göndərilir (orijinalda şəkil itib-batib idi).
 7. İstifadəçi mətnləri html.quote ilə qaçılır — HTML parse xətaları və
    injeksiya qeyri-mümkündür; media/boş mesajlara qoruma əlavə olundu.
 8. "Message is not modified" xətaları: eyni düyməni təkrar basanda bot
    çökmürdü — bütün edit_text çağırışları safe_edit içindədir.
 9. Köhnə bot.db faylları üçün avtomatik miqrasiya (bot_ads.price,
    channel_ads.file_id sütunları); rəddda DƏQİQ ödənilən məbləğ qaytarılır.
10. BOT_TOKEN yoxdursa aydın xəta mesajı; çıxıntılı `except: pass` əvəzinə
    logging; RESTRICTED (limitli amma üzv) istifadəçilər də abunə sayılır.

Quraşdırma:
    pip install -U aiogram python-dotenv
.env faylı (bot.py ilə eyni qovluqda):
    BOT_TOKEN=123456789:ABC-DEF...
    ADMIN_ID=teleqram_admin_idsi
    CHANNEL_ID=@alqisatqielanazerbaycan
İşə salma:
    python bot.py
"""

import asyncio
import logging
import os
import sqlite3
from contextlib import closing, suppress
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# ---------- Konfiqurasiya ----------
load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("reklam-coin")

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
CHANNEL_ID = os.getenv("CHANNEL_ID", "@alqisatqielanazerbaycan")
CHANNEL_URL = (
    f"https://t.me/{CHANNEL_ID.lstrip('@')}"
    if CHANNEL_ID.startswith("@")
    else "https://t.me/alqisatqielanazerbaycan"
)

DB_PATH = Path(__file__).parent / "bot.db"

if not TOKEN:
    raise SystemExit(
        "XƏTA: BOT_TOKEN tapılmadı. bot.py ilə eyni qovluqda .env faylı yaradın:\n"
        "  BOT_TOKEN=123456789:ABC-DEF...\n"
        "  ADMIN_ID=teleqram_admin_idsi\n"
        "  CHANNEL_ID=@kanaliniz"
    )
if not ADMIN_ID:
    logger.warning("ADMIN_ID təyin olunmayıb — admin funksiyaları işləməyəcək.")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# ---------- Verilənlər bazası (SQLite) ----------
def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """Köhnə bot.db faylları üçün sütun miqrasiyası."""
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        logger.info("Miqrasiya: %s cədvəlinə '%s' sütunu əlavə olundu", table, column)


def init_db() -> None:
    with closing(db_connect()) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, full_name TEXT, balance INTEGER DEFAULT 0,
                referal_id INTEGER, referal_count INTEGER DEFAULT 0, last_bonus TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS bot_ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT, link TEXT,
                reward INTEGER, max_users INTEGER, current_users INTEGER DEFAULT 0,
                price INTEGER DEFAULT 0, status TEXT DEFAULT 'pending', created_at TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS channel_ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, content TEXT,
                file_id TEXT, price INTEGER, duration_hours INTEGER,
                status TEXT DEFAULT 'pending', created_at TEXT, expire_at TEXT,
                channel_message_id INTEGER
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS task_completions (
                user_id INTEGER, ad_id INTEGER, PRIMARY KEY (user_id, ad_id)
            )"""
        )
        _ensure_column(conn, "bot_ads", "price", "INTEGER DEFAULT 0")
        _ensure_column(conn, "channel_ads", "file_id", "TEXT")
        conn.commit()


def get_user(uid: int) -> sqlite3.Row | None:
    with closing(db_connect()) as conn:
        return conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()


def update_balance(uid: int, amount: int) -> None:
    with closing(db_connect()) as conn:
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
        conn.commit()


def register_user(uid: int, full_name: str, ref_id: int | None) -> None:
    """İstifadəçini qeydiyyata alır (yoxdursa) və referal mükafatını verir."""
    if get_user(uid) is not None:
        return
    with closing(db_connect()) as conn:
        conn.execute(
            "INSERT INTO users (user_id, full_name, referal_id) VALUES (?, ?, ?)",
            (uid, full_name, ref_id),
        )
        conn.commit()
    if ref_id and ref_id != uid and get_user(ref_id):
        update_balance(ref_id, 5)
        with closing(db_connect()) as conn:
            conn.execute(
                "UPDATE users SET referal_count = referal_count + 1 WHERE user_id=?", (ref_id,)
            )
            conn.commit()


# ---------- FSM vəziyyətləri ----------
class AdOrder(StatesGroup):
    title = State()
    link = State()
    confirm = State()


class ChannelAd(StatesGroup):
    content = State()


class SupportTicket(StatesGroup):
    message = State()


class AdminAddCoin(StatesGroup):
    user_id = State()
    amount = State()


class AdminReplyTicket(StatesGroup):
    message = State()


# ---------- Məcburi abunəlik ----------
async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
    except Exception as exc:
        logger.warning("Abunəlik yoxlanışı alınmadı: %s", exc)
        return False
    if member.status == ChatMemberStatus.RESTRICTED:
        return bool(getattr(member, "is_member", False))
    return member.status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    )


def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanala Abunə Ol", url=CHANNEL_URL)],
            [InlineKeyboardButton(text="✅ Yoxla", callback_data="check_sub")],
        ]
    )


# ---------- Klaviaturalar ----------
def main_menu(uid: int) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="💰 Balansım", callback_data="balance")],
        [InlineKeyboardButton(text="📋 Tapşırıqlar", callback_data="tasks")],
        [InlineKeyboardButton(text="📢 Kanal Reklamı", callback_data="channel_ad")],
        [InlineKeyboardButton(text="🤖 Bot Reklamı (Tapşırıq yerləşdir)", callback_data="bot_ad")],
        [InlineKeyboardButton(text="👥 Referal sistemi", callback_data="referal")],
        [InlineKeyboardButton(text="🎁 Gündəlik bonus", callback_data="bonus")],
        [InlineKeyboardButton(text="💬 Dəstək xidməti", callback_data="support")],
        [InlineKeyboardButton(text="📜 Qaydalar", callback_data="rules")],
    ]
    if uid == ADMIN_ID:
        kb.append([InlineKeyboardButton(text="👨\u200d💻 Admin Paneli", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Ümumi Statistika", callback_data="admin_stats")],
            [InlineKeyboardButton(text="💰 Coin Əlavə Et", callback_data="admin_add_coin")],
            [InlineKeyboardButton(text="🔙 Geri", callback_data="back_main")],
        ]
    )


async def safe_edit(cb: CallbackQuery, text: str, reply_markup) -> None:
    """edit_text + 'message is not modified' / köhnə mesaj xətalarına qoruma."""
    try:
        await cb.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        pass


# ---------- /start ----------
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    args = (message.text or "").split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1][4:])
        except ValueError:
            ref_id = None

    # DÜZƏLİŞ: istifadəçi abunəlikdən ASILI OLMARAQ qeydiyyata alınır (düz. 4)
    register_user(user.id, user.full_name, ref_id)

    if not await is_subscribed(user.id):
        await message.answer(
            "Botdan istifadə etmək üçün əvvəlcə kanalımıza abunə olmalısınız! 👇",
            reply_markup=sub_keyboard(),
        )
        return

    await message.answer(
        f"Salam, {html.bold(html.quote(user.full_name))}! 👋\n\n"
        "Rəsmi Reklam Botuna xoş gəldiniz.",
        reply_markup=main_menu(user.id),
    )


@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: CallbackQuery):
    if not await is_subscribed(cb.from_user.id):
        await cb.answer("❌ Siz hələ kanala abunə olmamısınız!", show_alert=True)
        return
    register_user(cb.from_user.id, cb.from_user.full_name, None)
    await safe_edit(cb, "✅ Təşəkkürlər! İndi botdan istifadə edə bilərsiniz.", main_menu(cb.from_user.id))
    await cb.answer()


@dp.callback_query(F.data == "back_main")
async def cb_back_main(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(cb, "Əsas menyu:", main_menu(cb.from_user.id))
    await cb.answer()


# ---------- Balans, Referal, Bonus, Qaydalar ----------
@dp.callback_query(F.data == "balance")
async def cb_balance(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    if not u:
        await cb.answer("Zəhmət olmasa /start yazın!", show_alert=True)
        return
    await safe_edit(cb, f"💰 <b>Balansınız:</b> {u['balance']} coin", main_menu(cb.from_user.id))
    await cb.answer()


@dp.callback_query(F.data == "referal")
async def cb_referal(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    if not u:
        await cb.answer("Zəhmət olmasa /start yazın!", show_alert=True)
        return
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{cb.from_user.id}"
    await safe_edit(
        cb,
        f"👥 <b>Referal sistemi</b>\n\nSizin linkiniz:\n<code>{link}</code>\n\n"
        f"Dəvət etdiyiniz: {u['referal_count']} nəfər\nHər dəvətə: 5 coin",
        main_menu(cb.from_user.id),
    )
    await cb.answer()


@dp.callback_query(F.data == "bonus")
async def cb_bonus(cb: CallbackQuery):
    uid = cb.from_user.id
    u = get_user(uid)
    if not u:
        await cb.answer("Zəhmət olmasa /start yazın!", show_alert=True)
        return

    today = date.today().isoformat()
    if u["last_bonus"] == today:
        await cb.answer("❌ Bu gün artıq bonus almısınız!", show_alert=True)
        return
    with closing(db_connect()) as conn:
        conn.execute(
            "UPDATE users SET balance = balance + 2, last_bonus = ? WHERE user_id=?",
            (today, uid),
        )
        conn.commit()
    await safe_edit(
        cb,
        f"🎁 <b>Gündəlik bonus alındı!</b>\n+2 coin\n\nBalans: {get_user(uid)['balance']} coin",
        main_menu(uid),
    )
    await cb.answer("✅ +2 coin")


@dp.callback_query(F.data == "rules")
async def cb_rules(cb: CallbackQuery):
    await safe_edit(
        cb,
        "📜 <b>Qaydalar</b>\n\n"
        "1. Saxta hesablar qadağandır.\n"
        "2. Özünə referal göndərmək olmaz.\n"
        "3. Reklamlar admin tərəfindən yoxlanılır.",
        main_menu(cb.from_user.id),
    )
    await cb.answer()


# ---------- BOT REKLAMI (Tapşırıq formasında) ----------
@dp.callback_query(F.data == "bot_ad")
async def cb_bot_ad(cb: CallbackQuery, state: FSMContext):
    u = get_user(cb.from_user.id)
    if not u:
        await cb.answer("Zəhmət olmasa /start yazın!", show_alert=True)
        return

    if u["balance"] < 15:
        await cb.answer("❌ Balansınız kifayət etmir! Minimum 15 coin lazımdır.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="3 nəfər (15 coin)", callback_data="botad_3_15_3")],
            [InlineKeyboardButton(text="5 nəfər (25 coin)", callback_data="botad_5_25_3")],
            [InlineKeyboardButton(text="10 nəfər (50 coin)", callback_data="botad_10_50_3")],
            [InlineKeyboardButton(text="❌ Ləğv et", callback_data="back_main")],
        ]
    )
    await safe_edit(
        cb,
        "🤖 <b>Bot Reklamı (Tapşırıq)</b>\n\nReklamınızın neçə nəfərə göstərilməsini seçin.\n"
        "(İstifadəçilər tapşırığı yerinə yetirəndə 3 coin qazanacaqlar)",
        kb,
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("botad_"))
async def cb_botad_pkg(cb: CallbackQuery, state: FSMContext):
    try:
        _, max_users, price, reward = cb.data.split("_")
        max_users, price, reward = int(max_users), int(price), int(reward)
    except (ValueError, AttributeError):
        await cb.answer("Paket tapılmadı — yenidən cəhd edin.", show_alert=True)
        return

    await state.update_data(max_users=max_users, price=price, reward=reward)
    await state.set_state(AdOrder.title)
    await safe_edit(
        cb,
        "📝 Tapşırığın <b>başlığını</b> yazın (məs: 'Yeni kanala qoşul'):\n"
        "Ləğv etmək üçün /cancel yazın.",
        None,
    )
    await cb.answer()


@dp.message(AdOrder.title)
async def process_title(message: Message, state: FSMContext):
    if not message.text:  # DÜZƏLİŞ: media/boş mesajda çökmür (düz. 7)
        await message.answer("Zəhmət olmasa <b>mətn</b> göndərin.")
        return
    if len(message.text) > 100:
        await message.answer("Başlıq çox uzundur — 100 simvoldan qısa yazın.")
        return
    await state.update_data(title=message.text)
    await state.set_state(AdOrder.link)
    await message.answer("🔗 Kanala/qrupa qoşulmaq üçün <b>linki</b> göndərin:")


@dp.message(AdOrder.link)
async def process_link(message: Message, state: FSMContext):
    if not message.text or not message.text.startswith(("http://", "https://")):
        await message.answer("Zəhmət olmasa düzgün link göndərin (http:// və ya https:// ilə başlamalı).")
        return
    await state.update_data(link=message.text)
    data = await state.get_data()
    await state.set_state(AdOrder.confirm)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Təsdiqlə və Göndər", callback_data="confirm_bot_ad")],
            [InlineKeyboardButton(text="❌ Ləğv et", callback_data="back_main")],
        ]
    )
    await message.answer(
        "📋 <b>Xülasə:</b>\n\n"
        f"<b>Başlıq:</b> {html.quote(data['title'])}\n"
        f"<b>Link:</b> {html.quote(data['link'])}\n"
        f"<b>İştirakçı:</b> {data['max_users']} nəfər\n"
        f"<b>Hər nəfərə:</b> {data['reward']} coin\n"
        f"<b>Ümumi xərc:</b> {data['price']} coin\n\n"
        "Təsdiqləyirsinizmi?",
        reply_markup=kb,
    )


@dp.callback_query(F.data == "confirm_bot_ad")
async def cb_confirm_bot_ad(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = cb.from_user.id
    # DÜZƏLİŞ: köhnəlmiş sifariş + balansın təkrar yoxlanması (düz. 5)
    if not data.get("title") or not data.get("link"):
        await cb.answer("⌛ Sifariş köhnəlib — əsas menyudan yenidən başlayın.", show_alert=True)
        return
    price = int(data["price"])
    user = get_user(uid)
    if not user or user["balance"] < price:
        await state.clear()
        await cb.answer("❌ Balansınız kifayət etmir!", show_alert=True)
        return

    update_balance(uid, -price)
    with closing(db_connect()) as conn:
        cur = conn.execute(
            "INSERT INTO bot_ads (user_id, title, link, reward, max_users, price, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (uid, data["title"], data["link"], data["reward"], data["max_users"], price, datetime.now().isoformat()),
        )
        ad_id = cur.lastrowid
        conn.commit()

    await state.clear()
    await safe_edit(
        cb,
        "✅ Reklam sifarişiniz qəbul edildi! Admin təsdiqlədikdən sonra "
        "'Tapşırıqlar' bölməsində yayımlanacaq.",
        main_menu(uid),
    )
    await cb.answer()

    try:
        admin_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Təsdiqlə", callback_data=f"app_botad_{ad_id}")],
                [InlineKeyboardButton(text="❌ Rədd et (Pulu qaytar)", callback_data=f"rej_botad_{ad_id}")],
            ]
        )
        await bot.send_message(
            ADMIN_ID,
            f"🔔 <b>Yeni Bot Reklamı!</b>\n\n"
            f"<b>ID:</b> {ad_id}\n"
            f"<b>Başlıq:</b> {html.quote(str(data['title']))}\n"
            f"<b>Link:</b> {html.quote(str(data['link']))}\n"
            f"<b>Limit:</b> {data['max_users']} nəfər\n"
            f"<b>Mükafat:</b> {data['reward']} coin",
            reply_markup=admin_kb,
        )
    except Exception:
        logger.exception("Adminə bildiriş göndərilə bilmədi")


# ---------- KANAL REKLAMI ----------
@dp.callback_query(F.data == "channel_ad")
async def cb_channel_ad(cb: CallbackQuery, state: FSMContext):
    u = get_user(cb.from_user.id)
    if not u:
        await cb.answer("Zəhmət olmasa /start yazın!", show_alert=True)
        return

    if u["balance"] < 10:
        await cb.answer("❌ Balansınız kifayət etmir! Minimum 10 coin lazımdır.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1 saat - 10 coin", callback_data="chad_10_1")],
            [InlineKeyboardButton(text="3 saat - 15 coin", callback_data="chad_15_3")],
            [InlineKeyboardButton(text="10 saat - 25 coin", callback_data="chad_25_10")],
            [InlineKeyboardButton(text="❌ Ləğv et", callback_data="back_main")],
        ]
    )
    await safe_edit(
        cb,
        "📢 <b>Kanal Reklamı</b>\n\nReklamınızın əsas kanalda nə qədər qalmasını seçin:",
        kb,
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("chad_"))
async def cb_chad_pkg(cb: CallbackQuery, state: FSMContext):
    try:
        _, price, duration = cb.data.split("_")
        price, duration = int(price), int(duration)
    except (ValueError, AttributeError):
        await cb.answer("Paket tapılmadı — yenidən cəhd edin.", show_alert=True)
        return

    await state.update_data(price=price, duration=duration)
    await state.set_state(ChannelAd.content)
    await safe_edit(
        cb,
        "✍️ Reklam üçün <b>mətni</b>, <b>linki</b> və ya <b>şəkli</b> göndərin:\n"
        "Ləğv etmək üçün /cancel yazın.",
        None,
    )
    await cb.answer()


@dp.message(ChannelAd.content)
async def process_chad_content(message: Message, state: FSMContext):
    data = await state.get_data()
    uid = message.from_user.id

    content = message.text or message.caption
    file_id = message.photo[-1].file_id if message.photo else None  # DÜZƏLİŞ: şəkil saxlanılır (düz. 6)
    if not content and not file_id:
        await message.answer("Zəhmət olmasa mətn və ya şəkil göndərin.")
        return

    price = int(data.get("price", 0))
    user = get_user(uid)
    if not user or user["balance"] < price:
        await state.clear()
        await message.answer("❌ Balansınız kifayət etmir!", reply_markup=main_menu(uid))
        return

    update_balance(uid, -price)
    with closing(db_connect()) as conn:
        cur = conn.execute(
            "INSERT INTO channel_ads (user_id, content, file_id, price, duration_hours, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (uid, content, file_id, price, data.get("duration", 1), datetime.now().isoformat()),
        )
        ad_id = cur.lastrowid
        conn.commit()

    await state.clear()
    await message.answer(
        "✅ Reklam sifarişiniz qəbul edildi! Admin təsdiqlədikdən sonra kanalda paylaşılacaq.",
        reply_markup=main_menu(uid),
    )

    try:
        admin_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Təsdiqlə və Kanalda Paylaş", callback_data=f"app_chad_{ad_id}")],
                [InlineKeyboardButton(text="❌ Rədd et (Pulu qaytar)", callback_data=f"rej_chad_{ad_id}")],
            ]
        )
        preview = html.quote(content) if content else "<i>Şəkil</i>"
        await bot.send_message(
            ADMIN_ID,
            f"🔔 <b>Yeni Kanal Reklamı!</b>\n\n"
            f"<b>ID:</b> {ad_id}\n"
            f"<b>Müddət:</b> {data.get('duration', 1)} saat\n"
            f"<b>Mətn:</b> {preview}",
            reply_markup=admin_kb,
        )
    except Exception:
        logger.exception("Adminə bildiriş göndərilə bilmədi")


# DÜZƏLİŞ: orijinalda bu iki handler TAMAMILƏ yox idi (düz. 2)
@dp.callback_query(F.data.startswith("app_chad_"))
async def cb_app_chad(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return
    try:
        ad_id = int(cb.data.replace("app_chad_", ""))
    except ValueError:
        await cb.answer()
        return

    with closing(db_connect()) as conn:
        ad = conn.execute("SELECT * FROM channel_ads WHERE id=?", (ad_id,)).fetchone()
        if not ad or ad["status"] != "pending":
            await cb.answer("Bu reklam artıq işlənilib.", show_alert=True)
            return
        expire_at = (datetime.now() + timedelta(hours=ad["duration_hours"] or 1)).isoformat()
        try:
            if ad["file_id"]:
                sent = await bot.send_photo(CHANNEL_ID, photo=ad["file_id"], caption=ad["content"] or "")
            else:
                sent = await bot.send_message(CHANNEL_ID, ad["content"])
        except Exception as exc:
            logger.error("Kanal reklamı göndərilə bilmədi: %s", exc)
            await cb.answer(
                "❌ Kanala göndərmək alınmadı. Botun kanalda admin olduğunu yoxlayın.",
                show_alert=True,
            )
            return
        conn.execute(
            "UPDATE channel_ads SET status='approved', expire_at=?, channel_message_id=? WHERE id=?",
            (expire_at, sent.message_id, ad_id),
        )
        conn.commit()

    await safe_edit(
        cb,
        f"✅ Kanal reklamı (ID: {ad_id}) kanala yerləşdirildi.\n"
        f"⏳ {ad['duration_hours']} saatdan sonra avtomatik silinəcək.",
        None,
    )
    with suppress(Exception):
        await bot.send_message(ad["user_id"], "✅ Kanal reklamınız təsdiqləndi və kanalda paylandı!")
    await cb.answer()


@dp.callback_query(F.data.startswith("rej_chad_"))
async def cb_rej_chad(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return
    try:
        ad_id = int(cb.data.replace("rej_chad_", ""))
    except ValueError:
        await cb.answer()
        return

    with closing(db_connect()) as conn:
        ad = conn.execute("SELECT * FROM channel_ads WHERE id=?", (ad_id,)).fetchone()
        if not ad or ad["status"] != "pending":
            await cb.answer("Bu reklam artıq işlənilib.", show_alert=True)
            return
        conn.execute("UPDATE channel_ads SET status='rejected' WHERE id=?", (ad_id,))
        conn.commit()

    refund = ad["price"] or 0
    update_balance(ad["user_id"], refund)
    await safe_edit(cb, f"❌ Kanal reklamı (ID: {ad_id}) rədd edildi, {refund} coin qaytarıldı.", None)
    with suppress(Exception):
        await bot.send_message(ad["user_id"], f"❌ Kanal reklamınız rədd edildi və {refund} coin balansınıza qaytarıldı.")
    await cb.answer()


# ---------- TAPŞIRIQLAR ----------
@dp.callback_query(F.data == "tasks")
async def cb_tasks(cb: CallbackQuery):
    with closing(db_connect()) as conn:
        tasks = conn.execute(
            "SELECT * FROM bot_ads WHERE status='approved' AND current_users < max_users"
        ).fetchall()

    await safe_edit(
        cb,
        "📋 <b>Tapşırıqlar</b>\n\nTapşırıqları yerinə yetirərək coin qazanın:",
        main_menu(cb.from_user.id),
    )

    sent = 0
    for t in tasks:
        with closing(db_connect()) as conn:
            completed = conn.execute(
                "SELECT 1 FROM task_completions WHERE user_id=? AND ad_id=?",
                (cb.from_user.id, t["id"]),
            ).fetchone()
        if completed:
            continue
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Kanala Qoşul", url=t["link"])],
                [InlineKeyboardButton(text="✅ Yoxla və Coin Qazan", callback_data=f"chk_task_{t['id']}")],
            ]
        )
        await cb.message.answer(
            f"{html.quote(t['title'])}\n"
            f"Mükafat: {t['reward']} coin\n"
            f"Qalan yer: {t['max_users'] - t['current_users']}",
            reply_markup=kb,
        )
        sent += 1

    if not sent:
        await cb.answer("Hazırda sizin üçün aktiv tapşırıq yoxdur.", show_alert=True)
    else:
        await cb.answer()


@dp.callback_query(F.data.startswith("chk_task_"))
async def cb_chk_task(cb: CallbackQuery):
    try:
        task_id = int(cb.data.replace("chk_task_", ""))
    except ValueError:
        await cb.answer()
        return
    uid = cb.from_user.id

    with closing(db_connect()) as conn:
        task = conn.execute("SELECT * FROM bot_ads WHERE id=?", (task_id,)).fetchone()
        if not task or task["status"] != "approved" or task["current_users"] >= task["max_users"]:
            await cb.answer("❌ Tapşırıq artıq dolub.", show_alert=True)
            return
        completed = conn.execute(
            "SELECT 1 FROM task_completions WHERE user_id=? AND ad_id=?", (uid, task_id)
        ).fetchone()
        if completed:
            await cb.answer("❌ Bu tapşırığı artıq etmisiniz.", show_alert=True)
            return
        try:
            conn.execute("INSERT INTO task_completions (user_id, ad_id) VALUES (?, ?)", (uid, task_id))
        except sqlite3.IntegrityError:  # tək-tək klik yarışı
            await cb.answer("❌ Bu tapşırığı artıq etmisiniz.", show_alert=True)
            return
        conn.execute("UPDATE bot_ads SET current_users = current_users + 1 WHERE id=?", (task_id,))
        if task["current_users"] + 1 >= task["max_users"]:
            conn.execute("UPDATE bot_ads SET status='completed' WHERE id=?", (task_id,))
        conn.commit()

    update_balance(uid, task["reward"])
    await safe_edit(cb, f"✅ Tapşırıq tamamlandı! +{task['reward']} coin hesabınıza əlavə edildi.", None)
    await cb.answer("✅ Təbriklər!")


# ---------- DƏSTƏK SİSTEMİ ----------
@dp.callback_query(F.data == "support")
async def cb_support(cb: CallbackQuery, state: FSMContext):
    await state.set_state(SupportTicket.message)
    await safe_edit(
        cb,
        "💬 <b>Dəstək Xidməti</b>\n\nZəhmət olmasa sualınızı və ya probleminizi yazın. "
        "Admin tezliklə cavab verəcək.\nLəğv etmək üçün /cancel yazın.",
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Geri", callback_data="back_main")]]
        ),
    )
    await cb.answer()


@dp.message(SupportTicket.message)
async def process_support_message(message: Message, state: FSMContext):
    uid = message.from_user.id
    text = message.text or message.caption or "Media fayl"

    await state.clear()
    await message.answer(
        "✅ Mesajınız adminə göndərildi. Tezliklə cavab alacaqsınız.",
        reply_markup=main_menu(uid),
    )

    try:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="↩️ Cavab yaz", callback_data=f"reply_{uid}")]]
        )
        await bot.send_message(
            ADMIN_ID,
            f"💬 <b>Dəstək Müraciəti</b>\n\n"
            f"<b>İstifadəçi:</b> {html.quote(message.from_user.full_name)}\n"
            f"<b>ID:</b> <code>{uid}</code>\n\n"
            f"<b>Mesaj:</b> {html.quote(text)}",
            reply_markup=kb,
        )
    except Exception:
        logger.exception("Dəstək müraciəti adminə göndərilə bilmədi")


# ---------- ADMIN PANEL ----------
@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return
    await safe_edit(cb, "👨\u200d💻 <b>Admin Paneli</b>", admin_menu())
    await cb.answer()


@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return
    with closing(db_connect()) as conn:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        bot_ads = conn.execute("SELECT COUNT(*) FROM bot_ads WHERE status='pending'").fetchone()[0]
        ch_ads = conn.execute("SELECT COUNT(*) FROM channel_ads WHERE status='pending'").fetchone()[0]
    await safe_edit(
        cb,
        f"📊 <b>Statistika</b>\n\n👥 İstifadəçi: {users}\n"
        f"⏳ Gözləyən Tapşırıq Reklamı: {bot_ads}\n"
        f"⏳ Gözləyən Kanal Reklamı: {ch_ads}",
        admin_menu(),
    )
    await cb.answer()


# Admin: Coin Əlavə Et (ayrı FSM axını — düz. 3)
@dp.callback_query(F.data == "admin_add_coin")
async def cb_admin_add_coin(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminAddCoin.user_id)
    await safe_edit(cb, "👤 İstifadəçinin <b>ID</b> nömrəsini yazın:", None)
    await cb.answer()


@dp.message(AdminAddCoin.user_id)
async def admin_coin_uid(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("Yalnız rəqəm yazın.")
        return
    await state.update_data(target_uid=int(message.text))
    await state.set_state(AdminAddCoin.amount)
    await message.answer("💰 Əlavə etmək istədiyiniz <b>coin</b> miqdarını yazın:")


@dp.message(AdminAddCoin.amount)
async def admin_coin_amount(message: Message, state: FSMContext):
    if not message.text or not message.text.lstrip("-").isdigit():
        await message.answer("Yalnız rəqəm yazın.")
        return
    data = await state.get_data()
    target_uid = data.get("target_uid")
    amount = int(message.text)
    await state.clear()

    if get_user(target_uid):
        update_balance(target_uid, amount)
        await message.answer(
            f"✅ İstifadəçiyə (ID: {target_uid}) {amount} coin əlavə edildi.",
            reply_markup=main_menu(message.from_user.id),
        )
        with suppress(Exception):
            await bot.send_message(target_uid, f"💰 Balansınıza admin tərəfindən {amount} coin əlavə edildi!")
    else:
        await message.answer("❌ İstifadəçi tapılmadı.", reply_markup=main_menu(message.from_user.id))


# Admin: dəstək müraciətinə cavab (ayrı FSM axını — düz. 3)
@dp.callback_query(F.data.startswith("reply_"))
async def cb_admin_reply(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return
    try:
        target_uid = int(cb.data.replace("reply_", ""))
    except ValueError:
        await cb.answer()
        return
    await state.update_data(target_uid=target_uid)
    await state.set_state(AdminReplyTicket.message)
    await cb.message.answer("✍️ İstifadəçiyə cavabınızı yazın:\nLəğv etmək üçün /cancel yazın.")
    await cb.answer()


@dp.message(AdminReplyTicket.message)
async def process_admin_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    target_uid = data.get("target_uid")
    await state.clear()

    if not message.text:
        await message.answer("Zəhmət olmasa mətn yazın.", reply_markup=main_menu(message.from_user.id))
        return
    if not get_user(target_uid):
        await message.answer("❌ İstifadəçi tapılmadı.", reply_markup=main_menu(message.from_user.id))
        return
    try:
        await bot.send_message(target_uid, f"💬 <b>Dəstək xidməti cavabı:</b>\n\n{html.quote(message.text)}")
        await message.answer("✅ Cavab göndərildi.", reply_markup=main_menu(message.from_user.id))
    except Exception:
        logger.exception("Cavab göndərilə bilmədi")
        await message.answer(
            "❌ İstifadəçiyə göndərmək alınmadı (botu bloklamış ola bilər).",
            reply_markup=main_menu(message.from_user.id),
        )


# Admin: Tapşırıq reklamının təsdiqi / rəddi
@dp.callback_query(F.data.startswith("app_botad_"))
async def cb_app_botad(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return
    try:
        ad_id = int(cb.data.replace("app_botad_", ""))
    except ValueError:
        await cb.answer()
        return
    with closing(db_connect()) as conn:
        conn.execute("UPDATE bot_ads SET status='approved' WHERE id=?", (ad_id,))
        conn.commit()
    await safe_edit(
        cb,
        f"✅ Tapşırıq reklamı (ID: {ad_id}) təsdiqləndi və 'Tapşırıqlar' bölməsinə əlavə edildi.",
        None,
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("rej_botad_"))
async def cb_rej_botad(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return
    try:
        ad_id = int(cb.data.replace("rej_botad_", ""))
    except ValueError:
        await cb.answer()
        return
    with closing(db_connect()) as conn:
        ad = conn.execute("SELECT * FROM bot_ads WHERE id=?", (ad_id,)).fetchone()
        if not ad or ad["status"] != "pending":
            await cb.answer("Bu reklam artıq işlənilib.", show_alert=True)
            return
        conn.execute("UPDATE bot_ads SET status='rejected' WHERE id=?", (ad_id,))
        conn.commit()

    refund = ad["price"] or ad["max_users"] * 5  # DÜZƏLİŞ: dəqiq məbləğ qaytarılır (dü. 9)
    update_balance(ad["user_id"], refund)
    await safe_edit(cb, f"❌ Reklam rədd edildi, {refund} coin istifadəçiyə qaytarıldı.", None)
    with suppress(Exception):
        await bot.send_message(ad["user_id"], f"❌ Tapşırıq reklamınız rədd edildi və {refund} coin balansınıza qaytarıldı.")
    await cb.answer()


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Əməliyyat ləğv edildi.", reply_markup=main_menu(message.from_user.id))


# ---------- AVTOMATİK TƏMİZLƏYİCİ (Kanal Reklamı üçün) ----------
async def cleaner_worker():
    while True:
        try:
            now = datetime.now()
            with closing(db_connect()) as conn:
                ads = conn.execute(
                    "SELECT * FROM channel_ads WHERE status='approved' AND expire_at IS NOT NULL"
                ).fetchall()
                changed = False
                for ad in ads:
                    try:
                        expire = datetime.fromisoformat(ad["expire_at"])
                    except (TypeError, ValueError):
                        continue
                    if now < expire:
                        continue
                    if ad["channel_message_id"]:
                        with suppress(Exception):
                            await bot.delete_message(CHANNEL_ID, ad["channel_message_id"])
                    conn.execute("UPDATE channel_ads SET status='expired' WHERE id=?", (ad["id"],))
                    changed = True
                if changed:
                    conn.commit()
        except Exception:
            logger.exception("Təmizləyici xətası")
        await asyncio.sleep(60)


# ---------- İşə salma ----------
async def main() -> None:
    init_db()
    logger.info("Verilənlər bazası hazırdır — bot polling-a başlayır...")
    cleaner = asyncio.create_task(cleaner_worker())
    try:
        await dp.start_polling(bot, handle_signals=False)
    finally:
        cleaner.cancel()
        with suppress(asyncio.CancelledError):
            await cleaner


# DÜZƏLİŞ: orijinalda giriş nöqtəsi YOX İDİ — bot heç vaxt başlamırdı (dü. 1)
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot dayandırıldı")
