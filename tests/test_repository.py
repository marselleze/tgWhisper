import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from tgwhisper.models import Category, ItemStatus, ItemType
from tgwhisper.repository import Repository
from tgwhisper.schemas import Extraction, ItemDraft, Operation, OperationKind


def draft(title: str = "Заказать перчатки", due_at: str | None = None) -> ItemDraft:
    return ItemDraft(
        type=ItemType.TASK,
        title=title,
        description=None,
        status=ItemStatus.ACTIVE if due_at else ItemStatus.INBOX,
        category=Category.MATERIALS,
        due_at=due_at,
        waiting_for=None,
        source_text=title,
    )


class RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.temp.name) / "test.sqlite3")
        self.user_id = 42

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_draft_does_not_mutate_until_confirmed(self) -> None:
        extraction = Extraction(operations=[Operation(kind="create", item=draft())])
        draft_id = self.repo.create_draft(self.user_id, extraction)
        self.assertEqual([], self.repo.active_items(self.user_id))
        ids = self.repo.confirm_draft(self.user_id, draft_id)
        self.assertEqual(1, len(ids))
        self.assertEqual("Заказать перчатки", self.repo.active_items(self.user_id)[0].title)

    def test_confirmation_is_single_use(self) -> None:
        extraction = Extraction(operations=[Operation(kind="create", item=draft())])
        draft_id = self.repo.create_draft(self.user_id, extraction)
        self.repo.confirm_draft(self.user_id, draft_id)
        with self.assertRaises(ValueError):
            self.repo.confirm_draft(self.user_id, draft_id)

    def test_cancelled_draft_saves_nothing(self) -> None:
        extraction = Extraction(operations=[Operation(kind="create", item=draft())])
        draft_id = self.repo.create_draft(self.user_id, extraction)
        self.repo.cancel_draft(self.user_id, draft_id)
        self.assertEqual([], self.repo.active_items(self.user_id))

    def test_completion_updates_existing_item(self) -> None:
        create = Extraction(operations=[Operation(kind="create", item=draft())])
        created_id = self.repo.confirm_draft(
            self.user_id, self.repo.create_draft(self.user_id, create)
        )[0]
        complete = Extraction(operations=[
            Operation(kind=OperationKind.COMPLETE, target_item_id=created_id)
        ])
        self.repo.confirm_draft(self.user_id, self.repo.create_draft(self.user_id, complete))
        self.assertEqual([], self.repo.active_items(self.user_id))

    def test_due_query_includes_overdue_and_today(self) -> None:
        extraction = Extraction(operations=[
            Operation(kind="create", item=draft("Вчера", "2026-09-04")),
            Operation(kind="create", item=draft("Сегодня", "2026-09-05")),
            Operation(kind="create", item=draft("Завтра", "2026-09-06")),
        ])
        self.repo.confirm_draft(self.user_id, self.repo.create_draft(self.user_id, extraction))
        due_titles = [x.title for x in self.repo.due_items(self.user_id, "2026-09-05")]
        self.assertEqual(["Вчера", "Сегодня"], due_titles)

    def test_delivery_claim_is_idempotent(self) -> None:
        self.repo.ensure_user(self.user_id)
        self.assertTrue(self.repo.claim_delivery(self.user_id, "digest:2026-09-05"))
        self.assertFalse(self.repo.claim_delivery(self.user_id, "digest:2026-09-05"))

    def test_delivery_is_recorded_only_when_explicitly_marked(self) -> None:
        self.repo.ensure_user(self.user_id)
        key = "reminder:1:2026-09-05T15:00:00+03:00"
        self.assertFalse(self.repo.was_delivered(self.user_id, key))
        self.repo.record_delivery(self.user_id, key)
        self.assertTrue(self.repo.was_delivered(self.user_id, key))

    def test_explicit_reminder_action_can_complete_item(self) -> None:
        create = Extraction(
            operations=[
                Operation(
                    kind="create", item=draft("Позвонить", "2026-09-05T15:00:00+03:00")
                )
            ]
        )
        item_id = self.repo.confirm_draft(
            self.user_id, self.repo.create_draft(self.user_id, create)
        )[0]
        self.repo.apply_confirmed_operation(
            self.user_id, Operation(kind="complete", target_item_id=item_id)
        )
        self.assertEqual([], self.repo.active_items(self.user_id))

    def test_explicit_reminder_action_can_reschedule_item(self) -> None:
        create = Extraction(
            operations=[
                Operation(
                    kind="create", item=draft("Позвонить", "2026-09-05T15:00:00+03:00")
                )
            ]
        )
        item_id = self.repo.confirm_draft(
            self.user_id, self.repo.create_draft(self.user_id, create)
        )[0]
        self.repo.apply_confirmed_operation(
            self.user_id,
            Operation(
                kind="reschedule",
                target_item_id=item_id,
                due_at="2026-09-05T16:00:00+03:00",
            ),
        )
        updated_due = self.repo.active_items(self.user_id)[0].due_at
        self.assertEqual("2026-09-05T16:00:00+03:00", updated_due)


class SchemaTests(unittest.TestCase):
    def test_clarification_cannot_mutate(self) -> None:
        with self.assertRaises(ValueError):
            Extraction(
                operations=[Operation(kind="create", item=draft())],
                needs_clarification=True,
                clarification_question="Что вы имели в виду?",
            )

    def test_reschedule_requires_date(self) -> None:
        with self.assertRaises(ValueError):
            Operation(kind="reschedule", target_item_id=1)

    def test_due_datetime_requires_timezone(self) -> None:
        with self.assertRaises(ValueError):
            draft("Позвонить", "2026-09-05T15:00:00")

    def test_due_date_must_be_real_iso_date(self) -> None:
        with self.assertRaises(ValueError):
            draft("Позвонить", "2026-02-31")

    def test_mutation_cannot_smuggle_new_item(self) -> None:
        with self.assertRaises(ValueError):
            Operation(kind="complete", target_item_id=1, item=draft())


if __name__ == "__main__":
    unittest.main()
