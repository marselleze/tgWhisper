from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .ai import OpenAIAdapter
from .presentation import format_due_at, render_digest, render_preview
from .repository import Repository
from .schemas import Operation, OperationKind
from .service import CaptureService

router = Router()


def confirmation_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Всё верно", callback_data=f"confirm:{draft_id}"),
            InlineKeyboardButton(text="Исправить", callback_data=f"edit:{draft_id}"),
        ],
        [InlineKeyboardButton(text="Отмена", callback_data=f"cancel:{draft_id}")],
    ])


@router.message(Command("start"))
async def start(message: Message, capture_service: CaptureService) -> None:
    assert message.from_user is not None
    capture_service.repository.ensure_user(message.from_user.id)
    await message.answer(
        "Здравствуйте! Пришлите рабочую мысль текстом или голосом. "
        "Я покажу, что поняла, прежде чем сохранить.\n\n"
        "Часовой пояс: Europe/Moscow. Утренняя сводка: 08:00."
    )


@router.message(Command("today"))
async def today(message: Message, capture_service: CaptureService) -> None:
    assert message.from_user is not None
    settings = capture_service.repository.user_settings(message.from_user.id)
    date = datetime.now(ZoneInfo(settings["timezone"])).date().isoformat()
    due_items = capture_service.repository.due_items(message.from_user.id, date)
    await message.answer(render_digest(due_items))


@router.message(Command("help"))
async def help_message(message: Message) -> None:
    await message.answer(
        "Пришлите текст или голосовое, например:\n"
        "• Завтра заказать перчатки\n"
        "• Техник будет во вторник\n"
        "• В 15 часов напомни позвонить поставщику\n"
        "• Перчатки заказала\n\n"
        "Команды: /today, /inbox, /all, /settings"
    )


@router.message(Command("settings"))
async def settings(message: Message, capture_service: CaptureService) -> None:
    assert message.from_user is not None
    values = capture_service.repository.user_settings(message.from_user.id)
    await message.answer(
        "Настройки\n\n"
        f"Часовой пояс: {values['timezone']}\n"
        f"Утренняя сводка: {values['digest_time']}\n"
        f"Пустая сводка: {'включена' if values['empty_digest'] else 'выключена'}"
    )


@router.message(Command("inbox"))
@router.message(Command("all"))
async def show_items(message: Message, capture_service: CaptureService) -> None:
    assert message.from_user is not None
    items = capture_service.repository.active_items(message.from_user.id)
    if message.text and message.text.startswith("/inbox"):
        items = [item for item in items if item.due_at is None]
    text = "\n".join(
        f"#{item.id} · {item.title} · "
        f"{format_due_at(item.due_at) if item.due_at else 'без срока'}"
        for item in items
    )
    await message.answer(text or "Список пуст.")


async def _propose(message: Message, text: str, service: CaptureService) -> None:
    assert message.from_user is not None
    try:
        draft_id, extraction = await service.propose(message.from_user.id, text)
    except Exception:
        await message.answer("Сейчас не получилось обработать запись. Я ничего не сохранила.")
        return
    if extraction.needs_clarification:
        await message.answer(extraction.clarification_question or "Уточните, пожалуйста.")
        return
    assert draft_id is not None
    await message.answer(render_preview(extraction), reply_markup=confirmation_keyboard(draft_id))


@router.message(F.voice)
async def voice(
    message: Message, capture_service: CaptureService, openai_adapter: OpenAIAdapter
) -> None:
    assert message.voice is not None
    status = await message.answer("🎙 Распознаю голосовое…")
    buffer = BytesIO()
    try:
        await message.bot.download(message.voice, destination=buffer)
        text = await openai_adapter.transcribe("voice.ogg", buffer.getvalue())
        await status.edit_text(f"Распознано: «{text}»")
        await _propose(message, text, capture_service)
    except Exception:
        await status.edit_text(
            "Не удалось разобрать голосовое. Попробуйте записать ещё раз или пришлите текст."
        )


@router.message(F.text, ~F.text.startswith("/"))
async def text(message: Message, capture_service: CaptureService) -> None:
    assert message.text is not None
    await _propose(message, message.text, capture_service)


@router.callback_query(F.data.startswith("confirm:"))
async def confirm(callback: CallbackQuery, capture_service: CaptureService) -> None:
    assert callback.from_user is not None and callback.data is not None
    draft_id = int(callback.data.partition(":")[2])
    try:
        created = capture_service.confirm(callback.from_user.id, draft_id)
        await callback.message.edit_text(f"✓ Сохранено. Новых пунктов: {len(created)}")
    except (LookupError, ValueError):
        await callback.answer("Этот черновик уже обработан.", show_alert=True)
    await callback.answer()


@router.callback_query(F.data.startswith("cancel:"))
async def cancel(callback: CallbackQuery, capture_service: CaptureService) -> None:
    assert callback.from_user is not None and callback.data is not None
    draft_id = int(callback.data.partition(":")[2])
    try:
        capture_service.cancel(callback.from_user.id, draft_id)
        await callback.message.edit_text("Отменено. Ничего не сохранено.")
    except LookupError:
        await callback.answer("Этот черновик уже обработан.", show_alert=True)
    await callback.answer()


@router.callback_query(F.data.startswith("edit:"))
async def edit(callback: CallbackQuery, capture_service: CaptureService) -> None:
    assert callback.from_user is not None and callback.data is not None
    draft_id = int(callback.data.partition(":")[2])
    try:
        capture_service.cancel(callback.from_user.id, draft_id)
        await callback.message.edit_text(
            "Черновик отменён. Пришлите исправленный вариант текстом или голосом."
        )
    except LookupError:
        await callback.answer("Этот черновик уже обработан.", show_alert=True)
    await callback.answer()


@router.callback_query(F.data.startswith("done:"))
async def done(callback: CallbackQuery, capture_service: CaptureService) -> None:
    assert callback.from_user is not None and callback.data is not None
    item_id = int(callback.data.partition(":")[2])
    try:
        capture_service.repository.apply_confirmed_operation(
            callback.from_user.id,
            Operation(kind=OperationKind.COMPLETE, target_item_id=item_id),
        )
        await callback.message.edit_text("✓ Выполнено.")
    except LookupError:
        await callback.answer("Пункт уже закрыт или не найден.", show_alert=True)
    await callback.answer()


@router.callback_query(F.data.startswith("later:"))
async def later(callback: CallbackQuery, capture_service: CaptureService) -> None:
    assert callback.from_user is not None and callback.data is not None
    item_id = int(callback.data.partition(":")[2])
    active_items = capture_service.repository.active_items(callback.from_user.id)
    items = {item.id: item for item in active_items}
    item = items.get(item_id)
    if item is None or item.due_at is None or "T" not in item.due_at:
        await callback.answer("Не удалось перенести этот пункт.", show_alert=True)
        return
    new_due = (datetime.fromisoformat(item.due_at) + timedelta(hours=1)).isoformat()
    capture_service.repository.apply_confirmed_operation(
        callback.from_user.id,
        Operation(
            kind=OperationKind.RESCHEDULE,
            target_item_id=item_id,
            due_at=new_due,
            comment="Отложено кнопкой «Через час»",
        ),
    )
    await callback.message.edit_text(f"⏳ Напомню через час — в {new_due[11:16]}.")
    await callback.answer()


def create_dispatcher(repository: Repository, adapter: OpenAIAdapter) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    dispatcher["capture_service"] = CaptureService(repository, adapter)
    dispatcher["openai_adapter"] = adapter
    return dispatcher
