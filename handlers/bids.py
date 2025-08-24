from aiogram import Router, Bot, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from sqlalchemy.future import select
from sqlalchemy import desc
from collections import defaultdict
import asyncio

from database import async_session
from models import Lot, Bid, Watcher
from states import BidStates

CHANNEL_ID = -1002896763134

# Очереди ставок по lot_id
lot_bid_queues = defaultdict(asyncio.Queue)

router = Router()

# Главное меню (теперь будет всегда доступно)
# Главное меню
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📤 Хочу продать"), KeyboardButton(text="📋 Список аукционов")],
        [KeyboardButton(text="ℹ️ Правила"), KeyboardButton(text="📞 Поддержка")]
    ],
    resize_keyboard=True
)



# Обработчик кнопки "Поддержка"
@router.message(F.text == "📞 Поддержка")
async def support_handler(message: Message):
    support_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Написать в поддержку", url="https://t.me/+77778032236")]
        ]
    )
    await message.answer(
        "💬 Если у вас возникли вопросы или проблемы, свяжитесь с нашей поддержкой:",
        reply_markup=support_keyboard
    )

# Красивая карточка лота
def format_lot_card(lot):
    price = lot.current_price or lot.start_price
    return (
        f"📦 <b>{lot.title}</b>\n"
        f"📝 {lot.condition}\n"
        f"🛠 Ремонт:{lot.repairs}\n"
        f"🔋 Аккумулятор: {lot.battery}\n"
        f"💾 Память: {lot.memory}\n"
        f"📅 Год покупки: {lot.year}\n"
        f"🔒 Блокировки: {lot.locks}\n"
        f"💰 <b>Текущая цена:</b> {price}₽\n"
        f"🆔 ID: <code>{lot.id}</code>"
    )

# Кнопки для ставок
def get_bid_buttons(current_price: int, lot_id: int):
    increments = [100, 500, 1000]
    bid_buttons = [
        InlineKeyboardButton(
            text=f"💸 +{inc}₽ (итого {current_price + inc}₽)",
            callback_data=f"bid_{lot_id}_{inc}"
        )
        for inc in increments
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            bid_buttons
        ]
    )

@router.message(CommandStart(deep_link=True))
async def handle_start_with_lot(message: Message, command: CommandObject):
    if command.args and command.args.startswith("lot_"):
        lot_id = int(command.args.split("_")[1])

        async with async_session() as session:
            lot = await session.get(Lot, lot_id)
            if not lot:
                await message.answer("❌ Лот с таким ID не найден.", reply_markup=main_menu)
                return

            existing = await session.execute(
                select(Watcher).filter_by(lot_id=lot_id, user_id=message.from_user.id)
            )
            if existing.scalars().first():
                await message.answer("⚠️ Вы уже подписаны на этот лот.", reply_markup=main_menu)
                return

            session.add(Watcher(lot_id=lot_id, user_id=message.from_user.id))
            await session.commit()

            await message.answer(
                "ℹ️ Аукцион — это быстрый способ продать телефон.\n\n"
                "1.Участвуя в торгах, вы обязуетесь оплатить лотв случае Вашей победы.\n"
                "2.В случае отказа от победной ставки взимается штраф 1% от стоимости.\n"
                "3.Комиссия за успешную сделку 1%\n"
                "4.Сделка и расчёты происходят напрямую с продавцом. В случае победы мы предоставим контакты продавца\n"
                "5.При нарушении правил возможна блокировка.\n\n"
                "Продолжая Вы соглашаетесь с правилами аукциона(побдробнее можно посмотреть в разделе Правила"
            )

            await message.answer(
                f"✅ Вы подписались на лот:\n\n{format_lot_card(lot)}",
                reply_markup=get_bid_buttons(lot.current_price or lot.start_price, lot_id),
                parse_mode="HTML"
            )

            await message.answer("Выберите действие:", reply_markup=main_menu)

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("Выберите действие:", reply_markup=main_menu)

@router.message(F.text == "📋 Список аукционов")
async def handle_list_auctions(message: Message):
    async with async_session() as session:
        result = await session.execute(
            select(Lot).where(Lot.auction_ended == False)
        )
        lots = result.scalars().all()

    if not lots:
        await message.answer("📭 Нет активных аукционов.", reply_markup=main_menu)
        return

    for lot in lots:
        await message.answer(format_lot_card(lot), parse_mode="HTML")

    await message.answer("✍️ Отправьте ID лота, чтобы подписаться.", reply_markup=main_menu)

@router.message(F.text.regexp(r"^\d+$"))
async def watch_lot(message: Message):
    lot_id = int(message.text)

    async with async_session() as session:
        lot = await session.get(Lot, lot_id)
        if not lot:
            await message.answer("❌ Лот с таким ID не найден.", reply_markup=main_menu)
            return

        existing = await session.execute(
            select(Watcher).filter_by(lot_id=lot_id, user_id=message.from_user.id)
        )
        if existing.scalars().first():
            await message.answer("⚠️ Вы уже подписаны на этот лот.", reply_markup=main_menu)
            return

        session.add(Watcher(lot_id=lot_id, user_id=message.from_user.id))
        await session.commit()

        await message.answer(
            "ℹ️ Аукцион — это быстрый способ продать телефон.\n\n"
            "1. Выберите модель 📱\n"
            "2. Загрузите фото 📸\n"
            "3. Опишите товар 📝\n\n"
            "❗ После публикации изменить лот будет нельзя!"
        )

        await message.answer(
            f"✅ Вы подписались на лот:\n\n{format_lot_card(lot)}",
            reply_markup=get_bid_buttons(lot.current_price or lot.start_price, lot_id),
            parse_mode="HTML"
        )

        await message.answer("Выберите действие:", reply_markup=main_menu)

@router.callback_query(F.data.startswith("bid_"))
async def process_bid(callback: CallbackQuery):
    try:
        bot = callback.bot
        user_id = callback.from_user.id
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        if member.status in ("left", "kicked"):
            await callback.answer("📢 Подпишитесь на канал, чтобы участвовать в торгах.", show_alert=True)
            return
    except TelegramBadRequest:
        await callback.answer("⚠️ Ошибка проверки подписки.", show_alert=True)
        return

    try:
        _, lot_id_str, inc_str = callback.data.split("_")
        lot_id = int(lot_id_str)
        inc = int(inc_str)
    except (ValueError, IndexError):
        await callback.answer("❌ Некорректные данные.")
        return

    await lot_bid_queues[lot_id].put((callback, inc))

    if lot_bid_queues[lot_id].qsize() == 1:
        asyncio.create_task(process_lot_bids(lot_id))

async def process_lot_bids(lot_id: int):
    while not lot_bid_queues[lot_id].empty():
        callback, inc = await lot_bid_queues[lot_id].get()
        user_id = callback.from_user.id

        async with async_session() as session:
            lot = await session.get(Lot, lot_id)
            if not lot:
                await callback.answer("❌ Лот не найден.", show_alert=True)
                lot_bid_queues[lot_id].task_done()
                continue

            if lot.auction_ended:
                await callback.answer("⏳ Аукцион завершен.", show_alert=True)
                lot_bid_queues[lot_id].task_done()
                continue

            if not lot.auction_started:
                await callback.answer("⌛ Аукцион еще не начался.", show_alert=True)
                lot_bid_queues[lot_id].task_done()
                continue

            current_price = lot.current_price or lot.start_price
            new_price = current_price + inc

            highest_bid_res = await session.execute(
                select(Bid).filter_by(lot_id=lot_id).order_by(desc(Bid.amount)).limit(1)
            )
            highest_bid = highest_bid_res.scalars().first()
            if highest_bid and new_price <= highest_bid.amount:
                await callback.answer(f"⚠️ Ставка должна быть больше {highest_bid.amount}₽.", show_alert=True)
                lot_bid_queues[lot_id].task_done()
                continue

            session.add(Bid(lot_id=lot_id, user_id=user_id, amount=new_price))
            lot.current_price = new_price
            await session.commit()

        await callback.answer(f"✅ Ставка {new_price}₽ принята.", show_alert=True)
        await callback.message.answer(f"✅ Ваша ставка {new_price} принята.")
        bot = callback.bot
        async with async_session() as session:
            watchers_res = await session.execute(
                select(Watcher).filter_by(lot_id=lot_id)
            )
            watchers_list = watchers_res.scalars().all()

            for w in watchers_list:
                if w.user_id != user_id:
                    try:
                        await bot.send_message(w.user_id, f"📢 Новая ставка по лоту #{lot_id}: {new_price}₽")
                    except:

                        pass

            try:
                await bot.send_message(lot.seller_id, f"📢 Новая ставка по вашему лоту #{lot_id}: {new_price}₽")
            except:
                pass

        await asyncio.sleep(1)
        lot_bid_queues[lot_id].task_done()
