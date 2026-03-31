import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from anthropic import AsyncAnthropic

from calendar_client import get_events, format_events_for_llm, CalendarEvent

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "Australia/Brisbane"))

client = AsyncAnthropic()

MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are a helpful family calendar assistant. You answer questions about the user's calendar events.

Rules:
- Be concise and direct. No preamble.
- Use the user's timezone ({timezone}) for all dates and times.
- Today is {today}.
- When you need calendar data, call the get_calendar_events tool with appropriate start and end dates.
- For questions about "today", fetch just today. For "this week", fetch Monday through Sunday of the current week. For "next week", fetch the following Monday through Sunday. For "this month", fetch the rest of the current month. Default to the next 7 days if unclear.
- Format times in 12-hour format (e.g., 2:30 PM).
- If there are no events, say so clearly.
- If asked about free/busy time, analyze gaps between events.
"""

CALENDAR_TOOL = {
    "name": "get_calendar_events",
    "description": "Fetch calendar events in a date range. Use this to answer questions about the user's schedule.",
    "input_schema": {
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format",
            },
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format (inclusive)",
            },
        },
        "required": ["start_date", "end_date"],
    },
}


class LLMError(Exception):
    pass


def _build_system_prompt() -> str:
    now = datetime.now(TIMEZONE)
    return SYSTEM_PROMPT.format(
        timezone=str(TIMEZONE),
        today=now.strftime("%A, %B %d, %Y at %I:%M %p"),
    )


def _extract_text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text")


async def answer_question(question: str) -> str:
    """Send a calendar question to Claude with tool-use flow.

    1. Send question with get_calendar_events tool available
    2. Claude calls the tool with a date range
    3. Fetch events, send back as tool result
    4. Claude produces final answer
    """
    try:
        system = _build_system_prompt()
        messages = [{"role": "user", "content": question}]

        response = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            tools=[CALENDAR_TOOL],
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            tool_block = next(b for b in response.content if b.type == "tool_use")
            start_date = tool_block.input["start_date"]
            end_date = tool_block.input["end_date"]

            import asyncio

            events = await asyncio.to_thread(get_events, start_date, end_date)
            events_text = format_events_for_llm(events)

            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": events_text
                            if events_text
                            else "No events found in this date range.",
                        }
                    ],
                }
            )

            final = await client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=system,
                tools=[CALENDAR_TOOL],
                messages=messages,
            )

            return _extract_text(final)

        return _extract_text(response)

    except Exception as e:
        raise LLMError(f"Failed to get answer from LLM: {e}") from e


async def summarize_events(events: list[CalendarEvent], context: str) -> str:
    """Summarize pre-fetched events. Single API call, no tool use."""
    try:
        system = _build_system_prompt()
        events_text = format_events_for_llm(events)

        if not events_text:
            content = f"No events found for {context}."
        else:
            content = f"Here are {context}:\n\n{events_text}\n\nPlease summarize these events concisely."

        response = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": content}],
        )

        return _extract_text(response)

    except Exception as e:
        raise LLMError(f"Failed to summarize events: {e}") from e
