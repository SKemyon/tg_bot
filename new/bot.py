import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
#from aiogram.fsm.state import StatesGroup, State

from new.config import settings
from new.database import async_session, engine, Base
from new.handlers import seller, dealer, auctions, bids


logging.basicConfig(level=logging.INFO)




bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

dp.include_router(seller.router)
dp.include_router(dealer.router)
dp.include_router(auctions.router)
dp.include_router(bids.router)
# class SellerStates(StatesGroup):
#     title = State()
#     description = State()
#     start_price = State()

async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # восстановление активных аукционов, если нужно

async def main():
    await on_startup()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())



#не обрабатывает на какой именно лот ставка.
#заблокировать ставку на свой лот.
#сообщать победителю что он победитель.
#лаг между сообщением и началом торгов.

#сделать правильный запрос данных о телефоне у продавца
#пользовательское соглашение
#кидать предупреждения о добросовестном сотрудничестве
#платежка
#подумать над общим дизайном
#обрабатывать ставки через очередь.

#разделить логику бота на контакт с продавцом и покупателем.
#готово после фото лучше перенести на кнопки
#переход с канала на лот по кнопке
#почему не пишет 'аукцион завершен'
#надо что бы не обрабатывал запросы пришедшие во время спячки
