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

ALLOWED_PREFIXES = ["ЧСВ", "Красавчик", "Буст", "Ez"]
LINE = "━━━━━━━━━━━━━━━━━━━━"

WELCOME_MSG = (
    "🌟 **NORYX PAY — ТВОЙ ВЫБОР** 🌟\n"
    f"{LINE}\n"
    "🚀 Управляй подпиской, меняй префиксы и скачивай эксклюзивные сборки.\n\n"
    "💎 **Выбери раздел в меню:**"
)

def generate_password(length=12):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# ==================================================

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class BotStates(StatesGroup):
    waiting_for_promo = State()
    waiting_for_key = State()
    waiting_for_activations = State()
    gen_days = State()

class AuthStates(StatesGroup):
    reg_username = State()
    reg_choice = State() 
    reg_password = State() 
    login_username = State()
    login_password = State()
    change_password = State()

# --- 🛠 РАБОТА С БД ---
async def init_db():
    async with aiosqlite.connect('noryx_users.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            uid INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            prefix TEXT DEFAULT '',
            role TEXT DEFAULT 'FREE',
            expiry_date TEXT DEFAULT 'Нет',
            discount REAL DEFAULT 0.0,
            app_username TEXT,
            app_password TEXT
        )''')
        
        await db.execute('''CREATE TABLE IF NOT EXISTS generated_keys (
            key_code TEXT PRIMARY KEY,
            days INTEGER,
            role TEXT DEFAULT 'BETA',
            activations_left INTEGER DEFAULT 1
        )''')
        
        # Миграции
        try: await db.execute("ALTER TABLE users ADD COLUMN discount REAL DEFAULT 0.0")
        except: pass
        try: await db.execute("ALTER TABLE users ADD COLUMN app_username TEXT")
        except: pass
        try: await db.execute("ALTER TABLE users ADD COLUMN app_password TEXT")
        except: pass
        await db.commit()

async def get_user_data(user_id: int, first_name: str, username: str):
    async with aiosqlite.connect('noryx_users.db') as db:
        async with db.execute("SELECT uid, prefix, role, expiry_date, discount, app_username FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
        if not user:
            await db.execute("INSERT INTO users (user_id, first_name, username) VALUES (?, ?, ?)", (user_id, first_name, username))
            await db.commit()
            return await get_user_data(user_id, first_name, username)
    return user

# --- ⌨️ КЛАВИАТУРЫ ---
def get_auth_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Регистрация", callback_data="auth_reg")],
        [InlineKeyboardButton(text="🔑 Войти", callback_data="auth_login")]
    ])

def get_reg_choice_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⌨️ Свой пароль", callback_data="pass_own")],
        [InlineKeyboardButton(text="🎲 Рандомный", callback_data="pass_random")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_auth")]
    ])

def get_main_kb(username: str, role: str):
    kb = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🎭 Префиксы", callback_data="prefix_menu")],
        [InlineKeyboardButton(text="🔑 Активация", callback_data="activate_key"),
         InlineKeyboardButton(text="🛒 Магазин", callback_data="buy_beta")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo")]
    ]
    if role in ['BETA', 'VIP']:
        kb.insert(2, [InlineKeyboardButton(text="📁 СКАЧАТЬ BETA", callback_data="download_beta")])
    if username and username.lower() == OWNER_USERNAME.lower():
        kb.append([InlineKeyboardButton(text="⚡ АДМИНКА ⚡", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сменить пароль", callback_data="change_pass_start")],
        [InlineKeyboardButton(text="🚪 Выйти из аккаунта", callback_data="logout")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])

def get_back_kb(target="back_main"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=target)]])

# --- 🔐 РЕГИСТРАЦИЯ И ВХОД ---

@dp.callback_query(F.data == "back_to_auth")
async def back_to_auth(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("👋 Авторизуйтесь:", reply_markup=get_auth_kb())

@dp.callback_query(F.data == "auth_reg")
async def auth_reg_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AuthStates.reg_username)
    await callback.message.edit_text("📝 **РЕГИСТРАЦИЯ**\n\nВведите ваш **Логин**:", parse_mode="Markdown", reply_markup=get_back_kb("back_to_auth"))

@dp.message(AuthStates.reg_username)
async def auth_reg_user(message: Message, state: FSMContext):
    app_user = message.text.strip()
    async with aiosqlite.connect('noryx_users.db') as db:
        async with db.execute("SELECT uid FROM users WHERE app_username = ?", (app_user,)) as cur:
            if await cur.fetchone():
                await message.answer("❌ Этот логин занят!", reply_markup=get_back_kb("back_to_auth"))
                return
    await state.update_data(reg_username=app_user)
    await state.set_state(AuthStates.reg_choice)
    await message.answer(f"Логин `{app_user}` свободен. Выберите тип пароля:", parse_mode="Markdown", reply_markup=get_reg_choice_kb())

@dp.callback_query(AuthStates.reg_choice, F.data == "pass_random")
async def reg_pass_random(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    login = data['reg_username']
    new_pass = generate_password()
    async with aiosqlite.connect('noryx_users.db') as db:
        await db.execute("UPDATE users SET app_username=?, app_password=? WHERE user_id=?", (login, new_pass, callback.from_user.id))
        await db.commit()
    await state.clear()
    u = await get_user_data(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    await callback.message.edit_text(f"✅ Готово!\nЛогин: `{login}`\nПароль: `{new_pass}`", parse_mode="Markdown")
    await callback.message.answer(WELCOME_MSG, parse_mode="Markdown", reply_markup=get_main_kb(callback.from_user.username, u[2]))

@dp.callback_query(AuthStates.reg_choice, F.data == "pass_own")
async def reg_pass_own_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AuthStates.reg_password)
    await callback.message.edit_text("🔒 Введите свой пароль:")

@dp.message(AuthStates.reg_password)
async def reg_pass_own_finish(message: Message, state: FSMContext):
    app_pass = message.text.strip()
    data = await state.get_data()
    async with aiosqlite.connect('noryx_users.db') as db:
        await db.execute("UPDATE users SET app_username=?, app_password=? WHERE user_id=?", (data['reg_username'], app_pass, message.from_user.id))
        await db.commit()
    await state.clear()
    u = await get_user_data(message.from_user.id, message.from_user.first_name, message.from_user.username)
    await message.answer("✅ Аккаунт создан!", reply_markup=get_main_kb(message.from_user.username, u[2]))

@dp.callback_query(F.data == "auth_login")
async def auth_login_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AuthStates.login_username)
    await callback.message.edit_text("🔑 Введите Логин:")

@dp.message(AuthStates.login_username)
async def auth_login_user(message: Message, state: FSMContext):
    await state.update_data(login_username=message.text.strip())
    await state.set_state(AuthStates.login_password)
    await message.answer("🔒 Введите Пароль:")

@dp.message(AuthStates.login_password)
async def auth_login_pass(message: Message, state: FSMContext):
    app_pass = message.text.strip()
    data = await state.get_data()
    async with aiosqlite.connect('noryx_users.db') as db:
        async with db.execute("SELECT uid, app_password FROM users WHERE app_username=?", (data['login_username'],)) as cur:
            acc = await cur.fetchone()
        
        if acc and acc[1] == app_pass:
            # Устранение конфликтов ID: удаляем временного юзера и привязываем Telegram к найденному аккаунту
            await db.execute("DELETE FROM users WHERE user_id=? AND app_username IS NULL", (message.from_user.id,))
            await db.execute("UPDATE users SET user_id=NULL WHERE user_id=?", (message.from_user.id,))
            await db.execute("UPDATE users SET user_id=? WHERE uid=?", (message.from_user.id, acc[0]))
            await db.commit()
            await state.clear()
            u = await get_user_data(message.from_user.id, message.from_user.first_name, message.from_user.username)
            await message.answer(f"✅ Вход выполнен!", reply_markup=get_main_kb(message.from_user.username, u[2]))
        else:
            await message.answer("❌ Неверный логин или пароль!", reply_markup=get_auth_kb())

# --- 👤 ПРОФИЛЬ И СМЕНА ПАРОЛЯ ---

@dp.callback_query(F.data == "change_pass_start")
async def change_pass_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AuthStates.change_password)
    await callback.message.edit_text("📝 Введите новый пароль:", reply_markup=get_back_kb("profile"))

@dp.message(AuthStates.change_password)
async def change_pass_finish(message: Message, state: FSMContext):
    new_p = message.text.strip()
    if len(new_p) < 4:
        await message.answer("❌ Минимум 4 символа!")
        return
    async with aiosqlite.connect('noryx_users.db') as db:
        await db.execute("UPDATE users SET app_password = ? WHERE user_id = ?", (new_p, message.from_user.id))
        await db.commit()
    await state.clear()
    await message.answer(f"✅ Пароль изменен на: `{new_p}`", parse_mode="Markdown")
    await call_profile(message)

@dp.callback_query(F.data == "logout")
async def logout_handler(callback: CallbackQuery):
    async with aiosqlite.connect('noryx_users.db') as db:
        await db.execute("UPDATE users SET user_id = NULL WHERE user_id = ?", (callback.from_user.id,))
        await db.commit()
    await callback.message.edit_text("👋 Вы вышли из аккаунта.", reply_markup=get_auth_kb())

@dp.callback_query(F.data == "profile")
async def call_profile(union: [CallbackQuery, Message]):
    user_id = union.from_user.id
    u = await get_user_data(user_id, union.from_user.first_name, union.from_user.username)
    text = (f"👤 **ПРОФИЛЬ**\n{LINE}\n🆔 UID: `{u[0]}`\n🔑 Логин: `{u[5]}`\n👑 Роль: `{u[2]}`\n⏳ До: `{u[3]}`\n{LINE}")
    if isinstance(union, CallbackQuery):
        await union.message.edit_text(text, parse_mode="Markdown", reply_markup=get_profile_kb())
    else:
        await union.answer(text, parse_mode="Markdown", reply_markup=get_profile_kb())

# --- 🚀 СТАРТ И ПРОЧЕЕ ---

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    u = await get_user_data(message.from_user.id, message.from_user.first_name, message.from_user.username)
    if not u[5]:
        await message.answer("👋 Привет! Авторизуйтесь:", reply_markup=get_auth_kb())
    else:
        await message.answer(WELCOME_MSG, parse_mode="Markdown", reply_markup=get_main_kb(message.from_user.username, u[2]))

@dp.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    u = await get_user_data(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    await callback.message.edit_text(WELCOME_MSG, parse_mode="Markdown", reply_markup=get_main_kb(callback.from_user.username, u[2]))

@dp.callback_query(F.data == "prefix_menu")
async def prefix_menu(callback: CallbackQuery):
    btns = [[InlineKeyboardButton(text=f"💠 {p}", callback_data=f"setp_{p}")] for p in ALLOWED_PREFIXES]
    btns.append([InlineKeyboardButton(text="🗑 Сброс", callback_data="setp_clear")])
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    await callback.message.edit_text("🎭 ПРЕФИКСЫ:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("setp_"))
async def set_user_prefix(callback: CallbackQuery):
    choice = callback.data.split("_")[1]
    new_pref = "" if choice == "clear" else choice
    async with aiosqlite.connect('noryx_users.db') as db:
        await db.execute("UPDATE users SET prefix = ? WHERE user_id = ?", (new_pref, callback.from_user.id))
        await db.commit()
    await callback.answer("✅ Готово!")
    await prefix_menu(callback)

# --- 🛡 АДМИНКА ---
@dp.callback_query(F.data == "admin_main")
async def admin_main(callback: CallbackQuery):
    if callback.from_user.username.lower() != OWNER_USERNAME.lower(): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Юзеры", callback_data="admin_users")],
        [InlineKeyboardButton(text="🔑 Создать ключ", callback_data="admin_gen_menu")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text("🛡 АДМИНКА", reply_markup=kb)

@dp.callback_query(F.data == "admin_gen_menu")
async def admin_gen_menu(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="7д", callback_data="prep_7"), InlineKeyboardButton(text="30д", callback_data="prep_30")],
        [InlineKeyboardButton(text="∞", callback_data="prep_9999"), InlineKeyboardButton(text="◀️ Назад", callback_data="admin_main")]
    ])
    await callback.message.edit_text("🔑 СРОК КЛЮЧА:", reply_markup=kb)

@dp.callback_query(F.data.startswith("prep_"))
async def start_gen_key(callback: CallbackQuery, state: FSMContext):
    await state.update_data(gen_days=int(callback.data.split("_")[1]))
    await state.set_state(BotStates.waiting_for_activations)
    await callback.message.edit_text("🔢 Кол-во активаций:")

@dp.message(BotStates.waiting_for_activations)
async def finish_gen_key(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    data = await state.get_data()
    key = f"NORYX-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"
    async with aiosqlite.connect('noryx_users.db') as db:
        await db.execute("INSERT INTO generated_keys (key_code, days, role, activations_left) VALUES (?, ?, ?, ?)", 
                         (key, data['gen_days'], 'VIP' if data['gen_days']==9999 else 'BETA', int(message.text)))
        await db.commit()
    await state.clear()
    await message.answer(f"✅ Ключ: `{key}`", reply_markup=get_back_kb("admin_main"))

# --- 🔑 АКТИВАЦИЯ ---
@dp.callback_query(F.data == "activate_key")
async def call_activate(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_key)
    await callback.message.edit_text("🔑 Введите ключ:", reply_markup=get_back_kb())

@dp.message(BotStates.waiting_for_key)
async def proc_key(message: Message, state: FSMContext):
    key_code = message.text.strip()
    async with aiosqlite.connect('noryx_users.db') as db:
        async with db.execute("SELECT days, role, activations_left FROM generated_keys WHERE key_code=?", (key_code,)) as cur:
            data = await cur.fetchone()
        if data:
            days, role, left = data
            exp = "Навсегда" if days == 9999 else (datetime.now() + timedelta(days=days)).strftime("%d.%m.%Y")
            await db.execute("UPDATE users SET role=?, expiry_date=? WHERE user_id=?", (role, exp, message.from_user.id))
            if left > 1: await db.execute("UPDATE generated_keys SET activations_left=activations_left-1 WHERE key_code=?", (key_code,))
            else: await db.execute("DELETE FROM generated_keys WHERE key_code=?", (key_code,))
            await db.commit()
            await state.clear()
            await message.answer("✅ Активировано!")
        else:
            await message.answer("❌ Неверный ключ!")

# --- 🛒 МАГАЗИН ---
@dp.callback_query(F.data == "buy_beta")
async def shop_menu(callback: CallbackQuery):
    u = await get_user_data(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    def price(p): return math.ceil(p * (1 - u[4]))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"7д • {price(35)} ⭐", callback_data="starbuy_7")],
        [InlineKeyboardButton(text=f"30д • {price(120)} ⭐", callback_data="starbuy_30")],
        [InlineKeyboardButton(text=f"Навсегда • {price(175)} ⭐", callback_data="starbuy_life")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text("🛒 МАГАЗИН (Stars)", reply_markup=kb)

@dp.callback_query(F.data.startswith("starbuy_"))
async def send_invoice(callback: CallbackQuery):
    plan = callback.data.split("_")[1]
    u = await get_user_data(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    cost = 35 if plan == '7' else (120 if plan == '30' else 175)
    await bot.send_invoice(callback.from_user.id, title=f"Noryx {plan}", description="Подписка", payload=f"sub_{plan}", 
                           provider_token="", currency="XTR", prices=[LabeledPrice(label="XTR", amount=math.ceil(cost*(1-u[4])))])

@dp.pre_checkout_query()
async def pre_checkout_handler(q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(message: Message):
    days = 9999 if "life" in message.successful_payment.invoice_payload else 30
    exp = "Навсегда" if days == 9999 else (datetime.now() + timedelta(days=days)).strftime("%d.%m.%Y")
    async with aiosqlite.connect('noryx_users.db') as db:
        await db.execute("UPDATE users SET role=?, expiry_date=? WHERE user_id=?", ("VIP" if days==9999 else "BETA", exp, message.from_user.id))
        await db.commit()
    await message.answer("🎉 Оплачено!")

async def main():
    await init_db()
    print("🚀 BOT IS RUNNING")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
    