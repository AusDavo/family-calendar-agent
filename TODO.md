# Roadmap

Phase one (read-only calendar queries) is complete. What's next:

## Phase 2 — Daily life
- [x] Morning digest — scheduled summary of today's events sent to each user
- [ ] Proactive reminders — configurable alerts before events
- [ ] Multi-tool-call support — let Claude call the calendar tool multiple times per question

## Phase 3 — Create & manage events
- [x] Create events via chat — "Add dentist Thursday at 2pm"
- [ ] Move / reschedule events — "Move Friday's meeting to Monday"
- [ ] Cancel events — "Cancel tomorrow's lunch"
- [ ] Confirmation step before writes — bot confirms details before saving

## Phase 4 — Family coordination
- [ ] Family-wide free/busy — "Is anyone free Saturday afternoon?"
- [ ] Conflict detection — proactive alerts when family events overlap
- [ ] Per-person calendar views — each Telegram user sees their own calendar(s)
- [ ] Shared family calendar support — suggest the right calendar when creating events

## Phase 5 — Smart touches
- [ ] Birthday & anniversary reminders
- [ ] Weekly lookahead — Sunday evening preview of the week ahead
- [ ] Natural recurring events — "Add swimming every Tuesday at 4pm"
- [ ] Conversation memory within a chat session

## Infrastructure
- [ ] Persistent conversation context (session history)
- [ ] Graceful CalDAV error handling & retry
- [ ] Tests
