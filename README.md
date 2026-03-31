# Family Calendar Agent

A Telegram bot that answers natural language questions about your calendar. Reads events via CalDAV, uses Claude for natural language understanding.

**Examples:**
- "What's on my calendar tomorrow?"
- "Am I free Thursday afternoon?"
- "What does next week look like?"
- "Any clashes on Wednesday?"

## How It Works

```
User ──Telegram──▶ Bot (python-telegram-bot)
                       │
                       ├──▶ CalDAV server (read-only)
                       │       └── Fetches events for relevant date range
                       │
                       └──▶ Claude API (tool use)
                               └── Determines date range → reads events → answers
```

The bot uses Claude's tool-use capability to determine which dates to fetch from your calendar, then answers based on the actual events.

## Commands

- `/start` — Welcome message
- `/today` — Today's events
- `/week` — This week's overview
- Any other message — Natural language question about your schedule

## Setup

### 1. Create a Telegram Bot

Message [@BotFather](https://t.me/BotFather) on Telegram, use `/newbot`, and save the token.

### 2. Get Your Telegram User ID

Message [@userinfobot](https://t.me/userinfobot) to find your numeric user ID.

### 3. Get CalDAV Credentials

You need your CalDAV server URL and an app-specific password. For Fastmail:
- URL: `https://caldav.fastmail.com/dav/calendars/user/you@example.com/`
- Generate an app password at Settings → Privacy & Security → App Passwords

### 4. Configure

```bash
cp .env.example .env
```

Fill in `.env`:

```env
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_ALLOWED_USERS=123456789        # comma-separated user IDs
CALDAV_URL=https://caldav.fastmail.com/dav/calendars/user/you@example.com/
CALDAV_USERNAME=you@example.com
CALDAV_PASSWORD=your-app-password
ANTHROPIC_API_KEY=sk-ant-...
TIMEZONE=Australia/Brisbane
CALENDAR_NAMES=                          # optional: comma-separated, default: all
```

### 5. Run

```bash
docker compose up -d
```

Or without Docker:

```bash
pip install -r requirements.txt
python bot.py
```

## Access Control

Only Telegram user IDs listed in `TELEGRAM_ALLOWED_USERS` can interact with the bot. Messages from other users are silently ignored.

## Stack

- Python 3.13
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) — async Telegram API
- [caldav](https://github.com/python-caldav/caldav) — CalDAV client (RFC 4791)
- [anthropic](https://github.com/anthropics/anthropic-sdk-python) — Claude API
- Docker Compose for deployment
