import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from anthropic import AsyncAnthropic

from calendar_client import get_events, format_events_for_llm, get_calendar_names, CalendarEvent

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "Australia/Brisbane"))

client = AsyncAnthropic()

MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are a helpful family calendar assistant. You answer questions about the user's calendar events and can create new events.

Rules:
- Be concise and direct. No preamble.
- Use the user's timezone ({timezone}) for all dates and times.
- Today is {today}.
- When you need calendar data, call the get_calendar_events tool with appropriate start and end dates.
- For questions about "today", fetch just today. For "this week", fetch Monday through Sunday of the current week. For "next week", fetch the following Monday through Sunday. For "this month", fetch the rest of the current month. Default to the next 7 days if unclear.
- Format times in 12-hour format (e.g., 2:30 PM).
- If there are no events, say so clearly.
- If asked about free/busy time, analyze gaps between events.

Event creation rules:
- Available calendars: {calendars}
- When asked to create an event, pick the most appropriate calendar based on context.
- If no end time is given, default to 1 hour duration for timed events.
- For all-day events, set all_day to true and use date-only start/end.
- Always call the create_calendar_event tool — never just describe what you would create.
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

CREATE_EVENT_TOOL = {
    "name": "create_calendar_event",
    "description": "Create a new calendar event. Use this when the user asks to add, create, or schedule an event.",
    "input_schema": {
        "type": "object",
        "properties": {
            "calendar_name": {
                "type": "string",
                "description": "Name of the calendar to add the event to",
            },
            "summary": {
                "type": "string",
                "description": "Event title",
            },
            "start_datetime": {
                "type": "string",
                "description": "Start in ISO 8601 format (YYYY-MM-DDTHH:MM:SS for timed, YYYY-MM-DD for all-day)",
            },
            "end_datetime": {
                "type": "string",
                "description": "End in ISO 8601 format (YYYY-MM-DDTHH:MM:SS for timed, YYYY-MM-DD for all-day)",
            },
            "all_day": {
                "type": "boolean",
                "description": "Whether this is an all-day event",
            },
            "location": {
                "type": "string",
                "description": "Event location (optional)",
            },
            "description": {
                "type": "string",
                "description": "Event description (optional)",
            },
        },
        "required": ["calendar_name", "summary", "start_datetime", "end_datetime", "all_day"],
    },
}

TOOLS = [CALENDAR_TOOL, CREATE_EVENT_TOOL]


class LLMError(Exception):
    pass


def _build_system_prompt(calendar_names: list[str] | None = None) -> str:
    now = datetime.now(TIMEZONE)
    cal_str = ", ".join(calendar_names) if calendar_names else "(unknown)"
    return SYSTEM_PROMPT.format(
        timezone=str(TIMEZONE),
        today=now.strftime("%A, %B %d, %Y at %I:%M %p"),
        calendars=cal_str,
    )


def _extract_text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text")


async def answer_question(question: str) -> str | dict:
    """Send a calendar question to Claude with tool-use flow.

    Returns either:
        str — a text answer to display directly
        dict — a pending event creation needing user confirmation, with keys:
            calendar_name, summary, start_datetime, end_datetime, all_day,
            location (optional), description (optional), confirmation_message
    """
    try:
        import asyncio

        calendar_names = await asyncio.to_thread(get_calendar_names)
        system = _build_system_prompt(calendar_names)
        messages = [{"role": "user", "content": question}]

        # Tool-use loop: keep going until we get a text response or a create request
        max_rounds = 5
        for _ in range(max_rounds):
            response = await client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=system,
                tools=TOOLS,
                messages=messages,
            )

            if response.stop_reason != "tool_use":
                return _extract_text(response)

            # Process all tool calls in this response
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                if block.name == "get_calendar_events":
                    events = await asyncio.to_thread(
                        get_events, block.input["start_date"], block.input["end_date"]
                    )
                    events_text = format_events_for_llm(events)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": events_text or "No events found in this date range.",
                    })

                elif block.name == "create_calendar_event":
                    # Don't execute — return as pending for confirmation
                    pending = {
                        "calendar_name": block.input["calendar_name"],
                        "summary": block.input["summary"],
                        "start_datetime": block.input["start_datetime"],
                        "end_datetime": block.input["end_datetime"],
                        "all_day": block.input["all_day"],
                        "location": block.input.get("location"),
                        "description": block.input.get("description"),
                    }
                    # Get Claude's confirmation message text from the response
                    text = _extract_text(response)
                    pending["confirmation_message"] = text
                    return pending

            messages.append({"role": "user", "content": tool_results})

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
