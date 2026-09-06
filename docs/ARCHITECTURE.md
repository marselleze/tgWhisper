# Architecture and operating model

## Components

```text
Telegram text ─────────────────────────┐
Telegram voice → OpenAI transcription ├→ structured extraction → draft preview
                                      │                           │
SQLite active items ─→ match context ─┘                  user confirmation
                                                                  │
                                                                  ▼
                                                            SQLite transaction
                                                                  │
                                      APScheduler ← due items/users
                                           │
                                           ├→ morning digest
                                           └→ reminder → done / +1 hour
```

The Telegram process is the application boundary. FastAPI is deliberately omitted:
the MVP has no web client or external API, so a second server would add operational
cost without enabling a required scenario.

## Modules

| Module | Responsibility |
|---|---|
| `bot.py` | Telegram commands, text/voice capture, callbacks, previews |
| `ai.py` | Speech-to-text and schema-constrained extraction |
| `schemas.py` | Strict draft and operation contract |
| `service.py` | Capture orchestration and confirmation boundary |
| `repository.py` | SQLite schema, transactions, active context, event history |
| `scheduler.py` | Idempotent digest/reminder delivery |
| `presentation.py` | User-facing preview and digest text |

## State transitions

```text
capture → draft → confirmed → inbox/active → done
                  └─────────→ cancelled
draft   → cancelled (nothing written to items)
active waiting/reminder → rescheduled (event history retained)
```

LLM output cannot directly mutate an item. It is stored as a draft and applied only
after explicit confirmation. Reminder buttons are already explicit user actions and
therefore apply their single operation directly.

## Reliability

- Draft confirmation is transactional and single-use.
- Foreign keys and enum checks are enforced in SQLite.
- Morning digest and reminder delivery keys are idempotent.
- A delivery is recorded only after Telegram accepts it. A failed call is retried on
  the next scheduler tick, preferring a possible duplicate after a process crash over
  silently losing a reminder.
- Reschedules retain old/new deadlines and comments in `item_events`.
- User-facing service failures do not write partial items.

## Privacy boundary

Raw voice is held in memory only. It is sent to OpenAI for transcription and then
discarded. The transcript and structured item are stored locally in SQLite. The MVP
does not log user text, send data to analytics, or integrate with clinical systems.

## Deployment

One long-running Python process is sufficient for the MVP. Its writable `data/`
directory must be persisted and backed up. Only one scheduler instance should run
against a database. Configuration is loaded from environment variables or `.env`;
credentials are never committed.
