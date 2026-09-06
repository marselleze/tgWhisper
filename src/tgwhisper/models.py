from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ItemType(StrEnum):
    TASK = "task"
    WAITING = "waiting"
    NOTE = "note"
    REMINDER = "reminder"


class ItemStatus(StrEnum):
    INBOX = "inbox"
    ACTIVE = "active"
    DONE = "done"
    CANCELLED = "cancelled"


class Category(StrEnum):
    STAFF = "staff"
    EQUIPMENT = "equipment"
    MATERIALS = "materials"
    DOCUMENTS = "documents"
    SANITARY = "sanitary"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Item:
    id: int
    user_id: int
    type: ItemType
    title: str
    description: str | None
    status: ItemStatus
    category: Category
    created_at: datetime
    due_at: str | None
    completed_at: datetime | None
    waiting_for: str | None
    source_text: str

