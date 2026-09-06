"""Validate Telegram credentials with a read-only getMe request."""

from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from tgwhisper.config import Settings


async def main() -> int:
    settings = Settings()  # type: ignore[call-arg]
    bot = Bot(settings.telegram_bot_token)
    try:
        try:
            identity = await bot.get_me()
        except TelegramAPIError as error:
            print(f"Telegram check failed: {type(error).__name__}: {error}")
            return 2
        print(
            {
                "ok": True,
                "id": identity.id,
                "username": identity.username,
                "can_join_groups": identity.can_join_groups,
            }
        )
        return 0
    finally:
        await bot.session.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
