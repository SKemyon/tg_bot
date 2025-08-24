from sqlalchemy import (
    Column, Integer, String, ForeignKey, DateTime, Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.sql.sqltypes import Enum
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
  # твой базовый класс из engine

# class Lot(Base):
#     __tablename__ = "lots"
#
#     id = Column(Integer, primary_key=True, index=True)
#     user_id = Column(Integer, index=True)  # ID продавца в Telegram
#     model = Column(String, nullable=False)
#     start_price = Column(Integer, nullable=False)
#
#     memory = Column(String)        # Объём памяти
#     year = Column(Integer)         # Год покупки
#     condition = Column(String)     # Общее состояние
#     screen_state = Column(String)  # Состояние экрана
#     battery_state = Column(String) # Ёмкость аккумулятора / состояние
#     face_id = Column(Boolean)      # Работает ли Face ID / отпечаток
#     repairs = Column(Boolean)      # Были ли ремонты
#     water_damage = Column(Boolean) # Был ли в воде
#     locks = Column(Boolean)        # Есть ли блокировки (Apple ID, Google)
#     imei = Column(String)          # IMEI телефона
#     imei_verified = Column(Boolean, default=False)
#
#     confirmed_ownership = Column(Boolean) # Согласие "не краден"
#     agreed_imei_check = Column(Boolean)   # Согласие на проверку IMEI
#
#     created_at = Column(DateTime, default=datetime.utcnow)
#
#     # Связь с фото
#     images = relationship("LotImage", back_populates="lot")
#
# class LotImage(Base):
#     __tablename__ = "lot_images"
#
#     id = Column(Integer, primary_key=True, index=True)
#     lot_id = Column(Integer, ForeignKey("lots.id"))
#     file_id = Column(String, nullable=False)  # file_id из Telegram
#     unique_hash = Column(String, nullable=False)  # хэш для проверки уникальности
#
#     lot = relationship("Lot", back_populates="images")
class LotStatus(enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Lot(Base):
    __tablename__ = "lots"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    start_price = Column(Integer, nullable=False)
    seller_id = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    auction_started = Column(Boolean, default=False)
    auction_ended = Column(Boolean, default=False)
    current_price = Column(Integer, default=0)

    memory = Column(String, nullable=True)
    year = Column(String, nullable=True)
    condition = Column(String, nullable=True)
    battery = Column(String, nullable=True)
    repairs = Column(String, nullable=True)
    water = Column(String, nullable=True)
    locks = Column(String, nullable=True)

    status = Column(Enum(LotStatus), default=LotStatus.pending, nullable=False)


    bids = relationship("Bid", back_populates="lot", cascade="all, delete-orphan")
    watchers = relationship("Watcher", back_populates="lot", cascade="all, delete-orphan")

    images = relationship("LotImage", back_populates="lot", cascade="all, delete-orphan")



class LotImage(Base):
    __tablename__ = "lot_images"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(Integer, ForeignKey("lots.id", ondelete="CASCADE"), nullable=False)
    file_id = Column(String, nullable=False)

    lot = relationship("Lot", back_populates="images")


class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=False)
    user_id = Column(Integer, nullable=False)
    amount = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lot = relationship("Lot", back_populates="bids")

class Watcher(Base):
    __tablename__ = "watchers"

    id = Column(Integer, primary_key=True)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=False)
    user_id = Column(Integer, nullable=False)

    lot = relationship("Lot", back_populates="watchers")