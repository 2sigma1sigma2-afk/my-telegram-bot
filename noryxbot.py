import asyncio
import logging
import math
import random
import string
import aiosqlite
import sys
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ================= ⚙️ НАСТРОЙКИ ⚙️ =================
BOT_TOKEN = '7716127075:AAEs55gkC1Dk6NcC9tAdkW-6oM-5bRcag-w'
OWNER_USERNAME = 'illusiononce'

# Путь к БД: /app/data/ для Railway (нужен Volume), иначе локально
DB_PATH = '/app/data/noryx_users.db' if os.path.exists('/app/data') else 'noryx_users.db'

PRICES = {'7': 35, '30': 120, 'life': 175} # Цены в Telegram Stars
ALLOWED_PREFIXES = ["ЧСВ", "Красавчик", "Буст", "Ez"]
LINE = "━━━━━━━━━━━━━━━━━━━━"

# ==================================================

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class AuthStates(StatesGroup):
    reg_username = State()
    reg_password = State()
    login_username = State()
    login_password = State()

class BotStates(StatesGroup):
    waiting_for_promo = State()
    waiting_for_key = State()
    waiting_for_activations = State()
    gen_days = State()

# --- 🛠 БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            uid INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            prefix TEXT DEFAULT '',
            role TEXT DEFAULT 'FREE',
            expiry_date TEXT DEFAULT 'Нет',
            discount REAL DEFAULT 0.0,
            app_username TEXT UNIQUE,
            app_password TEXT
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS generated_keys (
            key_code TEXT PRIMARY KEY,
            days INTEGER,
            role TEXT DEFAULT 'BETA',
            activations_left INTEGER DEFAULT 1
        )''')
        await db.commit()

async def get_user_by_tg(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

# --- ⌨️ КЛАВИАТУРЫ ---
def get_auth_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Войти", callback_data="auth_login"),
         InlineKeyboardButton(text="📝 Регистрация", callback_data="auth_reg")]
    ])

def get_main_kb(role: str, tg_username: str):
    kb = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🎭 Префиксы", callback_data="prefix_menu")],
        [InlineKeyboardButton(text="🔑 Ключ", callback_data="activate_key"),
         InlineKeyboardButton(text="🛒 Магазин", callback_data="buy_beta")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo")]
    ]
    if role in ['BETA', 'VIP']:
        kb.insert(2, [InlineKeyboardButton(text="📁 СКАЧАТЬ BETA", callback_data="download_beta")])
    
    # Проверка админа
    if tg_username and tg_username.lower() == OWNER_USERNAME.lower():
        kb.append([InlineKeyboardButton(text="⚡ АДМИНКА ⚡", callback_data="admin_main")])
    
    kb.append([InlineKeyboardButton(text="🚪 Выйти из аккаунта", callback_data="logout")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]])

# --- 🔐 ВХОД / РЕГИСТРАЦИЯ / ВЫХОД ---

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user_by_tg(message.from_user.id)
    if not user:
        await message.answer("👋 Добро пожаловать!\nДля доступа к системе авторизуйтесь:", reply_markup=get_auth_kb())
    else:
        await message.answer(f"🌟 **NORYX — МЕНЮ**\n{LINE}\nВы вошли как: `{user[8]}`", parse_mode="Markdown", reply_markup=get_main_kb(user[5], message.from_user.username))

@dp.callback_query(F.data == "logout")
async def process_logout(callback: CallbackQuery, state: FSMContext):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET user_id = NULL WHERE user_id = ?", (callback.from_user.id,))
        await db.commit()
    await state.clear()
    await callback.message.edit_text("🚪 Вы успешно вышли из аккаунта.\nВойдите снова или зарегистрируйтесь:", reply_markup=get_auth_kb())

# Логика регистрации
@dp.callback_query(F.data == "auth_reg")
async def reg_1(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AuthStates.reg_username)
    await callback.message.edit_text("📝 Введите логин для нового аккаунта:")

@dp.message(AuthStates.reg_username)
async def reg_2(message: Message, state: FSMContext):
    name = message.text.strip()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT uid FROM users WHERE app_username = ?", (name,)) as cur:
            if await cur.fetchone():
                await message.answer("❌ Этот логин занят! Введите другой:")
                return
    await state.update_data(reg_username=name)
    await state.set_state(AuthStates.reg_password)
    await message.answer("🔒 Придумайте пароль:")

@dp.message(AuthStates.reg_password)
async def reg_3(message: Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO users (user_id, first_name, username, app_username, app_password) VALUES (?, ?, ?, ?, ?)",
                         (message.from_user.id, message.from_user.first_name, message.from_user.username, data['reg_username'], message.text.strip()))
        await db.commit()
    await state.clear()
    await message.answer("✅ Аккаунт создан! Теперь вы в системе.", reply_markup=get_main_kb("FREE", message.from_user.username))

# Логика входа
@dp.callback_query(F.data == "auth_login")
async def login_1(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AuthStates.login_username)
    await callback.message.edit_text("🔑 Введите ваш логин:")

@dp.message(AuthStates.login_username)
async def login_2(message: Message, state: FSMContext):
    await state.update_data(login_username=message.text.strip())
    await state.set_state(AuthStates.login_password)
    await message.answer("🔒 Введите пароль:")

@dp.message(AuthStates.login_password)
async def login_3(message: Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE app_username = ? AND app_password = ?", (data['login_username'], message.text.strip())) as cur:
            user = await cur.fetchone()
        if user:
            # Перепривязываем ТГ
            await db.execute("UPDATE users SET user_id = NULL WHERE user_id = ?", (message.from_user.id,))
            await db.execute("UPDATE users SET user_id = ? WHERE uid = ?", (message.from_user.id, user[0]))
            await db.commit()
            await state.clear()
            await message.answer(f"✅ Вход выполнен! Добро пожаловать, {data['login_username']}", reply_markup=get_main_kb(user[5], message.from_user.username))
        else:
            await message.answer("❌ Неверный логин или пароль!", reply_markup=get_auth_kb())

# --- 👤 ПРОФИЛЬ И ПРЕФИКСЫ ---

@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    u = await get_user_by_tg(callback.from_user.id)
    if not u: return
    text = (f"👤 **ПРОФИЛЬ**\n{LINE}\n🔑 Логин: `{u[8]}`\n🆔 UID: `{u[0]}`\n👑 Роль: `{u[5]}`\n⏳ Срок: `{u[6]}`\n🎭 Префикс: `{u[4] if u[4] else 'Нет'}`\n{LINE}")
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_back_kb())

@dp.callback_query(F.data == "prefix_menu")
async def prefix_menu(callback: CallbackQuery):
    kb = [[InlineKeyboardButton(text=f"💠 {p}", callback_data=f"setp_{p}")] for p in ALLOWED_PREFIXES]
    kb.append([InlineKeyboardButton(text="🗑 Сбросить", callback_data="setp_clear")])
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    await callback.message.edit_text("🎭 **ВЫБОР ПРЕФИКСА:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("setp_"))
async def set_prefix(callback: CallbackQuery):
    p = "" if "clear" in callback.data else callback.data.split("_")[1]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET prefix = ? WHERE user_id = ?", (p, callback.from_user.id))
        await db.commit()
    await callback.answer(f"✅ Готово!")
    await prefix_menu(callback)

# --- 🛒 МАГАЗИН ---

@dp.callback_query(F.data == "buy_beta")
async def shop_menu(callback: CallbackQuery):
    u = await get_user_by_tg(callback.from_user.id)
    def calc(p): return math.ceil(p * (1 - u[7]))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"7 дней — {calc(PRICES['7'])} ⭐", callback_data="pay_7")],
        [InlineKeyboardButton(text=f"30 дней — {calc(PRICES['30'])} ⭐", callback_data="pay_30")],
        [InlineKeyboardButton(text=f"Навсегда — {calc(PRICES['life'])} ⭐", callback_data="pay_life")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text("🛒 **МАГАЗИН ПОДПИСОК:**", reply_markup=kb)

@dp.callback_query(F.data.startswith("pay_"))
async def create_invoice(callback: CallbackQuery):
    plan = callback.data.split("_")[1]
    u = await get_user_by_tg(callback.from_user.id)
    cost = PRICES['7'] if plan=='7' else (PRICES['30'] if plan=='30' else PRICES['life'])
    final_cost = math.ceil(cost * (1 - u[7]))
    
    await bot.send_invoice(
        callback.from_user.id, title=f"Noryx Beta ({plan} d)",
        description=f"Активация доступа к читу на срок: {plan}",
        payload=f"sub_{plan}", provider_token="", currency="XTR",
        prices=[LabeledPrice(label="XTR", amount=final_cost)]
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.message(F.successful_payment)
async def payment_success(message: Message):
    plan = message.successful_payment.invoice_payload.split("_")[1]
    days = 9999 if plan == "life" else int(plan)
    exp = "Навсегда" if days == 9999 else (datetime.now() + timedelta(days=days)).strftime("%d.%m.%Y")
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET role=?, expiry_date=? WHERE user_id=?", 
                         ("VIP" if days == 9999 else "BETA", exp, message.from_user.id))
        await db.commit()
    await message.answer(f"🎉 Оплата успешно! Роль обновлена до {exp}")

# --- 🛡 АДМИНКА ---

@dp.callback_query(F.data == "admin_main")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.username.lower() != OWNER_USERNAME.lower(): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Все пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="🔑 Создать ключ", callback_data="admin_gen_key")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text("🛡 **АДМИН-ПАНЕЛЬ**", reply_markup=kb)

@dp.callback_query(F.data == "admin_users")
async def admin_list_users(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT uid, app_username, role FROM users LIMIT 10") as cur:
            users = await cur.fetchall()
    res = "👥 **АККАУНТЫ:**\n" + "\n".join([f"UID: {u[0]} | Логин: {u[1]} | {u[2]}" for u in users])
    await callback.message.edit_text(res, reply_markup=get_back_kb())

@dp.callback_query(F.data == "admin_gen_key")
async def admin_gen_step1(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="7 дней", callback_data="g_7"), InlineKeyboardButton(text="30 дней", callback_data="g_30")],
        [InlineKeyboardButton(text="Навсегда", callback_data="g_9999")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_main")]
    ])
    await callback.message.edit_text("На какой срок ключ?", reply_markup=kb)

@dp.callback_query(F.data.startswith("g_"))
async def admin_gen_step2(callback: CallbackQuery, state: FSMContext):
    await state.update_data(gen_days=int(callback.data.split("_")[1]))
    await state.set_state(BotStates.waiting_for_activations)
    await callback.message.edit_text("Количество активаций:")

@dp.message(BotStates.waiting_for_activations)
async def admin_gen_step3(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    data = await state.get_data()
    key = f"NORYX-{''.join(random.choices(string.ascii_uppercase + string.digits, k=10))}"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO generated_keys VALUES (?, ?, ?, ?)", 
                         (key, data['gen_days'], 'BETA' if data['gen_days']<9999 else 'VIP', int(message.text)))
        await db.commit()
    await state.clear()
    await message.answer(f"✅ Ключ создан: `{key}`", parse_mode="Markdown", reply_markup=get_back_kb())

# --- 🔑 КЛЮЧИ И ПРОМО ---

@dp.callback_query(F.data == "activate_key")
async def key_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_key)
    await callback.message.edit_text("🔑 Введите лицензионный ключ:", reply_markup=get_back_kb())

@dp.message(BotStates.waiting_for_key)
async def key_proc(message: Message, state: FSMContext):
    k = message.text.strip()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT days, role, activations_left FROM generated_keys WHERE key_code=?", (k,)) as cur:
            res = await cur.fetchone()
        if res:
            days, role, left = res
            exp = "Навсегда" if days == 9999 else (datetime.now() + timedelta(days=days)).strftime("%d.%m.%Y")
            await db.execute("UPDATE users SET role=?, expiry_date=? WHERE user_id=?", (role, exp, message.from_user.id))
            if left > 1: await db.execute("UPDATE generated_keys SET activations_left=left-1 WHERE key_code=?", (k,))
            else: await db.execute("DELETE FROM generated_keys WHERE key_code=?", (k,))
            await db.commit()
            await state.clear()
            await message.answer(f"✅ Успешно! Роль {role} активирована.", reply_markup=get_main_kb(role, message.from_user.username))
        else: await message.answer("❌ Ключ не найден!")

@dp.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    u = await get_user_by_tg(callback.from_user.id)
    if not u:
        await callback.message.edit_text("Авторизуйтесь:", reply_markup=get_auth_kb())
    else:
        await callback.message.edit_text(f"🌟 **NORYX — МЕНЮ**\n{LINE}", reply_markup=get_main_kb(u[5], callback.from_user.username))

# --- 🚀 СТАРТ ---
async def main():
    await init_db()
    print(f"🚀 Бот в сети! БД: {DB_PATH}")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
    
