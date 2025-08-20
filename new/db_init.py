import asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings  # твои настройки с DATABASE_URL
from models import Base  # где у тебя объявлены модели (Lot, LotImage, ...)


async def init_db():
    engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///my_base2.db", echo=True)

    async with engine.begin() as conn:
        # Создаёт все таблицы по моделям
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())
