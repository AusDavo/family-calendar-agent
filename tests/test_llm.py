"""Tests for llm.py — tool definitions, system prompt, and tool-use loop logic."""

import os
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

# Set required env vars before importing
os.environ.setdefault("CALDAV_URL", "https://example.com/dav/")
os.environ.setdefault("CALDAV_USERNAME", "test")
os.environ.setdefault("CALDAV_PASSWORD", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("TIMEZONE", "Australia/Brisbane")


class TestSystemPrompt:
    def test_contains_day_date_mapping(self):
        """System prompt must include explicit day-to-date mapping."""
        with patch("llm.get_calendar_names", return_value=["Personal"]):
            from llm import _build_system_prompt
            prompt = _build_system_prompt(["Personal"])

        # Should contain day = date mappings for this week
        assert "Monday =" in prompt
        assert "Tuesday =" in prompt
        assert "Saturday =" in prompt
        assert "Sunday =" in prompt
        # Should have both this week and next week
        assert "This week:" in prompt
        assert "Next week:" in prompt

    def test_date_mapping_is_correct(self):
        """The day-to-date mapping should be accurate for the current date."""
        from llm import _build_system_prompt, TIMEZONE
        from datetime import timedelta

        prompt = _build_system_prompt(["Personal"])
        now = datetime.now(TIMEZONE)

        # Find this Saturday's actual date
        days_until_saturday = (5 - now.weekday()) % 7
        saturday = now + timedelta(days=days_until_saturday)
        saturday_str = saturday.strftime("%B %-d")

        assert f"Saturday = {saturday_str}" in prompt

    def test_contains_memory_rules(self):
        """System prompt should instruct Claude on memory usage."""
        from llm import _build_system_prompt
        prompt = _build_system_prompt(["Personal"])
        assert "search_memory" in prompt
        assert "store_memory" in prompt

    def test_contains_move_rules(self):
        """System prompt should instruct Claude on move/delete flow."""
        from llm import _build_system_prompt
        prompt = _build_system_prompt(["Personal"])
        assert "delete_calendar_event" in prompt
        assert "MOVE" in prompt or "move" in prompt.lower()


class TestToolDefinitions:
    def test_all_tools_present(self):
        """TOOLS list should contain all expected tools."""
        from llm import TOOLS
        tool_names = {t["name"] for t in TOOLS}
        assert tool_names == {
            "get_calendar_events",
            "create_calendar_event",
            "delete_calendar_event",
            "store_memory",
            "search_memory",
        }

    def test_delete_tool_has_required_fields(self):
        """delete_calendar_event should require calendar_name, summary, start_date."""
        from llm import DELETE_EVENT_TOOL
        required = DELETE_EVENT_TOOL["input_schema"]["required"]
        assert "calendar_name" in required
        assert "summary" in required
        assert "start_date" in required


class TestAnswerQuestion:
    @pytest.mark.asyncio
    async def test_accepts_history(self):
        """answer_question should accept and use conversation history."""
        from llm import answer_question

        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(type="text", text="Hello!")]

        with patch("llm.client") as mock_client, \
             patch("llm.get_calendar_names", return_value=["Personal"]):
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            result = await answer_question(
                "What's on Saturday?",
                history=[
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "content": "Hello!"},
                ],
            )

        assert result == "Hello!"
        # Verify history was included in messages
        call_kwargs = mock_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 3  # 2 history + 1 new
        assert messages[0]["content"] == "Hi"
        assert messages[2]["content"] == "What's on Saturday?"

    @pytest.mark.asyncio
    async def test_move_returns_compound_pending(self):
        """When Claude calls both delete and create, return a move action."""
        from llm import answer_question

        # Simulate Claude calling both delete + create in one response
        delete_block = MagicMock()
        delete_block.type = "tool_use"
        delete_block.name = "delete_calendar_event"
        delete_block.id = "del-1"
        delete_block.input = {
            "calendar_name": "Personal",
            "summary": "Meeting",
            "start_date": "2026-04-02",
        }

        create_block = MagicMock()
        create_block.type = "tool_use"
        create_block.name = "create_calendar_event"
        create_block.id = "cre-1"
        create_block.input = {
            "calendar_name": "Personal",
            "summary": "Meeting",
            "start_datetime": "2026-04-04T09:30:00",
            "end_datetime": "2026-04-04T11:30:00",
            "all_day": False,
        }

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "I'll move that for you."

        mock_response = MagicMock()
        mock_response.stop_reason = "tool_use"
        mock_response.content = [text_block, delete_block, create_block]

        with patch("llm.client") as mock_client, \
             patch("llm.get_calendar_names", return_value=["Personal"]):
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            result = await answer_question("Move meeting to Saturday")

        assert isinstance(result, dict)
        assert result["action"] == "move"
        assert result["delete"]["summary"] == "Meeting"
        assert result["delete"]["start_date"] == "2026-04-02"
        assert result["create"]["start_datetime"] == "2026-04-04T09:30:00"
