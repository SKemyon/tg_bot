from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy import select
from new.database import async_session
from new.models import Lot

router = Router()

@router.message(Command("lots"))
async def list_active_lots(message: Message):
    async with async_session() as session:
        result = await session.execute(
            select(Lot).where(Lot.auction_ended == False)
        )
        lots = result.scalars().all()

    if not lots:
        return await message.answer("Сейчас нет активных лотов.")

    response = "📦 Активные лоты:\n"
    for lot in lots:
        response += (
            f"\n🆔 {lot.id} — {lot.title}\n"
            f"💬 {lot.description}\n"
            f"💰 Текущая цена: {lot.current_price or lot.start_price} ₽\n"
        )
    await message.answer(response)

