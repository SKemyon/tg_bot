import asyncio
from datetime import datetime, timedelta

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import text

from database import async_session
from models import Lot, Bid, Watcher
from config import settings

active_auctions = {}  # lot_id -> bool (флаг, активен ли аукцион)

def get_bid_button_to_pm(lot_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔨 Поставить",
                    url=f"https://t.me/{settings.bot_username}?start=lot_{lot_id}"
                )
            ]
        ]
    )

async def start_auction(lot_id: int, bot):
    async with async_session() as session:
        lot = await session.get(Lot, lot_id)
        if not lot or lot.auction_started:
            return

        await asyncio.sleep(settings.auction_duration_minutes * 30)
        lot.auction_started = True
        lot.current_price = lot.start_price
        await session.commit()



    await bot.send_message(
        settings.auction_channel_id,
        f"Аукцион по лоту '{lot.title}' начался! Принимаются ставки.",
        reply_markup=get_bid_button_to_pm(lot.id)
    )


    #active_auctions[lot_id] = False

    # Ждём время аукциона (например, 10 минут)
    await asyncio.sleep(settings.auction_duration_minutes * 60)

    #active_auctions[lot_id] = False

    # Завершаем аукцион и объявляем победителя
    async with async_session() as session:
        lot = await session.get(Lot, lot_id)
        lot.auction_ended = True
        await session.commit()

        highest_bid = await session.execute(
            # получить самую высокую ставку
            text("SELECT * FROM bids WHERE lot_id = :lot_id ORDER BY amount DESC LIMIT 1"),
            {"lot_id": lot_id}
        )
        winner = highest_bid.first()

        if winner:
            winner_user_id = winner.user_id
            amount = winner.amount

            # кнопки для продавца
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Согласиться", callback_data=f"accept_deal_{lot.id}_{winner_user_id}")],
                [InlineKeyboardButton(text="❌ Отказаться", callback_data=f"reject_deal_{lot.id}_{winner_user_id}")]
            ])

            await bot.send_message(
                lot.seller_id,
                f"⚡ Аукцион завершён!\nПобедитель предложил {amount} тг за '{lot.title}'.\n"
                f"Согласитесь на сделку и мы отправим Ваши контакты покупателю.",
                reply_markup=kb
            )
            await bot.send_message(
                settings.auction_channel_id,
                f"Аукцион по лоту '{lot.title}' завершён! Победная ставка {amount} тг. "
            )

            await bot.send_message(
                winner_user_id,
                f"🎉 Поздравляем!!!\nВы выйграли лот '{lot.title}' за {amount} тг\nЕсли продавец согласится на Вашу ставку, мы пришлем Вам его контактный номер."
            )
        else:
            await bot.send_message(
                settings.auction_channel_id,
                f"Аукцион по лоту '{lot.title}' завершён без ставок."
            )
            await bot.send_message(
                lot.seller_id,
                f"Аукцион по Вашему лоту '{lot.title}' завершён без ставок."
            )



