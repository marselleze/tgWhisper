from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .models import Category, Item, ItemStatus, ItemType
from .schemas import Extraction, ItemDraft, OperationKind

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    timezone TEXT NOT NULL DEFAULT 'Europe/Moscow',
    digest_time TEXT NOT NULL DEFAULT '08:00',
    empty_digest INTEGER NOT NULL DEFAULT 0 CHECK (empty_digest IN (0, 1))
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('task','waiting','note','reminder')),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL CHECK (status IN ('inbox','active','done','cancelled')),
    category TEXT NOT NULL CHECK (
        category IN ('staff','equipment','materials','documents','sanitary','other')
    ),
    created_at TEXT NOT NULL,
    due_at TEXT,
    completed_at TEXT,
    waiting_for TEXT,
    source_text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_user_status_due
    ON items(user_id, status, due_at);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    extraction_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    confirmed_at TEXT,
    cancelled_at TEXT
);
CREATE TABLE IF NOT EXISTS item_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    old_due_at TEXT,
    new_due_at TEXT,
    comment TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deliveries (
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    delivery_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(user_id, delivery_key)
);
"""


class Repository:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(SCHEMA)

    def ensure_user(
        self, user_id: int, timezone: str = "Europe/Moscow", digest_time: str = "08:00"
    ) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO users(telegram_id, timezone, digest_time) VALUES (?, ?, ?)",
                (user_id, timezone, digest_time),
            )

    def user_settings(self, user_id: int) -> sqlite3.Row:
        self.ensure_user(user_id)
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
            assert row is not None
            return row

    def create_draft(self, user_id: int, extraction: Extraction) -> int:
        self.ensure_user(user_id)
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO drafts(user_id, extraction_json, created_at) VALUES (?, ?, ?)",
                (user_id, extraction.model_dump_json(), _now()),
            )
            return int(cursor.lastrowid)

    def confirm_draft(self, user_id: int, draft_id: int) -> list[int]:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM drafts WHERE id = ? AND user_id = ?", (draft_id, user_id)
            ).fetchone()
            if row is None:
                raise LookupError("draft not found")
            if row["confirmed_at"] or row["cancelled_at"]:
                raise ValueError("draft is no longer pending")
            extraction = Extraction.model_validate_json(row["extraction_json"])
            created_ids: list[int] = []
            for operation in extraction.operations:
                if operation.kind == OperationKind.CREATE:
                    assert operation.item is not None
                    created_ids.append(self._insert_item(db, user_id, operation.item))
                else:
                    self._apply_mutation(db, user_id, operation)
            db.execute("UPDATE drafts SET confirmed_at = ? WHERE id = ?", (_now(), draft_id))
            return created_ids

    def cancel_draft(self, user_id: int, draft_id: int) -> None:
        with self.connect() as db:
            changed = db.execute(
                "UPDATE drafts SET cancelled_at = ? WHERE id = ? AND user_id = ? "
                "AND confirmed_at IS NULL AND cancelled_at IS NULL",
                (_now(), draft_id, user_id),
            ).rowcount
            if changed != 1:
                raise LookupError("pending draft not found")

    def active_items(self, user_id: int) -> list[Item]:
        return self._items(
            "user_id = ? AND status IN ('inbox','active') ORDER BY due_at IS NULL, due_at, id",
            (user_id,),
        )

    def due_items(self, user_id: int, local_date: str) -> list[Item]:
        return self._items(
            "user_id = ? AND status = 'active' AND due_at IS NOT NULL "
            "AND substr(due_at, 1, 10) <= ? ORDER BY due_at, id",
            (user_id, local_date),
        )

    def users(self) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute("SELECT * FROM users ORDER BY telegram_id").fetchall()

    def claim_delivery(self, user_id: int, delivery_key: str) -> bool:
        """Atomically reserve a digest/reminder delivery to prevent duplicates."""
        with self.connect() as db:
            changed = db.execute(
                "INSERT OR IGNORE INTO deliveries"
                "(user_id, delivery_key, created_at) VALUES (?, ?, ?)",
                (user_id, delivery_key, _now()),
            ).rowcount
            return changed == 1

    def was_delivered(self, user_id: int, delivery_key: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT 1 FROM deliveries WHERE user_id = ? AND delivery_key = ?",
                (user_id, delivery_key),
            ).fetchone()
            return row is not None

    def record_delivery(self, user_id: int, delivery_key: str) -> None:
        """Record success after Telegram accepted the message."""
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO deliveries"
                "(user_id, delivery_key, created_at) VALUES (?, ?, ?)",
                (user_id, delivery_key, _now()),
            )

    def apply_confirmed_operation(self, user_id: int, operation: object) -> None:
        """Apply an operation already confirmed by an explicit UI action."""
        with self.connect() as db:
            self._apply_mutation(db, user_id, operation)

    def _items(self, where: str, params: tuple[object, ...]) -> list[Item]:
        with self.connect() as db:
            rows = db.execute(f"SELECT * FROM items WHERE {where}", params).fetchall()
            return [_row_to_item(row) for row in rows]

    @staticmethod
    def _insert_item(db: sqlite3.Connection, user_id: int, item: ItemDraft) -> int:
        cursor = db.execute(
            """INSERT INTO items(
                user_id, type, title, description, status, category, created_at,
                due_at, completed_at, waiting_for, source_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
            (
                user_id, item.type, item.title, item.description, item.status,
                item.category, _now(), item.due_at, item.waiting_for, item.source_text,
            ),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _apply_mutation(db: sqlite3.Connection, user_id: int, operation: object) -> None:
        target_id = operation.target_item_id
        row = db.execute(
            "SELECT * FROM items WHERE id = ? AND user_id = ? AND status IN ('inbox','active')",
            (target_id, user_id),
        ).fetchone()
        if row is None:
            raise LookupError("active target item not found")
        if operation.kind == OperationKind.COMPLETE:
            db.execute(
                "UPDATE items SET status = 'done', completed_at = ? WHERE id = ?",
                (_now(), target_id),
            )
        elif operation.kind == OperationKind.CANCEL:
            db.execute("UPDATE items SET status = 'cancelled' WHERE id = ?", (target_id,))
        elif operation.kind == OperationKind.RESCHEDULE:
            db.execute("UPDATE items SET due_at = ? WHERE id = ?", (operation.due_at, target_id))
        db.execute(
            """INSERT INTO item_events(
                item_id, event_type, old_due_at, new_due_at, comment, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (target_id, operation.kind, row["due_at"], operation.due_at, operation.comment, _now()),
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_item(row: sqlite3.Row) -> Item:
    return Item(
        id=row["id"], user_id=row["user_id"], type=ItemType(row["type"]),
        title=row["title"], description=row["description"], status=ItemStatus(row["status"]),
        category=Category(row["category"]), created_at=datetime.fromisoformat(row["created_at"]),
        due_at=row["due_at"], completed_at=(datetime.fromisoformat(row["completed_at"])
        if row["completed_at"] else None), waiting_for=row["waiting_for"],
        source_text=row["source_text"],
    )
