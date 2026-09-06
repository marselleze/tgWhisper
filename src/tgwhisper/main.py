from __future__ import annotations

import asyncio

from aiogram import Bot

from .ai import OpenAIAdapter
from .bot import create_dispatcher
from .config import Settings
from .repository import Repository
from .scheduler import start_scheduler


async def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    repository = Repository(settings.database_path)
    adapter = OpenAIAdapter(
        settings.openai_api_key,
        settings.openai_text_model,
        settings.openai_transcription_model,
    )
    bot = Bot(settings.telegram_bot_token)
    dispatcher = create_dispatcher(repository, adapter)
    scheduler = start_scheduler(repository, bot)
    try:
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
