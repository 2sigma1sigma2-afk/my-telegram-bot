import asyncio
import logging
import math
import random
import string
import aiosqlite
import sys
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ================= ⚙️ НАСТРОЙКИ ⚙️ =================
BOT_TOKEN = '7716127075:AAEs55gkC1Dk6NcC9tAdkW-6oM-5bRcag-w'
OWNER_USERNAME = 'illusiononce'

# Цены в Telegram Stars (XTR)
PRICES = {'7': 35, '30': 120, 'life': 175}
ALLOWED_PREFIXES = ["ЧСВ", "Красавчик", "Буст", "Ez"]
LINE = "━━━━━━━━━━━━━━━━━━━━"

WELCOME_MSG = (
    "🌟 **NORYX PAY — ТВОЙ ВЫБОР** 🌟\n"
    f"{LINE}\n"
    "🚀 Управляй подпиской, меняй префиксы и скачивай эксклюзивные сборки.\n\n"
    "💎 **Выбери раздел в меню:**"
)
# ==================================================

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class BotStates(StatesGroup):
    waiting_for_promo = State()
    waiting_for_key = State()
    waiting_for_activations = State()

# --- 🛠 РАБОТА С БД ---
async def init_db():
    async with aiosqlite.connect('noryx_users.db') as db:
        # Таблица пользователей
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            uid INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            prefix TEXT DEFAULT '',
            role TEXT DEFAULT 'FREE',
            expiry_date TEXT DEFAULT 'Нет',
            discount REAL DEFAULT 0.0
        )''')
        
        # Таблица ключей
        await db.execute('''CREATE TABLE IF NOT EXISTS generated_keys (
            key_code TEXT PRIMARY KEY,
            days INTEGER,
            role TEXT DEFAULT 'BETA',
            activations_left INTEGER DEFAULT 1
        )''')
        
        # --- АВТО-МИГРАЦИИ (Добавление колонок в старую базу) ---
        # Проверка discount в users
        try:
            await db.execute("ALTER TABLE users ADD COLUMN discount REAL DEFAULT 0.0")
        except: pass
        
        # Проверка activations_left в generated_keys
        try:
            await db.execute("ALTER TABLE generated_keys ADD COLUMN activations_left INTEGER DEFAULT 1")
        except: pass
            
        await db.commit()

async def get_user_data(user_id: int, first_name: str, username: str):
    async with aiosqlite.connect('noryx_users.db') as db:
        async with db.execute("SELECT uid, prefix, role, expiry_date, discount FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
        if not user:
            await db.execute("INSERT INTO users (user_id, first_name, username) VALUES (?, ?, ?)", (user_id, first_name, username))
            await db.commit()
            return await get_user_data(user_id, first_name, username)
    return user

# --- ⌨️ КЛАВИАТУРЫ ---
def get_main_kb(username: str, role: str):
    kb = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🎭 Префиксы", callback_data="prefix_menu")],
        [InlineKeyboardButton(text="🔑 Активация", callback_data="activate_key")],
        [InlineKeyboardButton(text="🛒 Магазин", callback_data="buy_beta")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo")]
    ]
    if role in ['BETA', 'VIP']:
        kb.insert(2, [InlineKeyboardButton(text="📁 СКАЧАТЬ BETA", callback_data="download_beta")])
    
    if username and username.lower() == OWNER_USERNAME.lower():
        kb.append([InlineKeyboardButton(text="⚡ АДМИН-ПАНЕЛЬ ⚡", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_back_kb(target="back_main"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=target)]])

# --- 🚀 ХЕНДЛЕРЫ ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    u = await get_user_data(message.from_user.id, message.from_user.first_name, message.from_user.username)
    await message.answer(WELCOME_MSG, parse_mode="Markdown", reply_markup=get_main_kb(message.from_user.username, u[2]))

@dp.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    u = await get_user_data(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    await callback.message.edit_text(WELCOME_MSG, parse_mode="Markdown", reply_markup=get_main_kb(callback.from_user.username, u[2]))

@dp.callback_query(F.data == "profile")
async def call_profile(callback: CallbackQuery):
    u = await get_user_data(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    pref_tag = f"[{u[1]}] " if u[1] else ""
    text = (
        f"👤 **ЛИЧНЫЙ КАБИНЕТ**\n"
        f"{LINE}\n"
        f"🆔 **Твой UID:** `{u[0]}`\n"
        f"🏷 **Никнейм:** {pref_tag}`{callback.from_user.first_name}`\n\n"
        f"👑 **Роль:** `{u[2]}`\n"
        f"⏳ **Доступ до:** `{u[3]}`\n"
        f"{LINE}"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_back_kb())

@dp.callback_query(F.data == "prefix_menu")
async def prefix_menu(callback: CallbackQuery):
    btns = []
    row = []
    for p in ALLOWED_PREFIXES:
        row.append(InlineKeyboardButton(text=f"💠 {p}", callback_data=f"setp_{p}"))
        if len(row) == 2:
            btns.append(row)
            row = []
    btns.append([InlineKeyboardButton(text="🗑 Убрать префикс", callback_data="setp_clear")])
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    await callback.message.edit_text(f"🎭 **МЕНЮ ПРЕФИКСОВ**\n{LINE}\nВыбери стиль:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("setp_"))
async def set_user_prefix(callback: CallbackQuery):
    choice = callback.data.split("_")[1]
    new_pref = "" if choice == "clear" else choice
    async with aiosqlite.connect('noryx_users.db') as db:
        await db.execute("UPDATE users SET prefix = ? WHERE user_id = ?", (new_pref, callback.from_user.id))
        await db.commit()
    await callback.answer(f"✅ Префикс обновлен!", show_alert=True)
    await prefix_menu(callback)

@dp.callback_query(F.data == "download_beta")
async def download_beta(callback: CallbackQuery):
    u = await get_user_data(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    if u[2] not in ['BETA', 'VIP']:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    await callback.message.edit_text(f"📁 **СБОРКА NORYX BETA**\n{LINE}\n🔗 [СКАЧАТЬ](https://workupload.com/file/n8tTZVrzCcF)\n🗝 Пароль: `Нету`", parse_mode="Markdown", reply_markup=get_back_kb())

# --- 🛡 АДМИНКА ---
@dp.callback_query(F.data == "admin_main")
async def admin_main(callback: CallbackQuery):
    if callback.from_user.username.lower() != OWNER_USERNAME.lower(): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Юзеры", callback_data="admin_users")],
        [InlineKeyboardButton(text="🔑 Создать ключ", callback_data="admin_gen_menu")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text(f"🛡 **АДМИН-ЦЕНТР**\n{LINE}", reply_markup=kb)

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    async with aiosqlite.connect('noryx_users.db') as db:
        async with db.execute("SELECT uid, first_name, role, prefix FROM users") as cursor:
            users = await cursor.fetchall()
    msg = f"👥 **СПИСОК ЮЗЕРОВ**\n{LINE}\n"
    for u in users:
        msg += f"• {u[1]} (ID: `{u[0]}`), Статус: `{u[2]}`, Префикс: `{u[3] if u[3] else '—'}`\n"
    await callback.message.edit_text(msg, parse_mode="Markdown", reply_markup=get_back_kb("admin_main"))

@dp.callback_query(F.data == "admin_gen_menu")
async def admin_gen_menu(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="7 дней", callback_data="prep_7"), InlineKeyboardButton(text="30 дней", callback_data="prep_30")],
        [InlineKeyboardButton(text="Навсегда", callback_data="prep_9999"), InlineKeyboardButton(text="◀️ Назад", callback_data="admin_main")]
    ])
    await callback.message.edit_text("🔑 **СРОК КЛЮЧА:**", reply_markup=kb)

@dp.callback_query(F.data.startswith("prep_"))
async def start_gen_key(callback: CallbackQuery, state: FSMContext):
    await state.update_data(gen_days=int(callback.data.split("_")[1]))
    await state.set_state(BotStates.waiting_for_activations)
    await callback.message.edit_text("🔢 **Количество активаций:**")

@dp.message(BotStates.waiting_for_activations)
async def finish_gen_key(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    act = int(message.text)
    data = await state.get_data()
    days = data['gen_days']
    role = 'VIP' if days == 9999 else 'BETA'
    key = f"NORYX-{''.join(random.choices(string.ascii_uppercase + string.digits, k=10))}"
    async with aiosqlite.connect('noryx_users.db') as db:
        await db.execute("INSERT INTO generated_keys (key_code, days, role, activations_left) VALUES (?, ?, ?, ?)", (key, days, role, act))
        await db.commit()
    await state.clear()
    await message.answer(f"✅ Ключ: `{key}`", reply_markup=get_back_kb("admin_main"))

# --- 🛒 МАГАЗИН (STARS) ---
@dp.callback_query(F.data == "buy_beta")
async def shop_menu(callback: CallbackQuery):
    u = await get_user_data(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    def calc(price): return math.ceil(price * (1 - u[4]))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"7д • {calc(35)} ⭐", callback_data="starbuy_7")],
        [InlineKeyboardButton(text=f"30д • {calc(120)} ⭐", callback_data="starbuy_30")],
        [InlineKeyboardButton(text=f"Навсегда • {calc(175)} ⭐", callback_data="starbuy_life")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text(f"🛒 **МАГАЗИН**\n{LINE}", reply_markup=kb)

@dp.callback_query(F.data.startswith("starbuy_"))
async def send_invoice(callback: CallbackQuery):
    plan = callback.data.split("_")[1]
    u = await get_user_data(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    price = 35 if plan == '7' else (120 if plan == '30' else 175)
    await bot.send_invoice(callback.from_user.id, title=f"Noryx {plan}", description="Активация подписки", payload=f"sub_{plan}", provider_token="", currency="XTR", prices=[LabeledPrice(label="XTR", amount=math.ceil(price*(1-u[4])))])

@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(message: Message):
    p = message.successful_payment.invoice_payload
    days = 9999 if "life" in p else (30 if "30" in p else 7)
    role = "VIP" if days == 9999 else "BETA"
    exp = "Навсегда" if days == 9999 else (datetime.now() + timedelta(days=days)).strftime("%d.%m.%Y")
    async with aiosqlite.connect('noryx_users.db') as db:
        await db.execute("UPDATE users SET role=?, expiry_date=? WHERE user_id=?", (role, exp, message.from_user.id))
        await db.commit()
    await message.answer(f"🎉 Оплачено! Роль: {role}", reply_markup=get_main_kb(message.from_user.username, role))

# --- 🔑 АКТИВАЦИЯ ---
@dp.callback_query(F.data == "activate_key")
async def call_activate(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_key)
    await callback.message.edit_text("🔑 **ВВЕДИТЕ КЛЮЧ:**", reply_markup=get_back_kb())

@dp.message(BotStates.waiting_for_key)
async def proc_key(message: Message, state: FSMContext):
    key_code = message.text.strip()
    async with aiosqlite.connect('noryx_users.db') as db:
        async with db.execute("SELECT days, role, activations_left FROM generated_keys WHERE key_code = ?", (key_code,)) as c:
            data = await c.fetchone()
        if data:
            days, role, left = data
            exp = "Навсегда" if days == 9999 else (datetime.now() + timedelta(days=days)).strftime("%d.%m.%Y")
            await db.execute("UPDATE users SET role=?, expiry_date=? WHERE user_id=?", (role, exp, message.from_user.id))
            if left > 1: await db.execute("UPDATE generated_keys SET activations_left = activations_left - 1 WHERE key_code = ?", (key_code,))
            else: await db.execute("DELETE FROM generated_keys WHERE key_code = ?", (key_code,))
            await db.commit()
            await state.clear()
            await message.answer(f"✅ Активировано!", reply_markup=get_main_kb(message.from_user.username, role))
        else: await message.answer("❌ Ошибка!")

@dp.callback_query(F.data == "promo")
async def call_promo(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_promo)
    await callback.message.edit_text("🎁 **ВВЕДИ ПРОМОКОД:**", reply_markup=get_back_kb())

@dp.message(BotStates.waiting_for_promo)
async def proc_promo(message: Message, state: FSMContext):
    if message.text.strip().upper() == "NORYX7":
        async with aiosqlite.connect('noryx_users.db') as db:
            await db.execute("UPDATE users SET discount = 0.07 WHERE user_id = ?", (message.from_user.id,))
            await db.commit()
        await state.clear()
        await message.answer("✅ Скидка 7%!", reply_markup=get_back_kb())

async def main():
    await init_db()
    print("🚀 NORYX STAR BOT STARTED!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
    
