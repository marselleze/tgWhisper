import tempfile
import unittest
from pathlib import Path

from tgwhisper.repository import Repository
from tgwhisper.scheduler import _send_once


class FakeBot:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, user_id: int, text: str, **_: object) -> None:
        self.messages.append((user_id, text))
        if self.fail:
            raise RuntimeError("network unavailable")


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.temp.name) / "test.sqlite3")
        self.repo.ensure_user(42)

    def tearDown(self) -> None:
        self.temp.cleanup()

    async def test_successful_delivery_is_not_duplicated(self) -> None:
        bot = FakeBot()
        await _send_once(self.repo, bot, 42, "digest:today", "Доброе утро")
        await _send_once(self.repo, bot, 42, "digest:today", "Доброе утро")
        self.assertEqual([(42, "Доброе утро")], bot.messages)
        self.assertTrue(self.repo.was_delivered(42, "digest:today"))

    async def test_failed_delivery_remains_retryable(self) -> None:
        failed_bot = FakeBot(fail=True)
        await _send_once(self.repo, failed_bot, 42, "reminder:1", "Напоминание")
        self.assertFalse(self.repo.was_delivered(42, "reminder:1"))

        working_bot = FakeBot()
        await _send_once(self.repo, working_bot, 42, "reminder:1", "Напоминание")
        self.assertEqual([(42, "Напоминание")], working_bot.messages)
        self.assertTrue(self.repo.was_delivered(42, "reminder:1"))


if __name__ == "__main__":
    unittest.main()
