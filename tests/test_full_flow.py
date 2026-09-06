import tempfile
import unittest
from pathlib import Path

from tgwhisper.models import Category, ItemStatus, ItemType
from tgwhisper.repository import Repository
from tgwhisper.schemas import Extraction, ItemDraft, Operation
from tgwhisper.service import CaptureService


class QueueExtractor:
    def __init__(self, extractions: list[Extraction]) -> None:
        self.extractions = iter(extractions)
        self.context_sizes: list[int] = []

    async def extract(self, text, now_local, timezone, active_items):
        self.context_sizes.append(len(active_items))
        return next(self.extractions)


def create_item(item_type, title, category, due_at, waiting_for=None):
    return ItemDraft(
        type=item_type,
        title=title,
        description=None,
        status=ItemStatus.ACTIVE,
        category=category,
        due_at=due_at,
        waiting_for=waiting_for,
        source_text="Завтра заказать перчатки S и проверить техника по автоклаву",
    )


class FullMvpFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_surface_complete_and_reschedule_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Repository(Path(directory) / "flow.sqlite3")
            capture = Extraction(operations=[
                Operation(kind="create", item=create_item(
                    ItemType.TASK, "Заказать перчатки S", Category.MATERIALS, "2026-09-06"
                )),
                Operation(kind="create", item=create_item(
                    ItemType.WAITING, "Техник — автоклав", Category.EQUIPMENT,
                    "2026-09-06", "техник",
                )),
            ])
            extractor = QueueExtractor([capture])
            service = CaptureService(repository, extractor)

            draft_id, proposed = await service.propose(
                42, "Завтра заказать перчатки S и проверить техника по автоклаву"
            )
            self.assertEqual(2, len(proposed.operations))
            self.assertEqual([], repository.active_items(42), "preview must not persist items")

            created_ids = service.confirm(42, draft_id)
            self.assertEqual(2, len(created_ids))
            morning = repository.due_items(42, "2026-09-06")
            self.assertEqual(
                ["Заказать перчатки S", "Техник — автоклав"],
                [item.title for item in morning],
            )

            evening = Extraction(operations=[
                Operation(kind="complete", target_item_id=created_ids[0]),
                Operation(
                    kind="reschedule", target_item_id=created_ids[1],
                    due_at="2026-09-08",
                    comment="техник не приехал; сказал, что будет послезавтра",
                ),
            ])
            evening_extractor = QueueExtractor([evening])
            evening_service = CaptureService(repository, evening_extractor)
            update_draft, _ = await evening_service.propose(
                42, "Перчатки заказала, техник не приехал, сказал будет послезавтра"
            )
            self.assertEqual([2], evening_extractor.context_sizes)
            evening_service.confirm(42, update_draft)

            active = repository.active_items(42)
            self.assertEqual(1, len(active))
            self.assertEqual("Техник — автоклав", active[0].title)
            self.assertEqual("2026-09-08", active[0].due_at)
            with repository.connect() as db:
                event = db.execute(
                    "SELECT old_due_at, new_due_at, comment FROM item_events "
                    "WHERE item_id = ? AND event_type = 'reschedule'",
                    (created_ids[1],),
                ).fetchone()
            self.assertEqual("2026-09-06", event["old_due_at"])
            self.assertEqual("2026-09-08", event["new_due_at"])
            self.assertIn("не приехал", event["comment"])


if __name__ == "__main__":
    unittest.main()
