from __future__ import annotations

import json
from datetime import datetime
from typing import Protocol

from openai import AsyncOpenAI

from .models import Item
from .schemas import Extraction

SYSTEM_PROMPT = """You extract work items for a head nurse from Russian text.

Hard rule: never add information the user did not state. Missing is better than
invented. Do not silently choose among matching active items. Split independent
actions into independent operations.

Classify by meaning, not merely by tense or a date:
- task: an action for the user/team. An underspecified but actionable phrase such as
  "надо как-нибудь решить вопрос с поставщиком" is still a task with no due_at; keep
  the broad action and do not invent a call, meeting, person, date, or time.
- waiting: a promised/expected action by another person or control of whether that
  event happened. "Техник будет во вторник" and "проверить, приехал ли техник" are
  waiting items, not reminders.
- note: operational information with no requested action, even if it contains a
  future effective date. "С октября новый график" and a device serial number are
  notes. Preserve the date in the title/description, but keep due_at null because it
  is not a deadline.
- reminder: only an explicit request to remind/notify the user and only when the
  reminder has actual content. "Напомни в 15 часов" has no content, so ask what to
  remind about; never create a content-free reminder.

Dates: resolve explicit relative dates using now_local. Keep due_at null when no
deadline was said. A date without a stated exact time is YYYY-MM-DD. A vague part of
day such as "утром" may remain date-only and be surfaced in the daily digest; never
invent an exact hour. New tasks, waiting items, and reminders with a due date use
status=active; without one they use status=inbox.

Updates: do not treat a completion statement as a new task. For completion,
reschedule, or cancellation, set target_item_id only when exactly one active item is
an unambiguous semantic match; otherwise request clarification and return no
operations.

Categories follow the subject, not the document form: gloves, masks, shoe covers,
indicators, and consumables are materials; autoclaves and devices are equipment;
staff schedules/timesheets are staff; forms and general journals are documents;
cleaning, disinfection, and sanitary-regime schedules/journals are sanitary. Use
other only when evidence is insufficient."""


class Extractor(Protocol):
    async def extract(
        self, text: str, now_local: datetime, timezone: str, active_items: list[Item]
    ) -> Extraction: ...


class OpenAIAdapter:
    def __init__(
        self, api_key: str, text_model: str, transcription_model: str
    ) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.text_model = text_model
        self.transcription_model = transcription_model

    async def transcribe(self, filename: str, content: bytes) -> str:
        result = await self.client.audio.transcriptions.create(
            model=self.transcription_model,
            file=(filename, content),
            response_format="text",
            language="ru",
            prompt=(
                "Рабочая запись старшей медсестры. Возможные термины: автоклав, "
                "стерилизация, индикаторы, расходники, перчатки, бахилы."
            ),
        )
        text = result if isinstance(result, str) else result.text
        return text.strip()

    async def extract(
        self, text: str, now_local: datetime, timezone: str, active_items: list[Item]
    ) -> Extraction:
        context = [
            {
                "id": item.id, "type": item.type, "title": item.title,
                "due_at": item.due_at, "waiting_for": item.waiting_for,
            }
            for item in active_items
        ]
        response = await self.client.responses.parse(
            model=self.text_model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"now_local={now_local.isoformat()}\n"
                    f"timezone={timezone}\n"
                    f"active_items={json.dumps(context, ensure_ascii=False)}\n"
                    f"source_text={text}"
                )},
            ],
            text_format=Extraction,
        )
        if response.output_parsed is None:
            raise RuntimeError("model returned no structured extraction")
        return response.output_parsed
