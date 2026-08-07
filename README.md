# Content Pipeline

Automated AI content pipeline that turns a brief into a Short/Reel, with a **mandatory human QA gate** before every publish.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

pipeline init-db
pipeline run --vertical kids_rhymes --brief "learning colors with a friendly dog"
pipeline review
pipeline preview <id>
pipeline approve <id> --reviewer ishan
pipeline publish <id>
```

Stub providers are on by default (`PIPELINE_STUB_PROVIDERS=true`) so you can exercise the full DAG without API keys.

## Architecture

- **Config-driven verticals** — `config/verticals/*.yaml` validated by Pydantic (`config/schema.py`)
- **Hand-rolled DAG** — `orchestration/pipeline.py` + retry + state machine
- **SQLite now / Postgres later** — SQLAlchemy models in `db/models.py`
- **Human QA enforced in the state machine** — `qa_pending → published` is illegal; only `qa_approved → published`

## CLI

| Command | Purpose |
|---------|---------|
| `pipeline run -v <slug> -b "..."` | Enqueue brief and run to `qa_pending` |
| `pipeline review` | List QA queue |
| `pipeline preview <id>` | Open rendered file |
| `pipeline approve <id> --reviewer …` | Approve |
| `pipeline reject <id> --reviewer … --reason …` | Reject |
| `pipeline regen <id> --from audio_done` | Child run from rejected parent |
| `pipeline publish <id>` | Publish approved run |

## Adding a vertical

1. Add `config/verticals/<slug>.yaml`
2. Add `prompts/<slug>_script.txt` (if needed)
3. Add `rigs/<slug>/compositor.py` (+ assets)
4. Zero changes to `orchestration/`, `db/`, or `agents/base.py`

## Tests

```bash
pytest
```

Golden-path CI test: stub providers → `video_runs.status == qa_pending`.

## Status

Phase-1 skeleton from PRP v3:

- [x] DB schema + Alembic migration
- [x] Pipeline skeleton + stub agents/providers
- [x] CLI review/approve/reject/regen
- [x] Minimal kids_rhymes + horror_narration rigs
- [ ] Real Anthropic / ElevenLabs / Suno clients
- [ ] Mouth-flap / Ken Burns compositors
- [ ] YouTube OAuth upload + Instagram public-URL hosting
