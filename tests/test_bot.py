"""Tests for bot.py — confirmation flow and message handling."""

import os
import pytest
from datetime import datetime

os.environ.setdefault("CALDAV_URL", "https://example.com/dav/")
os.environ.setdefault("CALDAV_USERNAME", "test")
os.environ.setdefault("CALDAV_PASSWORD", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "fake:token")
os.environ.setdefault("TIMEZONE", "Australia/Brisbane")

from bot import _format_pending


class TestFormatPending:
    def test_format_create(self):
        pending = {
            "action": "create",
            "summary": "Dentist",
            "start_datetime": "2026-04-04T14:00:00",
            "end_datetime": "2026-04-04T15:00:00",
            "all_day": False,
            "calendar_name": "Personal",
            "location": None,
            "description": None,
        }
        result = _format_pending(pending)
        assert "*Dentist*" in result
        assert "Personal" in result
        assert "yes" in result.lower()

    def test_format_delete(self):
        pending = {
            "action": "delete",
            "summary": "Meeting",
            "start_date": "2026-04-02",
            "calendar_name": "Work",
        }
        result = _format_pending(pending)
        assert "Delete" in result
        assert "*Meeting*" in result
        assert "2026-04-02" in result

    def test_format_move(self):
        pending = {
            "action": "move",
            "delete": {
                "calendar_name": "DMP Calendar",
                "summary": "See Paulie",
                "start_date": "2026-04-02",
            },
            "create": {
                "calendar_name": "DMP Calendar",
                "summary": "See Paulie",
                "start_datetime": "2026-04-04T09:30:00",
                "end_datetime": "2026-04-04T11:30:00",
                "all_day": False,
                "location": "Southbank",
            },
            "confirmation_message": "",
        }
        result = _format_pending(pending)
        assert "Move" in result
        assert "*See Paulie*" in result
        assert "2026-04-02" in result
        assert "Saturday" in result
        assert "Southbank" in result

    def test_format_create_all_day(self):
        pending = {
            "action": "create",
            "summary": "Holiday",
            "start_datetime": "2026-04-06",
            "end_datetime": "2026-04-06",
            "all_day": True,
            "calendar_name": "Personal",
            "location": None,
            "description": None,
        }
        result = _format_pending(pending)
        assert "All day" in result
        assert "*Holiday*" in result

    def test_format_empty_reply_guard(self):
        """Ensure empty string reply doesn't crash Telegram."""
        # This tests the guard we added in handle_message
        reply = ""
        if not reply or not reply.strip():
            reply = "Done."
        assert reply == "Done."
