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

## Trend engine

**V1** ranks topics. **V2** ranks viral *opportunities* (emotion, hook, story, audio/visual patterns, lifecycle, character fit) and answers: *if we publish in the next 12 hours, what should we make?*

```bash
trend ingest                              # V1 topics → content_briefs
trend v2                                  # V2 Content DNA → opportunities → briefs
trend what-next -v horror_narration       # next-12h recommendation
trend opportunities -v kids_rhymes
trend briefs --source trend_engine_v2
```

Config: `trend_engine/config/sources.yaml` (collectors), `trend_engine/config/v2.yaml` (characters, opportunity weights). Stubs on by default.

## Probability & Verification Engine

Before production, every opportunity gets a full prediction object (probability + expected values + confidence + reasoning). After publish, verification compares predicted vs actual and feeds calibration.

```bash
trend v2                                 # opportunities → briefs + predictions
predict list                             # pending predictions
predict show <id>                        # explainability
predict rank -v horror_narration         # production queue by expected score
predict verify <id> --views 190000       # manual verification
predict calibration
predict kpis
predict retrain                          # apply vertical calibration multipliers
```

Workflow: **Trend → Predict → Rank → Create → Publish → Measure → Verify → Learn**.

## Architecture

- **Config-driven verticals** — `config/verticals/*.yaml` validated by Pydantic (`config/schema.py`)
- **Hand-rolled DAG** — `orchestration/pipeline.py` + retry + state machine
- **SQLite now / Postgres later** — SQLAlchemy models in `db/models.py`
- **Human QA enforced in the state machine** — `qa_pending → published` is illegal; only `qa_approved → published`
- **Trend engine** — shared DB tables (`trend_signals`, `trend_topics`, `trend_scores`, `trend_feedback`) feeding `content_briefs`

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
| `trend ingest` | Daily trend ingestion → briefs |

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

Phase-1 skeleton from PRP v3 + Trend Engine PRP v1:

- [x] DB schema + Alembic migration
- [x] Pipeline skeleton + stub agents/providers
- [x] CLI review/approve/reject/regen
- [x] Minimal kids_rhymes + horror_narration rigs
- [x] Trend tables + YouTube/Google Trends collectors (stub + live hooks)
- [x] Scoring + brief generator → `content_briefs`
- [x] V2: Content DNA, lifecycle, knowledge graph, opportunity score, character adaptation
- [x] Probability Engine + Prediction Registry + Verification + calibration
- [ ] Real Anthropic / ElevenLabs / Suno clients
- [ ] Mouth-flap / Ken Burns compositors
- [ ] YouTube OAuth upload + Instagram public-URL hosting
- [ ] TikTok/Reddit collectors + multimodal meme clustering
- [ ] LLM feature extractors (replace heuristics)
- [ ] V3 Growth Intelligence (own-channel experiment loop)
