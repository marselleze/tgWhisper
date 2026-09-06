from __future__ import annotations

from collections import defaultdict

from .models import Item, ItemType
from .schemas import Extraction, OperationKind

ICONS = {
    ItemType.TASK: "📦", ItemType.WAITING: "⏳",
    ItemType.NOTE: "📝", ItemType.REMINDER: "🔔",
}


def render_preview(extraction: Extraction) -> str:
    lines = [f"Подтвердить {len(extraction.operations)} пункт(а)?", ""]
    for operation in extraction.operations:
        if operation.kind == OperationKind.CREATE:
            item = operation.item
            assert item is not None
            lines.extend([
                f"{ICONS[item.type]} {item.title}",
                f"Срок: {item.due_at or 'не указан'}", "",
            ])
        elif operation.kind == OperationKind.COMPLETE:
            lines.extend([f"✓ Завершить пункт #{operation.target_item_id}", ""])
        elif operation.kind == OperationKind.RESCHEDULE:
            lines.extend([
                f"⏳ Перенести пункт #{operation.target_item_id}",
                f"Новый срок: {operation.due_at}", "",
            ])
        else:
            lines.extend([f"Отменить пункт #{operation.target_item_id}", ""])
    return "\n".join(lines).rstrip()


def render_digest(items: list[Item]) -> str:
    if not items:
        return "На сегодня ничего нет."
    groups: dict[ItemType, list[Item]] = defaultdict(list)
    for item in items:
        groups[item.type].append(item)
    labels = {
        ItemType.TASK: "🔴 Задачи", ItemType.WAITING: "⏳ Ожидания",
        ItemType.REMINDER: "🔔 Напоминания", ItemType.NOTE: "📝 Заметки",
    }
    lines = ["Доброе утро.", "", "На сегодня:", ""]
    for item_type in ItemType:
        if groups[item_type]:
            lines.append(f"{labels[item_type]} — {len(groups[item_type])}")
            lines.extend(f"• {item.title}" for item in groups[item_type])
            lines.append("")
    return "\n".join(lines).rstrip()

