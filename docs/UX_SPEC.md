# TgWhisper MVP 0.1 — Telegram UX specification

## Product promise

A head nurse can capture a work thought by voice or text in 5–10 seconds. The bot
turns only what was actually said into one or more items, asks for confirmation,
and brings each item back at the useful moment.

The core loop is:

`said → understood → confirmed → saved → surfaced → closed`

## Interaction principles

1. Voice and text are equal inputs.
2. The bot never invents a person, action, category, date, or time.
3. Missing information remains missing. A deadline is optional.
4. Every parse is shown before it becomes active data.
5. One message may create or update several items.
6. Destructive actions require an explicit confirmation.
7. Dates are shown in the user's timezone and in human language where possible.

## Commands and persistent menu

| Command | Result |
|---|---|
| `/start` | Onboarding and timezone confirmation |
| `/today` | Open items due today and overdue items |
| `/inbox` | Items without a deadline or awaiting clarification |
| `/all` | All active items grouped by type |
| `/settings` | Timezone and daily digest time |
| `/help` | Short examples and privacy notice |

Persistent menu buttons: `Сегодня`, `Входящие`, `Все`, `Настройки`.

## First run

### `/start`

```text
Здравствуйте! Я сохраняю рабочие мысли из текста и голосовых сообщений.

Можно написать или сказать, например:
«Завтра заказать перчатки и проверить техника по автоклаву».

Я покажу, что поняла, прежде чем сохранить.

Ваш часовой пояс: Europe/Moscow (14:35). Верно?

[Да, верно] [Изменить]
```

After confirmation:

```text
Готово. Присылайте первую запись.
Утренняя сводка будет приходить в 08:00.

[Изменить время] [Как это работает]
```

## Shared capture flow

While processing voice:

```text
🎙 Распознаю голосовое…
```

If transcription or parsing takes longer than a few seconds:

```text
Разбираю запись на отдельные пункты…
```

Preview before saving:

```text
Добавить 2 пункта?

📦 Заказать перчатки S
Задача · Материалы
📅 Завтра

⏳ Проверить, приехал ли техник по автоклаву
Ожидание · Оборудование
📅 Завтра

[Всё верно] [Исправить] [Отмена]
```

After confirmation:

```text
✓ Добавила 2 пункта.
[Открыть] [Отменить добавление]
```

`Исправить` opens per-item controls:

```text
Что исправить?

[1 · Заказать перчатки S]
[2 · Проверить техника]
[Разделить иначе] [Отмена]
```

For an item:

```text
Заказать перчатки S

[Название] [Тип] [Срок]
[Категория] [Удалить пункт]
[Готово]
```

The user may also reply in natural language: `У первого срок в пятницу`.

## Eight required scenarios

### 1. Simple task

Input: `Заказать перчатки`.

```text
Добавить пункт?

📥 Заказать перчатки
Задача · Материалы
Срок не указан

[Всё верно] [Исправить] [Отмена]
```

It enters `Входящие`; no deadline is inferred.

### 2. Task with a deadline

Input: `Завтра заказать перчатки`.

```text
📦 Заказать перчатки
Задача · Материалы
📅 Завтра
```

The stored absolute timestamp is calculated in the user's timezone. A date without
a time remains an all-day deadline.

### 3. Several tasks in one message

Input: `Заказать перчатки и позвонить технику`.

The preview contains two independently editable items. Confirmation saves both in
one transaction; cancellation saves neither.

### 4. Waiting for another person

Input: `Техник будет во вторник`.

```text
⏳ Техник — визит
Ожидание
Кого ждём: техник
📅 Во вторник
```

The verb is not made more specific than the source. If the context does not say
what the technician will do, the bot does not invent it.

### 5. Information without an action

Input: `С октября новый график`.

```text
📝 С октября новый график
Заметка
```

The phrase is stored as a note, not converted into a task.

### 6. Reminder

Input: `В 15 часов напомни позвонить поставщику`.

```text
🔔 Позвонить поставщику
Напоминание
⏰ Сегодня, 15:00
```

At the due time:

```text
🔔 Позвонить поставщику

[Готово] [Через час] [Перенести]
```

If 15:00 has already passed, the preview asks for clarification instead of moving
the reminder silently to tomorrow.

### 7. Complete an item

Input: `Перчатки заказала`.

If there is one strong match:

```text
Отметить выполненным?

✓ Заказать перчатки S

[Да] [Выбрать другой пункт] [Отмена]
```

If there are several plausible matches, the bot lists them and makes no update
until the user chooses. A completion statement that matches nothing becomes a
clarification, never a new task.

### 8. Change a situation

Input: `Техник не приехал, сказал будет послезавтра`.

```text
Обновить ожидание?

⏳ Техник — автоклав
Новый срок контроля: послезавтра
Комментарий: техник не приехал

[Обновить] [Выбрать другой пункт] [Отмена]
```

The existing item stays active; the previous due date is retained in its event
history.

## Daily digest

At the configured local time (default 08:00):

```text
Доброе утро.

На сегодня:

🔴 2 задачи
• Заказать перчатки S
• Проверить журнал стерилизации

⏳ 1 ожидание
• Техник — автоклав

Просрочено: 1

[Открыть всё] [Разобрать по одному]
```

No empty digest is sent unless the user enables it. Overdue items remain visible
until completed, cancelled, or rescheduled.

## Item details

```text
📦 Заказать перчатки S
Задача · Материалы
📅 6 сентября
Создано из голосового сообщения

[Готово] [Перенести]
[Изменить] [Отменить]
```

`Отменить` means changing status to `cancelled`, not deleting the database row.

## Failure and uncertainty states

### Voice cannot be transcribed

```text
Не удалось разобрать голосовое. Попробуйте записать ещё раз или пришлите текст.
[Записать снова]
```

### Parser is uncertain

```text
Я не уверена, что это задача.

«Надо как-нибудь решить вопрос с поставщиком»

[Сохранить как задачу] [Сохранить как заметку] [Отмена]
```

If saved as a task, its title is `Разобраться с вопросом по поставщику`; the
deadline stays empty.

### Date is ambiguous

```text
Какой понедельник вы имеете в виду?
[Ближайший, 7 сентября] [Следующий, 14 сентября] [Без срока]
```

### Service is temporarily unavailable

```text
Сейчас не получилось обработать запись. Я ничего не сохранила.
Попробуйте ещё раз через минуту.
```

## Settings

```text
Настройки

Часовой пояс: Europe/Moscow
Утренняя сводка: 08:00
Пустая сводка: выключена

[Часовой пояс] [Время сводки]
[Пустая сводка] [Удалить мои данные]
```

Deleting user data requires a second explicit confirmation and removes the user's
items, source transcripts, and settings.

## MVP exclusions

No mobile or web application, employee roles, analytics dashboard, clinical-system
integration, OCR, document workflows, complex projects, or custom category trees.
