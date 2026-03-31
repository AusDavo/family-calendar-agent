# Family Calendar Agent

A Telegram bot backed by an LLM that answers natural language questions about your calendar. Reads events via CalDAV. Designed for incremental enhancement.

## Phase 1 — Read-Only Calendar + Telegram Bot

### What It Does

A Telegram bot you can message with questions like:
- "What's on my calendar tomorrow?"
- "Am I free Thursday afternoon?"
- "What does next week look like?"
- "Any clashes on Wednesday?"

The bot reads your calendar via CalDAV, passes the relevant events to an LLM with the question, and returns a natural language answer.

### Architecture

```
User ──Telegram──▶ Bot (python-telegram-bot)
                       │
                       ├──▶ CalDAV server (read-only, app password auth)
                       │       └── Fetches events for relevant date range
                       │
                       └──▶ Claude API (Anthropic SDK)
                               └── Interprets question + calendar data → answer
```

Single Python service. No database. No persistent state beyond the Telegram session.

### Stack

- **Python 3.13** — matches existing infrastructure
- **python-telegram-bot** — async Telegram Bot API wrapper
- **caldav** — CalDAV client library (RFC 4791)
- **anthropic** — Claude API for natural language understanding
- **Docker Compose** — deployment, same pattern as other services
- **Caddy** — reverse proxy (only needed if adding a webhook endpoint later; Telegram polling needs no inbound port)

### CalDAV Integration

CalDAV is the standard protocol for calendar access. Works with Fastmail, Google (via gateway), Nextcloud, Radicale, etc.

**Connection requires:**
- CalDAV server URL (provider-specific, e.g. `https://caldav.fastmail.com/dav/calendars/user/{email}/`)
- Username (usually email)
- App-specific password (not the account password)

**Operations (Phase 1, read-only):**
- List calendars
- Fetch events in a date range
- Parse iCalendar (`.ics`) data — recurring events, all-day events, timezones

**Key considerations:**
- Recurring events (RRULE) need expansion — the `caldav` library handles this via `expand` parameter on date range queries
- Timezone handling — store and display in the user's local timezone
- All-day events vs timed events — different display formatting

### Telegram Bot

**Polling mode** (Phase 1) — no webhook, no inbound port needed. The bot polls Telegram's servers for updates. Simpler to deploy and debug.

**Commands:**
- `/start` — welcome message
- `/today` — shortcut for today's events
- `/week` — shortcut for this week's overview
- Any other message — interpreted as a natural language question

**Access control:**
- Restrict to a whitelist of Telegram user IDs (environment variable)
- Reject messages from unknown users silently

### LLM Integration

Each question goes to Claude with:
1. The user's question
2. Calendar events for the relevant date range (determined heuristically — if the question mentions "next week", fetch next 7 days)
3. Current date/time in the user's timezone
4. System prompt instructing concise, direct answers

**Date range heuristic:**
- Default: today + next 7 days
- "Tomorrow" → tomorrow only
- "Next week" → Monday–Sunday of next week
- "This month" → rest of current month
- Specific date mentioned → that day ± 1 day for context

### Configuration

All via environment variables (no personal info in code):

```env
# Telegram
TELEGRAM_BOT_TOKEN=           # from @BotFather
TELEGRAM_ALLOWED_USERS=       # comma-separated Telegram user IDs

# CalDAV
CALDAV_URL=                   # CalDAV server URL
CALDAV_USERNAME=              # email / username
CALDAV_PASSWORD=              # app-specific password
CALENDAR_NAMES=               # comma-separated calendar names to monitor (optional, default: all)

# LLM
ANTHROPIC_API_KEY=            # Claude API key

# General
TIMEZONE=Australia/Brisbane   # display timezone
```

### Deployment

Same Docker Compose pattern as other services on the home server:

```yaml
services:
  bot:
    build: .
    container_name: family-calendar-agent
    restart: unless-stopped
    environment:
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      TELEGRAM_ALLOWED_USERS: ${TELEGRAM_ALLOWED_USERS}
      CALDAV_URL: ${CALDAV_URL}
      CALDAV_USERNAME: ${CALDAV_USERNAME}
      CALDAV_PASSWORD: ${CALDAV_PASSWORD}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      TIMEZONE: ${TIMEZONE:-Australia/Brisbane}
```

No Caddy/reverse proxy needed for Phase 1 (polling mode, no inbound connections). Just Docker on the server.

### File Structure

```
family-calendar-agent/
├── bot.py              # Telegram bot + message handling
├── calendar.py         # CalDAV client wrapper
├── llm.py              # Claude API integration
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE
├── PLAN.md
└── README.md           # Setup and usage instructions
```

### Verification

1. Bot responds to `/start` with a welcome message
2. Bot responds to `/today` with today's calendar events
3. Bot responds to "Am I free Thursday afternoon?" with a correct answer
4. Bot ignores messages from non-whitelisted users
5. Recurring events are expanded correctly
6. Timezone handling is correct (events display in local time)

---

## Phase 2 — Second Calendar + Memory

- Add a second calendar provider (Google Calendar API, OAuth2)
- Deploy a dedicated memory MCP instance for family context (meal plans, preferences, recurring commitments not in any calendar)
- Cross-calendar conflict detection
- "What are *we* doing this weekend?" queries across both calendars

## Phase 3 — Write Capability + Digest

- Create/move/cancel events on both calendars via the bot
- Daily or weekly digest message summarizing upcoming events
- Confirmation flow for write operations ("Create 'Dentist' on Thursday 2pm? Yes/No")
- Add family members to the Telegram bot (group or individual chats)
