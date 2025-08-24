from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    bot_token: str
    admin_ids: list[int] = []
    auction_channel_id: int
    moderator_chat_id: int
    auction_duration_minutes: int = 1
    bot_username: str = 'bit_kz_bot'


    class Config:
        env_file = ".env"
        extra = "allow"
settings = Settings()