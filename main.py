import os
import logging
import sqlite3
import re
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- KONFIGURATSIYA (Railway Variables orqali) ---
TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
# ADMIN_ID ni Railway dan olamiz, agar bo'lmasa siz yuborgan ID ni ishlatadi
admin_id_env = os.getenv("ADMIN_ID", "7699033921")
ADMIN_ID = int(admin_id_env)
CHANNEL_ID = "@Kimyo_imtihon_savollar"

# Loglarni sozlash
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- BAZA BILAN ISHLASH ---
conn = sqlite3.connect("bot_base.db")
cursor = conn.cursor()

# Jadvallarni yaratish
cursor.execute('''CREATE TABLE IF NOT EXISTS violations 
                  (user_id INTEGER, chat_id INTEGER, count INTEGER, last_time TIMESTAMP, 
                  PRIMARY KEY (user_id, chat_id))''')
cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
cursor.execute('CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY)')
conn.commit()

# Reklama holati (FSM)
class BroadcastStates(StatesGroup):
    waiting_for_message = State()

# --- FILTR: REKLAMA VA LINKLAR ---
class AdFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        if not message.text and not message.caption:
            return False
        text = (message.text or message.caption).lower()
        patterns = [r'http[s]?://', r't\.me/', r'@[a-zA-Z0-9_]{5,}', r'www\.', r'\.uz', r'\.com', r'\.ru']
        return any(re.search(p, text) for p in patterns)

# --- OBUNANI TEKSHIRISH ---
async def check_subscription(user_id: int):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# --- ADMIN PANEL: STATISTIKA VA REKLAMA ---

@dp.message(Command("stats"), F.from_user.id == ADMIN_ID)
async def show_stats(message: types.Message):
    cursor.execute("SELECT COUNT(*) FROM users")
    u_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chats")
    c_count = cursor.fetchone()[0]
    await message.answer(f"📊 **Bot statistikasi:**\n\n👤 Foydalanuvchilar: {u_count}\n👥 Guruhlar: {c_count}", parse_mode="Markdown")

@dp.message(Command("reklama"), F.from_user.id == ADMIN_ID)
async def start_broadcast(message: types.Message, state: FSMContext):
    await message.answer("📣 Reklama xabarini yuboring (matn, rasm yoki video).\nBekor qilish uchun /cancel buyrug'ini bosing.")
    await state.set_state(BroadcastStates.waiting_for_message)

@dp.message(Command("cancel"), BroadcastStates.waiting_for_message)
async def cancel_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Reklama yuborish bekor qilindi.")

@dp.message(BroadcastStates.waiting_for_message, F.from_user.id == ADMIN_ID)
async def process_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🚀 Reklama tarqatilmoqda, kuting...")

    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    cursor.execute("SELECT chat_id FROM chats")
    chats = [row[0] for row in cursor.fetchall()]

    all_targets = list(set(users + chats))
    success = 0
    failed = 0

    for target in all_targets:
        try:
            await message.copy_to(chat_id=target)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    
    await message.answer(f"✅ **Reklama yakunlandi!**\n\n🎯 Yetkazildi: {success}\n🚫 Yetkazilmadi: {failed}", parse_mode="Markdown")

# --- FOYDALANUVCHILAR UCHUN START ---

@dp.message(Command("start"), F.chat.type == "private")
async def start_cmd(message: types.Message):
    # Foydalanuvchini bazaga qo'shish
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    conn.commit()

    is_subscribed = await check_subscription(message.from_user.id)
    if is_subscribed:
        link = f"https://t.me/{BOT_USERNAME}?startgroup=true"
        text = (
            "✅ **Siz kanalimizga a'zo bo'lgansiz!**\n\n"
            "Meni guruhga qo'shib admin qilsangiz, guruhni reklamalardan tozalayman."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Guruhga qo'shish", url=link)]])
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        text = (
            "⚠️ **Botdan foydalanish uchun kanalimizga a'zo bo'lishingiz kerak!**\n\n"
            "Kanalga kiring va 'Tasdiqlash' tugmasini bosing."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga a'zo bo'lish", url=f"https://t.me/{CHANNEL_ID[1:]}")],
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="check_sub")]
        ])
        await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "check_sub")
async def check_callback(call: CallbackQuery):
    if await check_subscription(call.from_user.id):
        await call.message.delete()
        link = f"https://t.me/{BOT_USERNAME}?startgroup=true"
        await call.message.answer("✅ Rahmat! Endi meni guruhga qo'shishingiz mumkin:", 
                                  reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Guruhga qo'shish", url=link)]]))
    else:
        await call.answer("❌ Kanalga hali a'zo emassiz!", show_alert=True)

# --- GURUHDA REKLAMA TOZALASH ---

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def cleaner_handler(message: types.Message):
    # Guruhni bazaga qo'shish (reklama yuborish uchun)
    cursor.execute("INSERT OR IGNORE INTO chats (chat_id) VALUES (?)", (message.chat.id,))
    conn.commit()

    # Agar xabar reklama bo'lsa
    if await AdFilter()(message):
        try:
            member = await message.chat.get_member(message.from_user.id)
            if member.status in ['administrator', 'creator']:
                return
        except:
            return

        bot_member = await message.chat.get_member(bot.id)
        if not bot_member.can_delete_messages or not bot_member.can_restrict_members:
            return 

        user_id = message.from_user.id
        chat_id = message.chat.id
        now = datetime.now()

        # 1. Reklamani o'chirish (iz qoldirmaydi)
        try:
            await message.delete()
        except:
            pass

        # 2. Jazo muddatini hisoblash
        cursor.execute("SELECT count, last_time FROM violations WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        row = cursor.fetchone()

        mute_minutes = 10
        new_count = 1

        if row:
            count, last_time_str = row
            last_time = datetime.strptime(last_time_str, '%Y-%m-%d %H:%M:%S.%f')
            # 1 hafta ichida bo'lsa jazoni ko'paytirish
            if now - last_time < timedelta(weeks=1):
                new_count = count + 1
                mute_minutes = new_count * 10
        
        # 3. Mute qilish
        try:
            until_date = now + timedelta(minutes=mute_minutes)
            await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False), until_date=until_date)
        except:
            pass

        # 4. Bazani yangilash
        cursor.execute("INSERT OR REPLACE INTO violations (user_id, chat_id, count, last_time) VALUES (?, ?, ?, ?)", 
                       (user_id, chat_id, new_count, now))
        conn.commit()

# --- ISHGA TUSHIRISH ---
async def main():
    print(f"@{BOT_USERNAME} admin {ADMIN_ID} bilan ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot to'xtatildi!")

