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

# --- KONFIGURATSIYA ---
TOKEN = os.getenv("BOT_TOKEN")  
BOT_USERNAME = os.getenv("BOT_USERNAME")
ADMIN_ID = int(os.getenv("ADMIN_ID", 5892540785)) # Default qiymat sifatida sizning ID-ingiz
CHANNEL_ID = "@Kimyo_imtihon_savollar"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- BAZA BILAN ISHLASH ---
conn = sqlite3.connect("bot_base.db")
cursor = conn.cursor()

# Jadvallarni yaratish
cursor.execute('CREATE TABLE IF NOT EXISTS violations (user_id INTEGER, chat_id INTEGER, count INTEGER, last_time TIMESTAMP, PRIMARY KEY (user_id, chat_id))')
cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)') # Botga start bosganlar
cursor.execute('CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY)') # Guruhlar ro'yxati
conn.commit()

# Reklama holati uchun klass
class BroadcastStates(StatesGroup):
    waiting_for_message = State()

# --- FILTRLAR ---
class AdFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        if not message.text and not message.caption:
            return False
        text = (message.text or message.caption).lower()
        patterns = [r'http[s]?://', r't\.me/', r'@[a-zA-Z0-9_]{5,}', r'www\.', r'\.uz', r'\.com', r'\.ru']
        return any(re.search(p, text) for p in patterns)

# --- FUNKSIYALAR ---
async def check_subscription(user_id: int):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# --- ADMIN BUYRUQLARI ---

# Statistika
@dp.message(Command("stats"), F.from_user.id == ADMIN_ID)
async def show_stats(message: types.Message):
    cursor.execute("SELECT COUNT(*) FROM users")
    u_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chats")
    c_count = cursor.fetchone()[0]
    
    await message.answer(f"📊 **Bot statistikasi:**\n\n👤 Foydalanuvchilar: {u_count}\n👥 Guruhlar: {c_count}")

# Reklama yuborishni boshlash
@dp.message(Command("reklama"), F.from_user.id == ADMIN_ID)
async def start_broadcast(message: types.Message, state: FSMContext):
    await message.answer("Reklama xabarini yuboring (Text, rasm yoki video).\nBekor qilish uchun /cancel deb yozing.")
    await state.set_state(BroadcastStates.waiting_for_message)

# Bekor qilish
@dp.message(Command("cancel"), BroadcastStates.waiting_for_message)
async def cancel_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Reklama yuborish bekor qilindi.")

# Reklamani tarqatish
@dp.message(BroadcastStates.waiting_for_message)
async def process_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🚀 Reklama tarqatish boshlandi...")

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    cursor.execute("SELECT chat_id FROM chats")
    chats = cursor.fetchall()

    count = 0
    # Foydalanuvchilarga yuborish
    for user in users:
        try:
            await message.copy_to(chat_id=user[0])
            count += 1
            await asyncio.sleep(0.05) # Telegram limitidan oshib ketmaslik uchun
        except:
            continue

    # Guruhlarga yuborish
    for chat in chats:
        try:
            await message.copy_to(chat_id=chat[0])
            count += 1
            await asyncio.sleep(0.05)
        except:
            continue

    await message.answer(f"✅ Reklama yakunlandi. {count} ta manzilga yetkazildi.")

# --- FOYDALANUVCHI BUYRUQLARI ---

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
            "Men guruhlarni reklamadan tozalovchi botman.\n"
            "Meni guruhga qo'shing va admin qiling!"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Guruhga qo'shish", url=link)]])
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        text = "⚠️ **Botdan foydalanish uchun kanalimizga a'zo bo'lishingiz kerak!**"
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
        await call.message.answer("✅ Rahmat! Guruhga qo'shish tugmasini bosing:", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Guruhga qo'shish", url=link)]]))
    else:
        await call.answer("❌ Siz hali ham kanalga a'zo bo'lmadingiz!", show_alert=True)

# --- GURUHDA REKLAMA TOZALASH ---

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def cleaner_handler(message: types.Message):
    # Guruhni bazaga qo'shish (Agarda hali bo'lmasa)
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

        bot_member = await message.chat.get_member(bot.id)
        if not bot_member.can_delete_messages or not bot_member.can_restrict_members:
            return 

        user_id = message.from_user.id
        chat_id = message.chat.id
        now = datetime.now()

        try:
            await message.delete()
        except:
            pass

        # Jazo tizimi
        cursor.execute("SELECT count, last_time FROM violations WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        row = cursor.fetchone()

        mute_minutes = 10
        new_count = 1

        if row:
            count, last_time_str = row
            last_time = datetime.strptime(last_time_str, '%Y-%m-%d %H:%M:%S.%f')
            if now - last_time < timedelta(weeks=1):
                new_count = count + 1
                mute_minutes = new_count * 10
        
        try:
            until_date = now + timedelta(minutes=mute_minutes)
            await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False), until_date=until_date)
        except:
            pass

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


