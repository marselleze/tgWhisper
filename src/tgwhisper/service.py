from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .ai import Extractor
from .repository import Repository
from .schemas import Extraction


class CaptureService:
    def __init__(self, repository: Repository, extractor: Extractor) -> None:
        self.repository = repository
        self.extractor = extractor

    async def propose(self, user_id: int, text: str) -> tuple[int | None, Extraction]:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("message is empty")
        settings = self.repository.user_settings(user_id)
        timezone = settings["timezone"]
        extraction = await self.extractor.extract(
            clean_text,
            datetime.now(ZoneInfo(timezone)),
            timezone,
            self.repository.active_items(user_id),
        )
        if extraction.needs_clarification:
            return None, extraction
        if not extraction.operations:
            raise ValueError("message produced no operations")
        return self.repository.create_draft(user_id, extraction), extraction

    def confirm(self, user_id: int, draft_id: int) -> list[int]:
        return self.repository.confirm_draft(user_id, draft_id)

    def cancel(self, user_id: int, draft_id: int) -> None:
        self.repository.cancel_draft(user_id, draft_id)

