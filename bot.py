import asyncio
import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from calendar_client import get_events, create_event, delete_event, CalendarError
from llm import answer_question, summarize_events, digest_summary, LLMError

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "Australia/Brisbane"))
ALLOWED_USERS: set[int] = set()


class _AllowedUsersFilter(filters.MessageFilter):
    def filter(self, message) -> bool:
        return message.from_user is not None and message.from_user.id in ALLOWED_USERS


allowed_filter = _AllowedUsersFilter()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! I'm your calendar assistant. Ask me anything about your schedule, "
        "or use /today or /week for quick summaries."
    )


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.chat.send_action("typing")
    try:
        now = datetime.now(TIMEZONE)
        today_str = now.strftime("%Y-%m-%d")
        events = await asyncio.to_thread(get_events, today_str, today_str)
        reply = await summarize_events(events, "today's events")
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
    except (CalendarError, LLMError) as e:
        logger.error("Error in /today: %s", e)
        await update.message.reply_text(
            "Sorry, I had trouble checking your calendar. Please try again."
        )


async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.chat.send_action("typing")
    try:
        now = datetime.now(TIMEZONE)
        monday = now - timedelta(days=now.weekday())
        sunday = monday + timedelta(days=6)
        events = await asyncio.to_thread(
            get_events, monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")
        )
        reply = await summarize_events(events, "this week's events")
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
    except (CalendarError, LLMError) as e:
        logger.error("Error in /week: %s", e)
        await update.message.reply_text(
            "Sorry, I had trouble checking your calendar. Please try again."
        )


async def send_digest(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the morning digest to a user."""
    chat_id = context.job.chat_id
    try:
        now = datetime.now(TIMEZONE)
        today_str = now.strftime("%Y-%m-%d")

        # Rest of week: tomorrow through Sunday
        tomorrow = now + timedelta(days=1)
        days_until_sunday = 6 - now.weekday()
        if days_until_sunday <= 0:
            days_until_sunday += 7
        sunday = now + timedelta(days=days_until_sunday)

        today_events = await asyncio.to_thread(get_events, today_str, today_str)
        week_events = await asyncio.to_thread(
            get_events, tomorrow.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")
        )

        reply = await digest_summary(today_events, week_events)
        await context.bot.send_message(
            chat_id=chat_id, text=reply, parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error("Error sending digest to %s: %s", chat_id, e)


def _format_pending(pending: dict) -> str:
    """Format a pending action into a confirmation message."""
    action = pending.get("action", "create")

    if action == "delete":
        lines = [
            f"Delete *{pending['summary']}*",
            f"Date: {pending['start_date']}",
            f"Calendar: {pending['calendar_name']}",
            "\nReply *yes* to confirm or *no* to cancel.",
        ]
        return "\n".join(lines)

    if action == "move":
        old = pending["delete"]
        new = pending["create"]
        new_start = datetime.fromisoformat(new["start_datetime"])
        new_end = datetime.fromisoformat(new["end_datetime"])
        if new.get("all_day"):
            new_time = f"All day ({new_start.strftime('%A, %b %-d')})"
        elif new_start.date() == new_end.date():
            new_time = f"{new_start.strftime('%A, %b %-d')} · {new_start.strftime('%-I:%M %p')} – {new_end.strftime('%-I:%M %p')}"
        else:
            new_time = f"{new_start.strftime('%a %b %-d %-I:%M %p')} – {new_end.strftime('%a %b %-d %-I:%M %p')}"
        lines = [
            f"Move *{old['summary']}*",
            f"From: {old['start_date']}",
            f"To: {new_time}",
            f"Calendar: {new['calendar_name']}",
        ]
        if new.get("location"):
            lines.append(f"Location: {new['location']}")
        lines.append("\nReply *yes* to confirm or *no* to cancel.")
        return "\n".join(lines)

    # Create action
    start = datetime.fromisoformat(pending["start_datetime"])
    end = datetime.fromisoformat(pending["end_datetime"])

    if pending["all_day"]:
        time_str = "All day"
        if start.date() != end.date():
            time_str += f" ({start.strftime('%a %b %-d')} – {end.strftime('%a %b %-d')})"
        else:
            time_str += f" ({start.strftime('%A, %b %-d')})"
    else:
        if start.date() == end.date():
            time_str = f"{start.strftime('%A, %b %-d')} · {start.strftime('%-I:%M %p')} – {end.strftime('%-I:%M %p')}"
        else:
            time_str = f"{start.strftime('%a %b %-d %-I:%M %p')} – {end.strftime('%a %b %-d %-I:%M %p')}"

    lines = [
        f"*{pending['summary']}*",
        time_str,
        f"Calendar: {pending['calendar_name']}",
    ]
    if pending.get("location"):
        lines.append(f"Location: {pending['location']}")
    if pending.get("description"):
        lines.append(f"Note: {pending['description']}")

    lines.append("\nReply *yes* to confirm or *no* to cancel.")
    return "\n".join(lines)


_CONFIRM_WORDS = {"yes", "yep", "y", "confirm", "ok", "sure", "do it", "go ahead"}
_CANCEL_WORDS = {"no", "nope", "n", "cancel", "nevermind", "never mind", "nah"}


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.chat.send_action("typing")
    text = update.message.text.strip()
    text_lower = text.lower()

    # Check for pending action confirmation
    pending = context.user_data.get("pending_event")
    if pending:
        if text_lower in _CONFIRM_WORDS:
            action = pending.get("action", "create")
            try:
                if action == "move":
                    old = pending["delete"]
                    new = pending["create"]
                    # Delete the old event
                    deleted = await asyncio.to_thread(
                        delete_event,
                        calendar_name=old["calendar_name"],
                        summary=old["summary"],
                        start_date=old["start_date"],
                    )
                    if not deleted:
                        del context.user_data["pending_event"]
                        await update.message.reply_text(
                            f"Couldn't find *{old['summary']}* to move. It may have already been removed.",
                            parse_mode=ParseMode.MARKDOWN,
                        )
                        return
                    # Create the new event
                    start = datetime.fromisoformat(new["start_datetime"])
                    end = datetime.fromisoformat(new["end_datetime"])
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=TIMEZONE)
                    if end.tzinfo is None:
                        end = end.replace(tzinfo=TIMEZONE)
                    await asyncio.to_thread(
                        create_event,
                        calendar_name=new["calendar_name"],
                        summary=new["summary"],
                        start=start,
                        end=end,
                        all_day=new.get("all_day", False),
                        location=new.get("location"),
                        description=new.get("description"),
                    )
                    del context.user_data["pending_event"]
                    await update.message.reply_text(
                        f"Done! *{new['summary']}* moved to its new time.",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    return

                elif action == "delete":
                    deleted = await asyncio.to_thread(
                        delete_event,
                        calendar_name=pending["calendar_name"],
                        summary=pending["summary"],
                        start_date=pending["start_date"],
                    )
                    del context.user_data["pending_event"]
                    if deleted:
                        await update.message.reply_text(
                            f"Done! *{pending['summary']}* has been deleted.",
                            parse_mode=ParseMode.MARKDOWN,
                        )
                    else:
                        await update.message.reply_text(
                            f"Couldn't find *{pending['summary']}* to delete. It may have already been removed.",
                            parse_mode=ParseMode.MARKDOWN,
                        )
                    return

                else:  # create
                    start = datetime.fromisoformat(pending["start_datetime"])
                    end = datetime.fromisoformat(pending["end_datetime"])
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=TIMEZONE)
                    if end.tzinfo is None:
                        end = end.replace(tzinfo=TIMEZONE)

                    await asyncio.to_thread(
                        create_event,
                        calendar_name=pending["calendar_name"],
                        summary=pending["summary"],
                        start=start,
                        end=end,
                        all_day=pending["all_day"],
                        location=pending.get("location"),
                        description=pending.get("description"),
                    )
                    del context.user_data["pending_event"]
                    await update.message.reply_text(
                        f"Done! *{pending['summary']}* added to {pending['calendar_name']}.",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    return

            except CalendarError as e:
                logger.error("Error executing %s: %s", action, e)
                del context.user_data["pending_event"]
                await update.message.reply_text(
                    f"Sorry, I couldn't {action} that event. Please try again."
                )
                return

        elif text_lower in _CANCEL_WORDS:
            del context.user_data["pending_event"]
            await update.message.reply_text("Cancelled.")
            return

        else:
            # New message clears pending event and processes normally
            del context.user_data["pending_event"]

    try:
        # Maintain conversation history for context
        history = context.user_data.setdefault("history", [])
        reply = await answer_question(text, history=history)

        if isinstance(reply, dict):
            # Pending event creation — ask for confirmation
            context.user_data["pending_event"] = reply
            confirmation = _format_pending(reply)
            # Add exchange to history
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": confirmation})
            await update.message.reply_text(confirmation, parse_mode=ParseMode.MARKDOWN)
            return

        # Add exchange to history
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply})
        # Keep last 20 turns (10 exchanges) to avoid token bloat
        if len(history) > 20:
            context.user_data["history"] = history[-20:]

        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
    except (CalendarError, LLMError) as e:
        logger.error("Error handling message: %s", e)
        await update.message.reply_text(
            "Sorry, I had trouble answering that. Please try again."
        )


def main() -> None:
    global ALLOWED_USERS

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    allowed = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
    for uid in allowed.split(","):
        uid = uid.strip()
        if not uid:
            continue
        if not uid.isdigit():
            raise ValueError(
                f"TELEGRAM_ALLOWED_USERS must be numeric user IDs, got '{uid}'. "
                "Message @userinfobot on Telegram to find your ID."
            )
    ALLOWED_USERS = {int(uid.strip()) for uid in allowed.split(",") if uid.strip()}

    if not ALLOWED_USERS:
        logger.warning("No allowed users configured — bot will reject all messages")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command, filters=allowed_filter))
    app.add_handler(CommandHandler("today", today_command, filters=allowed_filter))
    app.add_handler(CommandHandler("week", week_command, filters=allowed_filter))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & allowed_filter, handle_message
        )
    )

    # Schedule morning digest for each allowed user
    from datetime import time as dt_time
    digest_dt = dt_time(hour=6, minute=0, tzinfo=TIMEZONE)
    for uid in ALLOWED_USERS:
        app.job_queue.run_daily(
            send_digest, time=digest_dt, chat_id=uid, name=f"digest_{uid}"
        )
    logger.info(
        "Morning digest scheduled at %s for %d user(s)", digest_dt, len(ALLOWED_USERS)
    )

    logger.info("Bot starting in polling mode...")
    app.run_polling()


if __name__ == "__main__":
    main()
