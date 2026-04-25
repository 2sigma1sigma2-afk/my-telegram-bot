import asyncio
import logging
import math
import random
import string
import aiosqlite
import sys
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ================= НАСТРОЙКИ =================
BOT_TOKEN = '7716127075:AAEs55gkC1Dk6NcC9tAdkW-6oM-5bRcag-w'
OWNER_USERNAME = 'illusiononce'

PROMO_CODES = {'NORYX7': 0.07}
BASE_PRICES = {'7_days': 35, '14_days': 70, '30_days': 120, 'lifetime': 175}

HELP_TEXT = (
    "ℹ **Как пользоваться ботом**\n\n"
    "✅ Нажми Login в клиенте Noryx и подтверди вход в боте.\n"
    "✅ Для инвайта в beta-чат активируй ключ или купи BETA.\n"
    "✅ После вступления в чат нажми «Проверить beta» для обновления роли."
)
# ==============================================

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class BotStates(StatesGroup):
    waiting_for_promo = State()
    waiting_for_key = State()

# --- УМНАЯ ИНИЦИАЛИЗАЦИЯ БД ---
async def init_db():
    async with aiosqlite.connect('noryx_users.db') as db:
        # Создаем таблицу, если её нет
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            uid INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            prefix TEXT DEFAULT '',
            role TEXT DEFAULT 'FREE',
            sub_type TEXT DEFAULT 'FREE',
            has_beta INTEGER DEFAULT 0,
            active_promo_discount REAL DEFAULT 0.0,
            expiry_date TEXT DEFAULT 'Нет'
        )''')
        
        # --- БЛОК АВТО-ФИКСА (Миграция) ---
        # Проверяем наличие колонки expiry_date, если её нет - добавляем
        cursor = await db.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in await cursor.fetchall()]
        
        if 'expiry_date' not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN expiry_date TEXT DEFAULT 'Нет'")
        if 'username' not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN username TEXT")
        
        await db.execute('''CREATE TABLE IF NOT EXISTS generated_keys (
            key_code TEXT PRIMARY KEY,
            days INTEGER,
            role TEXT DEFAULT 'BETA'
        )''')
        await db.commit()

async def get_user_data(user_id: int, first_name: str, username: str):
    async with aiosqlite.connect('noryx_users.db') as db:
        async with db.execute(
            "SELECT uid, prefix, role, sub_type, has_beta, active_promo_discount, expiry_date FROM users WHERE user_id = ?", 
            (user_id,)
        ) as cursor:
            user = await cursor.fetchone()
        
        if not user:
            await db.execute(
                "INSERT INTO users (user_id, first_name, username) VALUES (?, ?, ?)", 
                (user_id, first_name, username)
            )
            await db.commit()
            return await get_user_data(user_id, first_name, username)
    return user

# --- КЛАВИАТУРЫ ---
def get_main_kb(username: str, has_beta: bool):
    kb = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🔄 Проверить BETA", callback_data="check_beta")],
        [InlineKeyboardButton(text="🔑 Активировать ключ", callback_data="activate_key")],
        [InlineKeyboardButton(text="⭐ Купить BETA", callback_data="buy_beta")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo")],

    ]
    if has_beta:
        kb.append([InlineKeyboardButton(text="⬇ Скачать бета", callback_data="download_beta")])
    if username == OWNER_USERNAME:
        kb.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_buy_kb(discount: float):
    def p(base): return math.ceil(base * (1 - discount))
    kb = [
        [InlineKeyboardButton(text=f"📅 7 дней • {p(BASE_PRICES['7_days'])} ⭐", callback_data="buy_7"),
         InlineKeyboardButton(text=f"📅 14 дней • {p(BASE_PRICES['14_days'])} ⭐", callback_data="buy_14")],
        [InlineKeyboardButton(text=f"📅 30 дней • {p(BASE_PRICES['30_days'])} ⭐", callback_data="buy_30"),
         InlineKeyboardButton(text=f"🎉 Навсегда • {p(BASE_PRICES['lifetime'])} ⭐", callback_data="buy_life")],
        [InlineKeyboardButton(text="💸 Переводом админу", callback_data="buy_admin")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="help")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- ХЕНДЛЕРЫ ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user_data(message.from_user.id, message.from_user.first_name, message.from_user.username)
    await message.answer(
        f"Привет, **{message.from_user.first_name}**, что бы вы хотели?",
        parse_mode="Markdown",
        reply_markup=get_main_kb(message.from_user.username, bool(user[4]))
    )

@dp.callback_query(F.data == "help")
async def call_help(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user_data(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    await callback.message.edit_text(HELP_TEXT, parse_mode="Markdown", reply_markup=get_main_kb(callback.from_user.username, bool(user[4])))

@dp.callback_query(F.data == "profile")
async def call_profile(callback: CallbackQuery):
    u = await get_user_data(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    name = f"[{u[1]}] {callback.from_user.first_name}" if u[1] else callback.from_user.first_name
    text = (
        f"**Noryx PAY**\n👤 Профиль\n\n🧾 **UID:** {u[0]}\n🏷 **Имя:** {name}\n🎭 **Роль:** {u[2]}\n"
        f"📦 **Подписка:** {u[3]}\n⏳ **Доступ до:** {u[6]}"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_kb(callback.from_user.username, bool(u[4])))

# --- АДМИНКА ---
@dp.callback_query(F.data == "admin_panel")
async def call_admin(callback: CallbackQuery):
    if callback.from_user.username != OWNER_USERNAME: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="7 дней", callback_data="gen_7"), InlineKeyboardButton(text="30 дней", callback_data="gen_30")],
        [InlineKeyboardButton(text="Навсегда", callback_data="gen_9999")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="help")]
    ])
    await callback.message.edit_text("🛠 **Генерация ключа**", parse_mode="Markdown", reply_markup=kb)

@dp.callback_query(F.data.startswith("gen_"))
async def handle_gen(callback: CallbackQuery):
    days = int(callback.data.split("_")[1])
    key = f"NORYX-{''.join(random.choices(string.ascii_uppercase + string.digits, k=12))}"
    async with aiosqlite.connect('noryx_users.db') as db:
        await db.execute("INSERT INTO generated_keys (key_code, days) VALUES (?, ?)", (key, days))
        await db.commit()
    await callback.message.answer(f"✅ **Ключ создан!**\n\n`{key}`\nСрок: {days} дн.", parse_mode="Markdown")

# --- АКТИВАЦИЯ ---
@dp.callback_query(F.data == "activate_key")
async def call_activate(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_key)
    await callback.message.edit_text("🔑 **Введите ваш ключ:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="help")]]))

@dp.message(BotStates.waiting_for_key)
async def proc_key(message: Message, state: FSMContext):
    key_code = message.text.strip()
    async with aiosqlite.connect('noryx_users.db') as db:
        async with db.execute("SELECT days, role FROM generated_keys WHERE key_code = ?", (key_code,)) as c:
            key_data = await c.fetchone()
        if key_data:
            days, role = key_data
            exp = (datetime.now() + timedelta(days=days)).strftime("%d.%m.%Y")
            await db.execute("UPDATE users SET role=?, sub_type=?, has_beta=1, expiry_date=? WHERE user_id=?", (role, f"{days}д", exp, message.from_user.id))
            await db.execute("DELETE FROM generated_keys WHERE key_code = ?", (key_code,))
            await db.commit()
            await state.clear()
            await message.answer(f"✅ Активировано! До: {exp}", reply_markup=get_main_kb(message.from_user.username, True))
        else:
            await message.answer("❌ Неверный ключ!")

# --- СКИДКИ И ПРОЧЕЕ ---
@dp.callback_query(F.data == "promo")
async def call_promo(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_promo)
    await callback.message.edit_text("🎁 **Введите промокод:**")

@dp.message(BotStates.waiting_for_promo)
async def proc_promo(message: Message, state: FSMContext):
    if message.text.strip().upper() in PROMO_CODES:
        async with aiosqlite.connect('noryx_users.db') as db:
            await db.execute("UPDATE users SET active_promo_discount = 0.07 WHERE user_id = ?", (message.from_user.id,))
            await db.commit()
        await state.clear()
        await message.answer("✅ Скидка 7% применена!")
    else: await message.answer("❌ Код неверный.")

@dp.callback_query(F.data == "buy_beta")
async def call_buy(callback: CallbackQuery):
    u = await get_user_data(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    await callback.message.edit_text("🌑 **Покупка подписки**", reply_markup=get_buy_kb(u[5]))

@dp.callback_query(F.data == "download_beta")
async def call_down(callback: CallbackQuery):
    await callback.message.answer("📁 **Ссылка:** `https://noryx.dev/download`")

@dp.callback_query(F.data == "check_beta")
async def call_check(callback: CallbackQuery):
    await callback.answer("👁 Проверка...", show_alert=True)

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
