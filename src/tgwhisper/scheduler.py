from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .models import ItemType
from .presentation import render_digest
from .repository import Repository

logger = logging.getLogger(__name__)


async def _send_once(
    repository: Repository,
    bot: Bot,
    user_id: int,
    delivery_key: str,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if repository.was_delivered(user_id, delivery_key):
        return
    try:
        await bot.send_message(user_id, text, reply_markup=reply_markup)
    except Exception:
        logger.exception("Telegram delivery failed for user_id=%s key=%s", user_id, delivery_key)
        return
    repository.record_delivery(user_id, delivery_key)


async def deliver(repository: Repository, bot: Bot) -> None:
    """Minute-level idempotent reminder and digest delivery."""
    for user in repository.users():
        user_id = int(user["telegram_id"])
        now = datetime.now(ZoneInfo(user["timezone"]))
        today = now.date().isoformat()
        minute = now.strftime("%H:%M")
        if minute == user["digest_time"]:
            items = repository.due_items(user_id, today)
            if items or user["empty_digest"]:
                await _send_once(
                    repository, bot, user_id, f"digest:{today}", render_digest(items)
                )
        for item in repository.due_items(user_id, today):
            if item.type != ItemType.REMINDER or not item.due_at or "T" not in item.due_at:
                continue
            if item.due_at[:16] <= now.isoformat()[:16]:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Готово", callback_data=f"done:{item.id}"),
                    InlineKeyboardButton(text="Через час", callback_data=f"later:{item.id}"),
                ]])
                await _send_once(
                    repository, bot, user_id, f"reminder:{item.id}:{item.due_at}",
                    f"🔔 {item.title}", keyboard,
                )


def start_scheduler(repository: Repository, bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(deliver, "interval", minutes=1, args=(repository, bot), max_instances=1)
    scheduler.start()
    return scheduler
