import logging
import sqlite3
import re
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command, BaseFilter

TOKEN = "8335628903:AAGsyseEKhZt0pALcaM1AgJRQSkLLP3U7JE"  
BOT_USERNAME = "BOT_USERNAME" 
CHANNEL_ID = "@Kimyo_imtihon_savollar"  

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()


conn = sqlite3.connect("bot_base.db")
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS violations (
        user_id INTEGER, chat_id INTEGER, count INTEGER, last_time TIMESTAMP,
        PRIMARY KEY (user_id, chat_id)
    )
''')
conn.commit()

class AdFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        if not message.text and not message.caption:
            return False
        text = (message.text or message.caption).lower()
        patterns = [r'http[s]?://', r't\.me/', r'@[a-zA-Z0-9_]{5,}', r'www\.', r'\.uz', r'\.com', r'\.ru']
        return any(re.search(p, text) for p in patterns)


async def check_subscription(user_id: int):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False


@dp.message(Command("start"), F.chat.type == "private")
async def start_cmd(message: types.Message):
    is_subscribed = await check_subscription(message.from_user.id)
    
    if is_subscribed:

        link = f"https://t.me/{BOT_USERNAME}?startgroup=true"
        text = (
            "✅ **Siz kanalimizga a'zo bo'lgansiz!**\n\n"
            "Men guruhlarni reklamadan tozalovchi botman.\n"
            "1. Link va reklamalarni darhol o'chiraman.\n"
            "2. Reklama tarqatuvchini 10 daqiqaga mute qilaman.\n"
            "3. O'zimdan keyin hech qanday xabar qoldirmayman.\n\n"
            "Botni guruhga qo'shib admin qiling!"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Guruhga qo'shish", url=link)]
        ])
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:

        text = (
            "⚠️ **Botdan foydalanish uchun kanalimizga a'zo bo'lishingiz kerak!**\n\n"
            "Pastdagi tugma orqali kanalga kiring va 'Tasdiqlash' tugmasini bosing."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga a'zo bo'lish", url=f"https://t.me/{CHANNEL_ID[1:]}")],
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="check_sub")]
        ])
        await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data == "check_sub")
async def check_callback(call: CallbackQuery):
    is_subscribed = await check_subscription(call.from_user.id)
    
    if is_subscribed:
        await call.message.delete()
        link = f"https://t.me/{BOT_USERNAME}?startgroup=true"
        await call.message.answer(
            "✅ Rahmat! Endi botdan foydalanishingiz mumkin.\n"
            "Botni guruhga qo'shish uchun quyidagi tugmani bosing:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Guruhga qo'shish", url=link)]
            ])
        )
    else:
        await call.answer("❌ Siz hali ham kanalga a'zo bo'lmadingiz!", show_alert=True)


@dp.message(AdFilter(), F.chat.type.in_({"group", "supergroup"}))
async def cleaner_handler(message: types.Message):
    try:
        member = await message.chat.get_member(message.from_user.id)
        if member.status in ['administrator', 'creator']:
            return
    except:
        return

    bot_member = await message.chat.get_member(bot.id)
    if bot_member.status != 'administrator' or not bot_member.can_delete_messages or not bot_member.can_restrict_members:
        return 

    user_id = message.from_user.id
    chat_id = message.chat.id
    now = datetime.now()

    try:
        await message.delete()
    except:
        pass

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
        else:
            new_count = 1
            mute_minutes = 10
    
    try:
        until_date = now + timedelta(minutes=mute_minutes)
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
    except Exception as e:
        logging.error(f"Restrict error: {e}")

    cursor.execute('''
        INSERT OR REPLACE INTO violations (user_id, chat_id, count, last_time)
        VALUES (?, ?, ?, ?)
    ''', (user_id, chat_id, new_count, now))
    conn.commit()

async def main():
    print(f"@{BOT_USERNAME} ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot to'xtatildi!")