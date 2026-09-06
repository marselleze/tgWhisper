from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import Category, ItemStatus, ItemType


class OperationKind(StrEnum):
    CREATE = "create"
    COMPLETE = "complete"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"


class ItemDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ItemType
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    status: ItemStatus
    category: Category
    due_at: str | None = None
    waiting_for: str | None = Field(default=None, max_length=200)
    source_text: str = Field(min_length=1, max_length=4000)

    @field_validator("due_at")
    @classmethod
    def validate_due_at(cls, value: str | None) -> str | None:
        return _validate_due_at(value)


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: OperationKind
    item: ItemDraft | None = None
    target_item_id: int | None = None
    due_at: str | None = None
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("due_at")
    @classmethod
    def validate_due_at(cls, value: str | None) -> str | None:
        return _validate_due_at(value)

    @model_validator(mode="after")
    def validate_shape(self) -> Operation:
        if self.kind == OperationKind.CREATE and self.item is None:
            raise ValueError("create requires item")
        if self.kind == OperationKind.CREATE and self.target_item_id is not None:
            raise ValueError("create must not target an existing item")
        if self.kind != OperationKind.CREATE and self.target_item_id is None:
            raise ValueError("mutation requires target_item_id")
        if self.kind != OperationKind.CREATE and self.item is not None:
            raise ValueError("mutation must not contain a new item")
        if self.kind == OperationKind.RESCHEDULE and self.due_at is None:
            raise ValueError("reschedule requires due_at")
        if self.kind in {OperationKind.COMPLETE, OperationKind.CANCEL} and self.due_at is not None:
            raise ValueError("complete/cancel must not change due_at")
        return self


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[Operation] = Field(max_length=20)
    needs_clarification: bool = False
    clarification_question: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_clarification(self) -> Extraction:
        if self.needs_clarification and not self.clarification_question:
            raise ValueError("clarification question is required")
        if self.needs_clarification and self.operations:
            raise ValueError("clarification response must not contain operations")
        return self


def _validate_due_at(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        if "T" not in value:
            parsed_date = date.fromisoformat(value)
            if value != parsed_date.isoformat():
                raise ValueError
            return value
        parsed_datetime = datetime.fromisoformat(value)
        if parsed_datetime.tzinfo is None or parsed_datetime.utcoffset() is None:
            raise ValueError("datetime due_at must include a timezone offset")
        return value
    except ValueError as error:
        raise ValueError("due_at must be an ISO date or timezone-aware ISO datetime") from error
