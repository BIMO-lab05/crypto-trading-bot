"""
Unit Tests for telegram_notifier.send_message — NOTIFICATION_TEST_MODE=record branch.

Fills Phase 2 / Plan 02-05 Nyquist gap (INFRA-01 / CD-01):
  - Plan 02-05 shipped only an integration test (`tests/integration/test_notification_delivery.py`)
    that requires a live Docker stack. The record-mode write path itself was never exercised
    in isolation.
  - This file pins the record-mode branch with a real-file behavioral test using `tmp_path`
    and asserts the live POST path is NEVER reached.

Per project memory `feedback_pathlib_mocking.md`: pathlib.Path.open / write_text bypass
builtins.open. We avoid the trap entirely by writing to a real `tmp_path` file and
reading it back with `Path.read_text()`.
"""

import json
from unittest.mock import patch

import pytest


class TestRecordModeBranch:
    """Verify that NOTIFICATION_TEST_MODE=record routes send_message to a JSON file write
    and skips the api.telegram.org POST entirely."""

    @pytest.mark.asyncio
    async def test_record_mode_writes_json_line_with_message_marker(self, tmp_path):
        """Record mode MUST write a JSON line containing the message text to the configured
        record_path. The file is read back and parsed — no mocking of pathlib involved."""
        record_file = tmp_path / ".notifications.log"
        unique_marker = "RECORD-MODE-MARKER-XYZ789"

        with patch("app.telegram_notifier.config") as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = "123456:ABC-DEF"
            mock_config.telegram_chat_id = "987654321"
            mock_config.notification_test_mode = "record"
            mock_config.notification_record_path = str(record_file)

            from app.telegram_notifier import TelegramNotifier

            notifier = TelegramNotifier()
            result = await notifier.send_message(
                f"Test alert containing {unique_marker} body"
            )

        assert result is True, (
            "record-mode send_message should return True on successful write"
        )
        assert record_file.exists(), f"record file was not created at {record_file}"

        # Read back via Path.read_text (matches project convention; sidesteps the
        # builtins.open mocking trap noted in feedback_pathlib_mocking.md).
        contents = record_file.read_text(encoding="utf-8")
        lines = [ln for ln in contents.splitlines() if ln.strip()]
        assert len(lines) == 1, (
            f"expected exactly 1 JSON line, got {len(lines)}: {contents!r}"
        )

        record = json.loads(lines[0])
        assert "text" in record, f"record missing 'text' key: {record!r}"
        assert unique_marker in record["text"], (
            f"record text {record['text']!r} did not contain marker {unique_marker!r}"
        )
        assert record["chat_id"] == "987654321", f"unexpected chat_id: {record!r}"
        assert "parse_mode" in record, f"record missing 'parse_mode' key: {record!r}"
        assert "timestamp" in record, f"record missing 'timestamp' key: {record!r}"

    @pytest.mark.asyncio
    async def test_record_mode_does_not_call_telegram_api(self, tmp_path):
        """Record mode MUST NOT instantiate httpx.AsyncClient nor POST to api.telegram.org.
        Catches a regression where record-mode falls through to the live branch (e.g. if
        the early `return True` on the record path is removed or the branch condition flips)."""
        record_file = tmp_path / ".notifications.log"

        with patch("app.telegram_notifier.config") as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = "123456:ABC-DEF"
            mock_config.telegram_chat_id = "987654321"
            mock_config.notification_test_mode = "record"
            mock_config.notification_record_path = str(record_file)

            with patch("app.telegram_notifier.httpx.AsyncClient") as mock_async_client:
                from app.telegram_notifier import TelegramNotifier

                notifier = TelegramNotifier()
                result = await notifier.send_message("any message")

                # Sanity: write succeeded.
                assert result is True
                assert record_file.exists()

                # Behavioral: the live HTTP path was never entered. AsyncClient is
                # instantiated as `httpx.AsyncClient()` in the live branch — calling
                # the patched class counts as "called" for assert_not_called().
                mock_async_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_record_mode_appends_multiple_calls_to_same_file(self, tmp_path):
        """Two send_message calls in record mode must produce two JSON lines (append, not overwrite).
        Confirms `open('a')` semantics — protects against a regression where someone changes 'a' to 'w'."""
        record_file = tmp_path / ".notifications.log"

        with patch("app.telegram_notifier.config") as mock_config:
            mock_config.telegram_enabled = True
            mock_config.telegram_bot_token = "123456:ABC-DEF"
            mock_config.telegram_chat_id = "987654321"
            mock_config.notification_test_mode = "record"
            mock_config.notification_record_path = str(record_file)

            from app.telegram_notifier import TelegramNotifier

            notifier = TelegramNotifier()
            assert await notifier.send_message("first message FIRST-MARKER") is True
            assert await notifier.send_message("second message SECOND-MARKER") is True

        contents = record_file.read_text(encoding="utf-8")
        lines = [ln for ln in contents.splitlines() if ln.strip()]
        assert len(lines) == 2, (
            f"expected 2 lines (append mode), got {len(lines)}: {contents!r}"
        )

        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert "FIRST-MARKER" in first["text"]
        assert "SECOND-MARKER" in second["text"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--no-cov"])
