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
# Username-dagi @ belgisini avtomatik olib tashlaymiz
raw_username = os.getenv("BOT_USERNAME", "")
BOT_USERNAME = raw_username.replace("@", "") 

# Admin ID ni Railway dan olamiz, agar bo'lmasa 6617367133 ni qo'yadi
admin_raw = os.getenv("ADMIN_ID", "6617367133")
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
    # Admin bo'lsa tekshirib o'tirmaydi
    if user_id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# --- ADMIN KEYBOARD ---
def admin_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📣 Reklama yuborish")]
    ], resize_keyboard=True)

# --- START BUYRUG'I ---
@dp.message(Command("start"), F.chat.type == "private")
async def start_cmd(message: types.Message):
    # Bazaga foydalanuvchini qo'shish
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    conn.commit()

    # ADMIN TEKSHIRUVI (Birinchi navbatda)
    if message.from_user.id == ADMIN_ID:
        await message.answer(f"👋 Salom, Admin ({ADMIN_ID})! Kerakli bo'limni tanlang:", reply_markup=admin_keyboard())
        return

    # ODDIY FOYDALANUVCHI
    is_subscribed = await check_subscription(message.from_user.id)
    if is_subscribed:
        link = f"https://t.me/{BOT_USERNAME}?startgroup=true"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Guruhga qo'shish", url=link)]])
        await message.answer("✅ Obuna tasdiqlandi. Meni guruhga qo'shib admin qilsangiz, reklamalarni tozalayman.", reply_markup=kb)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga a'zo bo'lish", url=f"https://t.me/{CHANNEL_ID[1:]}")],
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="check_sub")]
        ])
        await message.answer("⚠️ Botdan foydalanish uchun kanalga a'zo bo'ling:", reply_markup=kb)

# --- ADMIN FUNKSIYALARI ---
@dp.message(F.text == "📊 Statistika", F.from_user.id == ADMIN_ID)
async def stats(message: types.Message):
    cursor.execute("SELECT COUNT(*) FROM users")
    u = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chats")
    c = cursor.fetchone()[0]
    await message.answer(f"📊 **Statistika:**\n\n👤 Foydalanuvchilar: {u}\n👥 Guruhlar: {c}", parse_mode="Markdown")

@dp.message(F.text == "📣 Reklama yuborish", F.from_user.id == ADMIN_ID)
async def broadcast_start(message: types.Message, state: FSMContext):
    await message.answer("📣 Reklama xabarini yuboring (Text, rasm, video).\nBekor qilish uchun /cancel", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(BroadcastStates.waiting_for_message)

@dp.message(Command("cancel"), BroadcastStates.waiting_for_message)
async def cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Bekor qilindi.", reply_markup=admin_keyboard())

@dp.message(BroadcastStates.waiting_for_message, F.from_user.id == ADMIN_ID)
async def broadcast_send(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🚀 Tarqatilmoqda...")
    
    cursor.execute("SELECT user_id FROM users")
    us = [r[0] for r in cursor.fetchall()]
    cursor.execute("SELECT chat_id FROM chats")
    ch = [r[0] for r in cursor.fetchall()]
    
    all_targets = list(set(us + ch))
    ok = 0
    for t in all_targets:
        try:
            await message.copy_to(t)
            ok += 1
            await asyncio.sleep(0.05)
        except:
            continue
    await message.answer(f"✅ Yakunlandi: {ok} ta manzilga yuborildi.", reply_markup=admin_keyboard())

# --- CALLBACK ---
@dp.callback_query(F.data == "check_sub")
async def check_cb(call: CallbackQuery):
    if await check_subscription(call.from_user.id):
        await call.message.delete()
        link = f"https://t.me/{BOT_USERNAME}?startgroup=true"
        await call.message.answer("✅ Rahmat! Guruhga qo'shish tugmasini bosing:", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Guruhga qo'shish", url=link)]]))
    else:
        await call.answer("❌ Obuna bo'lmagansiz!", show_alert=True)

# --- GURUHDA ISHLASH ---
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def cleaner(message: types.Message):
    # Guruhni bazaga olish (reklama yuborish uchun kerak)
    cursor.execute("INSERT OR IGNORE INTO chats (chat_id) VALUES (?)", (message.chat.id,))
    conn.commit()

    if await AdFilter()(message):
        try:
            m = await message.chat.get_member(message.from_user.id)
            if m.status in ['administrator', 'creator']: return
        except: return

        try: await message.delete()
        except: return

        # Jazo
        cursor.execute("SELECT count, last_time FROM violations WHERE user_id = ? AND chat_id = ?", (message.from_user.id, message.chat.id))
        row = cursor.fetchone()
        mute = 10
        count = 1
        if row:
            last = datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S.%f')
            if datetime.now() - last < timedelta(weeks=1):
                count = row[0] + 1
                mute = count * 10
        
        try:
            await bot.restrict_chat_member(message.chat.id, message.from_user.id, ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(minutes=mute))
        except: pass

        cursor.execute("INSERT OR REPLACE INTO violations VALUES (?, ?, ?, ?)", (message.from_user.id, message.chat.id, count, datetime.now()))
        conn.commit()

async def main():
    print(f"Bot @{BOT_USERNAME} admin {ADMIN_ID} bilan ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("Stop")
