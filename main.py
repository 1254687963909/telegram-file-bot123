import os
import logging
import sqlite3
import re
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- KONFIGURATSIYA ---
TOKEN = os.getenv("BOT_TOKEN")
raw_username = os.getenv("BOT_USERNAME", "")
BOT_USERNAME = raw_username.replace("@", "").strip()

admin_raw = str(os.getenv("ADMIN_ID", "6617367133")).strip()
ADMIN_ID = int(admin_raw)

CHANNEL_ID = "@Kimyo_imtihon_savollar"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- BAZA ---
conn = sqlite3.connect("bot_base.db")
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS violations 
                  (user_id INTEGER, chat_id INTEGER, count INTEGER, last_time TIMESTAMP, 
                  PRIMARY KEY (user_id, chat_id))''')
cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
cursor.execute('CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY)')
conn.commit()

class BroadcastStates(StatesGroup):
    waiting_for_message = State()

class AdFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        if not message.text and not message.caption:
            return False
        text = (message.text or message.caption).lower()
        patterns = [r'http[s]?://', r't\.me/', r'@[a-zA-Z0-9_]{5,}', r'www\.', r'\.uz', r'\.com', r'\.ru']
        return any(re.search(p, text) for p in patterns)

async def check_subscription(user_id: int):
    if user_id == ADMIN_ID: return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return False

def admin_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📣 Reklama yuborish")]
    ], resize_keyboard=True)

def add_to_group_inline():
    link = f"https://t.me/{BOT_USERNAME}?startgroup=admin&admin=delete_messages+restrict_members"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Guruhga qo'shish", url=link)]])

# --- ADMIN PANEL ---

@dp.message(F.text == "📊 Statistika", F.from_user.id == ADMIN_ID)
async def stats_handler(message: types.Message):
    cursor.execute("SELECT COUNT(*) FROM users")
    u = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chats")
    c = cursor.fetchone()[0]
    await message.answer(f"📊 Statistika:\n👤 Odamlar: {u}\n👥 Guruhlar: {c}")

@dp.message(F.text == "📣 Reklama yuborish", F.from_user.id == ADMIN_ID)
async def broadcast_request(message: types.Message, state: FSMContext):
    await message.answer("📣 Reklama yuboring. Bekor qilish: /cancel", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(BroadcastStates.waiting_for_message)

@dp.message(Command("cancel"), BroadcastStates.waiting_for_message)
async def broadcast_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Bekor qilindi.", reply_markup=admin_keyboard())

@dp.message(BroadcastStates.waiting_for_message, F.from_user.id == ADMIN_ID)
async def broadcast_execute(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🚀 Tarqatilmoqda...")
    cursor.execute("SELECT user_id FROM users")
    targets = [r[0] for r in cursor.fetchall()]
    cursor.execute("SELECT chat_id FROM chats")
    targets.extend([r[0] for r in cursor.fetchall()])
    
    ok = 0
    for t in set(targets):
        try:
            await message.copy_to(t)
            ok += 1
            await asyncio.sleep(0.05)
        except: continue
    await message.answer(f"✅ {ok} ta manzilga yuborildi.", reply_markup=admin_keyboard())

# --- FOYDALANUVCHILAR UCHUN ---

@dp.message(Command("start"), F.chat.type == "private")
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

    if user_id == ADMIN_ID:
        await message.answer("👋 Salom, Admin!", reply_markup=admin_keyboard())
        await message.answer("Guruhga qo'shish:", reply_markup=add_to_group_inline())
        return

    if await check_subscription(user_id):
        await message.answer("✅ Obuna tasdiqlangan:", reply_markup=add_to_group_inline())
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga a'zo bo'lish", url=f"https://t.me/{CHANNEL_ID[1:]}")],
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="check_sub")]
        ])
        await message.answer("⚠️ Botdan foydalanish uchun kanalga a'zo bo'ling:", reply_markup=kb)

@dp.callback_query(F.data == "check_sub")
async def check_callback(call: CallbackQuery):
    if await check_subscription(call.from_user.id):
        await call.message.delete()
        await call.message.answer("✅ Tayyor! Guruhga qo'shing:", reply_markup=add_to_group_inline())
    else:
        await call.answer("❌ Obuna bo'lmagansiz!", show_alert=True)

# --- GURUHDA ISHLASH (ASOSIY TOZALASH QISMI) ---

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def group_handler(message: types.Message):
    # Guruh ID-sini bazaga qo'shish
    cursor.execute("INSERT OR IGNORE INTO chats (chat_id) VALUES (?)", (message.chat.id,))
    conn.commit()

    # --- KANAL VA ANONIM ADMINLAR HIMOYA QISMI ---
    # 1. Agar xabar ulangan kanaldan kelayotgan bo'lsa (Linked Channel)
    if message.is_automatic_forward:
        return
    
    # 2. Agar xabar kanal nomidan yozilayotgan bo'lsa (Sender Chat)
    if message.sender_chat:
        return

    # 3. Agar foydalanuvchi ob'ekti bo'lmasa (kamdan-kam xolat, himoya uchun)
    if not message.from_user:
        return

    # --- REKLAMA TOZALASH QISMI ---
    if await AdFilter()(message):
        try:
            # Foydalanuvchi admin bo'lsa bot tegmaydi
            member = await message.chat.get_member(message.from_user.id)
            if member.status in ['administrator', 'creator']: return
            
            # Botning o'zi adminligini tekshirish
            bot_member = await message.chat.get_member(bot.id)
            if bot_member.status not in ["administrator", "creator"]: return
            if not bot_member.can_delete_messages or not bot_member.can_restrict_members: return
        except: return

        try:
            # 1. Reklamani o'chirish
            await message.delete()
            
            # 2. Jazo muddatini hisoblash
            user_id = message.from_user.id
            user_name = message.from_user.full_name
            chat_id = message.chat.id
            
            cursor.execute("SELECT count, last_time FROM violations WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
            row = cursor.fetchone()
            mute_min, count = 10, 1
            
            if row:
                last_time = datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S.%f')
                if datetime.now() - last_time < timedelta(weeks=1):
                    count = row[0] + 1
                    mute_min = count * 10
            
            # 3. Mute qilish (Sukut rejimi)
            await bot.restrict_chat_member(
                chat_id, user_id, 
                ChatPermissions(can_send_messages=False),
                until_date=datetime.now() + timedelta(minutes=mute_min)
            )
            
            # 4. Guruhda xabar berish
            warn_msg = await message.answer(
                f"🚫 {user_name}, siz guruh qoidalarini buzganingiz uchun "
                f"**{mute_min} daqiqa** sukut rejimiga o'tkazildingiz!",
                parse_mode="Markdown"
            )
            
            # 5. Bazani yangilash
            cursor.execute("INSERT OR REPLACE INTO violations VALUES (?, ?, ?, ?)", 
                           (user_id, chat_id, count, datetime.now()))
            conn.commit()

            # 6. Ogohlantirishni 1 daqiqadan keyin o'chirish
            await asyncio.sleep(120)
            try: await warn_msg.delete()
            except: pass

        except Exception as e:
            logging.error(f"Xato: {e}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("Stop")
