import os




from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import aiosqlite



DATABASE_URL = "sqlite+aiosqlite:///./auction.db"
DB_LITE="sqlite+aiosqlite:///my_base2.db"

engine = create_async_engine(DB_LITE, echo=True)

async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass