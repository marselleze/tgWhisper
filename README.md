# TgWhisper

Voice-first Telegram capture for a head nurse. The MVP turns text or voice into
confirmed tasks, waiting items, notes, and reminders; stores them in SQLite; and
sends reminders and a morning digest.

## Run

Requires Python 3.12+ and a Telegram bot token plus an OpenAI API key.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
# Fill in .env, then:
tgwhisper
```

No user content is logged. Voice bytes are sent to OpenAI for transcription and
the transcript is sent for structured extraction. SQLite data stays local.

## Verify

```powershell
pytest
```

The test suite covers the repository, capture/confirmation lifecycle, digest
selection, and a 40-message Russian-language contract corpus.

To evaluate the configured model against that corpus (40 paid API requests):

```powershell
$env:OPENAI_API_KEY = "..."
python scripts/evaluate_corpus.py
```

After prompt changes, rerun only selected cases to reduce API usage:

```powershell
python scripts/evaluate_corpus.py --ids 10,13,14,17,20,23,25,28,32,33,36,40
```

The evaluator fails each case on an incorrect operation count/type/date/category,
unexpected clarification, or explicitly forbidden invented detail.

Validate the Telegram token without starting polling or sending a message:

```powershell
python scripts/smoke_telegram.py
```

Product behavior is specified in [docs/UX_SPEC.md](docs/UX_SPEC.md) and the model
contract in [docs/AI_CONTRACT.md](docs/AI_CONTRACT.md).
