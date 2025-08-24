from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData

from database import async_session
from models import Lot, Watcher, Bid
from auctions.logic import active_auctions
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

@router.message(Command("follow"))
async def follow_lot(message: Message):
    # ожидание айди лота после команды
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Используйте: /follow <id лота>")

    lot_id = int(args[1])

    async with async_session() as session:
        lot = await session.get(Lot, lot_id)
        if not lot:
            return await message.answer("Лот не найден")

        # добавляем подписчика
        watcher = Watcher(lot_id=lot_id, user_id=message.from_user.id)
        session.add(watcher)
        await session.commit()

    await message.answer(f"Вы подписались на лот {lot.title}")

    # Отправить клавиатуру для ставок
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="+100", callback_data=f"bid_{lot_id}_100"),
            InlineKeyboardButton(text="+500", callback_data=f"bid_{lot_id}_500"),
            InlineKeyboardButton(text="+1000", callback_data=f"bid_{lot_id}_1000"),
        ]
    ])
    await message.answer("Поднимите ставку:", reply_markup=keyboard)


@router.callback_query(F.text.startswith("bid_"))
async def process_bid(callback: CallbackQuery):
    _, lot_id_str, increment_str = callback.data.split("_")
    lot_id = int(lot_id_str)
    increment = int(increment_str)
    user_id = callback.from_user.id

    if not active_auctions.get(lot_id, False):
        return await callback.answer("Аукцион по этому лоту завершён.", show_alert=True)

    async with async_session() as session:
        lot = await session.get(Lot, lot_id)
        if not lot or lot.auction_ended:
            return await callback.answer("Аукцион завершён или лот не найден.", show_alert=True)

        # Проверяем текущую ставку и обновляем
        new_price = lot.current_price + increment
        lot.current_price = new_price

        bid = Bid(lot_id=lot_id, user_id=user_id, amount=new_price)
        session.add(bid)
        await session.commit()

        # Отправляем обновления всем подписчикам
        watchers = await session.execute(
            f"SELECT user_id FROM watchers WHERE lot_id = :lot_id",
            {"lot_id": lot_id}
        )
        watchers_ids = [w[0] for w in watchers.fetchall()]

    for watcher_id in watchers_ids:
        try:
            await callback.bot.send_message(watcher_id, f"Новая ставка по лоту {lot.title}: {new_price} ₽")
        except:
            pass

    # Отправляем ответ дилеру, что ставка принята
    await callback.answer(f"Ставка повышена до {new_price} ₽")
