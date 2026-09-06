# AI extraction contract

## Purpose

Convert one user utterance into proposed operations. The response is a draft and
must not mutate the database until the user confirms it.

## Invariants

- Extract only information stated by the user or present in supplied active-item
  context.
- Never invent a deadline, time, person, action, category, completion, or update.
- Prefer an empty optional field and `other` over a plausible guess.
- Split distinct actions into distinct operations.
- A completion or reschedule targets an existing item. If the match is ambiguous,
  return `needs_clarification=true` and do not choose.
- Resolve relative dates from `now_local` in `timezone`; output ISO 8601.
- A date without a stated time is represented as `YYYY-MM-DD`, not midnight.
- A vague part of day such as `утром` is not converted into a conventional hour.
  It may remain date-only and surface in the daily digest.
- Tasks, waiting items, and reminders with a deadline are `active`; without a
  deadline they are `inbox`.
- Preserve the original utterance in `source_text`.

## Structured response

```json
{
  "operations": [
    {
      "kind": "create",
      "item": {
        "type": "task",
        "title": "Заказать перчатки S",
        "description": null,
        "status": "active",
        "category": "materials",
        "due_at": "2026-09-06",
        "waiting_for": null,
        "source_text": "Завтра надо заказать перчатки S"
      },
      "target_item_id": null,
      "comment": null
    }
  ],
  "needs_clarification": false,
  "clarification_question": null
}
```

`kind` is `create`, `complete`, `reschedule`, or `cancel`. `item` is required only
for `create`; `target_item_id` is required for mutations. Allowed item values:

- `type`: `task`, `waiting`, `note`, `reminder`
- `status`: `inbox`, `active`, `done`, `cancelled`
- `category`: `staff`, `equipment`, `materials`, `documents`, `sanitary`, `other`

## Model prompt

```text
You extract work items for a head nurse from Russian text.

Hard rule: never add information the user did not state. Missing is better than
invented. Do not silently choose among matching active items. Do not turn factual
notes into tasks. Do not treat a statement of completion as a new task.

Given now_local, timezone, source_text, and a compact list of active_items, return
only the supplied JSON schema. Split independent actions. Resolve explicit relative
dates. Keep due_at null if no deadline was said. Use a date-only ISO value when no
time was said. Never invent an hour for a vague part of day. Choose category=other
if evidence is insufficient. For completion,
reschedule, or cancellation, set target_item_id only when one active item is an
unambiguous semantic match; otherwise request clarification.
```

## Acceptance examples

- `Надо как-нибудь решить вопрос с поставщиком` → task, no due date, no invented
  call or meeting.
- `С октября новый график` → note, not a task.
- `Перчатки заказала` → complete a unique matching active item or clarify.
- `Техник не приехал, будет завтра` → reschedule a unique waiting item; preserve
  the fact that the technician did not arrive as an event comment.
