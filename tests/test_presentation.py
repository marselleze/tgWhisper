import unittest

from tgwhisper.models import Category, ItemStatus, ItemType
from tgwhisper.presentation import format_due_at, render_preview
from tgwhisper.schemas import Extraction, ItemDraft, Operation


class PresentationTests(unittest.TestCase):
    def test_formats_due_datetime_for_user(self) -> None:
        self.assertEqual(
            "07.09.2026 в 11:00",
            format_due_at("2026-09-07T11:00:00+03:00"),
        )

    def test_formats_date_without_time(self) -> None:
        self.assertEqual("07.09.2026", format_due_at("2026-09-07"))

    def test_preview_does_not_expose_iso_datetime(self) -> None:
        item = ItemDraft(
            type=ItemType.REMINDER,
            title="Позвонить поставщику",
            description=None,
            status=ItemStatus.ACTIVE,
            category=Category.OTHER,
            due_at="2026-09-07T11:00:00+03:00",
            waiting_for=None,
            source_text="В 11 часов напомни позвонить поставщику",
        )

        preview = render_preview(
            Extraction(operations=[Operation(kind="create", item=item)])
        )

        self.assertIn("Срок: 07.09.2026 в 11:00", preview)
        self.assertNotIn("2026-09-07T11:00:00+03:00", preview)


if __name__ == "__main__":
    unittest.main()
