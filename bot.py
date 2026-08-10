import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8725302935:AAEnBgrGYZACH-SNA5VKWeZX3Jhw72ltxro"
WEBAPP_URL = "https://ваш-домен.com/" # Ссылка на развернутый HTML-файл

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Запустить проверку", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer("Анализатор юзернеймов готов к работе:", reply_markup=markup)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())