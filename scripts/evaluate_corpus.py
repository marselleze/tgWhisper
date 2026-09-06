"""Run the 40-message contract corpus against the configured OpenAI model.

This intentionally requires an explicit OPENAI_API_KEY and makes paid API calls.
It prints only aggregate/case-level contract results, never the credential.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from openai import OpenAIError

from tgwhisper.ai import OpenAIAdapter
from tgwhisper.models import Category, Item, ItemStatus, ItemType

ROOT = Path(__file__).parents[1]
CORPUS = json.loads((ROOT / "tests" / "corpus.json").read_text(encoding="utf-8"))
ZONE = ZoneInfo("Europe/Moscow")


def item(
    item_id: int,
    title: str,
    item_type: ItemType,
    due: str | None = None,
    waiting_for: str | None = None,
) -> Item:
    return Item(
        id=item_id, user_id=1, type=item_type, title=title, description=None,
        status=ItemStatus.ACTIVE, category=Category.OTHER,
        created_at=datetime(2026, 9, 1, tzinfo=ZONE), due_at=due,
        completed_at=None, waiting_for=waiting_for,
        source_text=title,
    )


CONTEXTS = {
    "gloves_task": [item(1, "Заказать перчатки", ItemType.TASK)],
    "journal_task": [item(4, "Проверить журнал стерилизации", ItemType.TASK)],
    "application_task": [item(5, "Отправить заявку на расходники", ItemType.TASK)],
    "technician_waiting": [
        item(2, "Техник — визит", ItemType.WAITING, "2026-09-05", "техник")
    ],
    "supplier_waiting": [
        item(6, "Поставщик — доставка", ItemType.WAITING, "2026-09-08", "поставщик")
    ],
    "sergey_waiting": [
        item(7, "Сергей — осмотр компрессора", ItemType.WAITING, "2026-09-06", "Сергей")
    ],
    "two_matching_tasks": [
        item(1, "Заказать перчатки S", ItemType.TASK),
        item(3, "Заказать перчатки M", ItemType.TASK),
    ],
    "gloves_and_technician": [
        item(1, "Заказать перчатки S", ItemType.TASK),
        item(2, "Техник — автоклав", ItemType.WAITING, "2026-09-05", "техник"),
    ],
}


def assess(case: dict, extraction: object) -> list[str]:
    errors: list[str] = []
    operations = extraction.operations
    if extraction.needs_clarification != case.get("clarify", False):
        errors.append("clarification")
    if len(operations) != case["count"]:
        errors.append(f"count={len(operations)}")
    kinds = [operation.kind.value for operation in operations]
    if kinds != case["kinds"]:
        errors.append(f"kinds={kinds}")
    types = [operation.item.type.value for operation in operations if operation.item]
    if types != case["types"]:
        errors.append(f"types={types}")
    due = [
        operation.item.due_at if operation.item else operation.due_at
        for operation in operations
        if operation.item or operation.kind.value == "reschedule"
    ]
    if due != case["due"]:
        errors.append(f"due={due}")
    if case.get("category"):
        categories = [operation.item.category.value for operation in operations if operation.item]
        if categories != [case["category"]]:
            errors.append(f"category={categories}")
    if case.get("target_ids"):
        target_ids = [operation.target_item_id for operation in operations]
        if target_ids != case["target_ids"]:
            errors.append(f"target_ids={target_ids}")
    text = extraction.model_dump_json().lower()
    for forbidden in case.get("forbidden", []):
        if forbidden.lower() in text:
            errors.append(f"invented={forbidden}")
    return errors


async def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument(
        "--ids",
        help="comma-separated case IDs; omitted means all 40",
    )
    args = argument_parser.parse_args()
    selected_ids = (
        {int(value) for value in args.ids.split(",") if value.strip()} if args.ids else None
    )
    selected_cases = [case for case in CORPUS if selected_ids is None or case["id"] in selected_ids]
    if selected_ids is not None and len(selected_cases) != len(selected_ids):
        known = {case["id"] for case in selected_cases}
        missing = sorted(selected_ids - known)
        print(f"Unknown case IDs: {missing}")
        return 2
    for case in selected_cases:
        context_name = case.get("context")
        if context_name and context_name not in CONTEXTS:
            print(f"Case {case['id']:02d} references unknown context: {context_name}")
            return 2
        expected_targets = set(case.get("target_ids", []))
        context_targets = {item.id for item in CONTEXTS.get(context_name, [])}
        if not expected_targets <= context_targets:
            missing_targets = sorted(expected_targets - context_targets)
            print(f"Case {case['id']:02d} context lacks target IDs: {missing_targets}")
            return 2
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is required; no API calls were made.")
        return 2
    model = os.getenv("OPENAI_TEXT_MODEL", "gpt-5-mini")
    adapter = OpenAIAdapter(api_key, model, "gpt-4o-mini-transcribe")
    failures = 0
    for case in selected_cases:
        now = datetime.fromisoformat(case.get("now", "2026-09-05T12:00:00+03:00"))
        context = CONTEXTS.get(case.get("context"), [])
        try:
            extraction = await adapter.extract(case["text"], now, "Europe/Moscow", context)
        except OpenAIError as error:
            print(
                f"Provider error before case {case['id']:02d}: "
                f"{type(error).__name__}: {error}"
            )
            print("Evaluation stopped; remaining cases were not called.")
            return 3
        errors = assess(case, extraction)
        failures += bool(errors)
        print(f"{case['id']:02d} {'FAIL ' + ', '.join(errors) if errors else 'OK'}")
    passed = len(selected_cases) - failures
    print(
        f"\nResult: {passed}/{len(selected_cases)} passed "
        f"({passed / len(selected_cases):.1%})"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
