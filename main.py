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

# Admin ID ni Railway dan olamiz, agar xato bo'lsa stripping qilamiz
admin_raw = str(os.getenv("ADMIN_ID", "6617367133")).strip()
ADMIN_ID = int(admin_raw)

CHANNEL_ID = "@Kimyo_imtihon_savollar"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- BAZA ---
conn = sqlite3.connect("bot_base.db")
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS violations (user_id INTEGER, chat_id INTEGER, count INTEGER, last_time TIMESTAMP, PRIMARY KEY (user_id, chat_id))')
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
    if user_id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# --- KEYBOARDS ---
def admin_keyboard():
    kb = [
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📣 Reklama yuborish")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- BUYRUQLAR ---

@dp.message(Command("myid"))
async def get_my_id(message: types.Message):
    await message.answer(f"Sizning ID: `{message.from_user.id}`\nAdmin ID: `{ADMIN_ID}`", parse_mode="Markdown")

@dp.message(Command("start"), F.chat.type == "private")
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    # Bazaga qo'shish
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

    # ADMIN TEKSHIRUVI
    if user_id == ADMIN_ID:
        await message.answer("👋 Salom, Admin! Kerakli bo'limni tanlang:", reply_markup=admin_keyboard())
        return

    # FOYDALANUVCHI TEKSHIRUVI
    if await check_subscription(user_id):
        link = f"https://t.me/{BOT_USERNAME}?startgroup=true"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Guruhga qo'shish", url=link)]])
        await message.answer("✅ Obuna tasdiqlangan. Meni guruhga qo'shib admin qiling:", reply_markup=kb)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga a'zo bo'lish", url=f"https://t.me/{CHANNEL_ID[1:]}")],
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="check_sub")]
        ])
        await message.answer("⚠️ Botdan foydalanish uchun kanalga a'zo bo'ling:", reply_markup=kb)

# --- ADMIN PANEL LOGIKASI ---

@dp.message(F.text == "📊 Statistika", F.from_user.id == ADMIN_ID)
async def stats_handler(message: types.Message):
    cursor.execute("SELECT COUNT(*) FROM users")
    u = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chats")
    c = cursor.fetchone()[0]
    await message.answer(f"📊 **Bot statistikasi:**\n\n👤 Foydalanuvchilar: {u}\n👥 Guruhlar: {c}", parse_mode="Markdown")

@dp.message(F.text == "📣 Reklama yuborish", F.from_user.id == ADMIN_ID)
async def broadcast_request(message: types.Message, state: FSMContext):
    await message.answer("📣 Reklama xabarini yuboring (rasm, video yoki matn).\nBekor qilish uchun: /cancel", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(BroadcastStates.waiting_for_message)

@dp.message(Command("cancel"), BroadcastStates.waiting_for_message)
async def broadcast_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Bekor qilindi.", reply_markup=admin_keyboard())

@dp.message(BroadcastStates.waiting_for_message, F.from_user.id == ADMIN_ID)
async def broadcast_execute(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🚀 Reklama tarqatilmoqda...")
    
    cursor.execute("SELECT user_id FROM users")
    users = [r[0] for r in cursor.fetchall()]
    cursor.execute("SELECT chat_id FROM chats")
    chats = [r[0] for r in cursor.fetchall()]
    
    all_targets = list(set(users + chats))
    count = 0
    for target in all_targets:
        try:
            await message.copy_to(chat_id=target)
            count += 1
            await asyncio.sleep(0.05)
        except:
            continue
    await message.answer(f"✅ Yakunlandi! {count} ta manzilga yetkazildi.", reply_markup=admin_keyboard())

# --- QOLGAN FUNKSIYALAR ---

@dp.callback_query(F.data == "check_sub")
async def check_callback(call: CallbackQuery):
    if await check_subscription(call.from_user.id):
        await call.message.delete()
        link = f"https://t.me/{BOT_USERNAME}?startgroup=true"
        await call.message.answer("✅ Rahmat! Meni guruhga qo'shishingiz mumkin:", 
                                  reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Guruhga qo'shish", url=link)]]))
    else:
        await call.answer("❌ Siz hali kanalga a'zo emassiz!", show_alert=True)

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def group_handler(message: types.Message):
    # Guruhni bazaga qo'shish
    cursor.execute("INSERT OR IGNORE INTO chats (chat_id) VALUES (?)", (message.chat.id,))
    conn.commit()

    # Reklama filtri
    if await AdFilter()(message):
        try:
            member = await message.chat.get_member(message.from_user.id)
            if member.status in ['administrator', 'creator']:
                return
        except:
            return

        # Bot adminligini tekshirish
        bot_member = await message.chat.get_member(bot.id)
        if not bot_member.can_delete_messages or not bot_member.can_restrict_members:
            return

        try:
            await message.delete()
            
            # Jazo hisoblash
            cursor.execute("SELECT count, last_time FROM violations WHERE user_id = ? AND chat_id = ?", (message.from_user.id, message.chat.id))
            row = cursor.fetchone()
            mute_min, count = 20, 1
            
            if row:
                last_time = datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S.%f')
                if datetime.now() - last_time < timedelta(weeks=1):
                    count = row[0] + 1
                    mute_min = count * 10
            
            await bot.restrict_chat_member(
                message.chat.id, 
                message.from_user.id, 
                ChatPermissions(can_send_messages=False),
                until_date=datetime.now() + timedelta(minutes=mute_min)
            )
            
            cursor.execute("INSERT OR REPLACE INTO violations VALUES (?, ?, ?, ?)", 
                           (message.from_user.id, message.chat.id, count, datetime.now()))
            conn.commit()
        except:
            pass

async def main():
    print(f"Bot @{BOT_USERNAME} ishga tushdi. Admin ID: {ADMIN_ID}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot to'xtatildi")


