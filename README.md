# AI Media Platform (Phase-0)

**Constitution:** [docs/AMP.md](docs/AMP.md) — every future PRP must reference AMP.  
**Service map:** [docs/AMP_SERVICE_MAP.md](docs/AMP_SERVICE_MAP.md)

This repo is the Phase-0 modular monolith that already contains Trend, Strategy, Probability, Generation, QA, Publishing, Metrics, and Verification logic. Services communicate through the in-process event bus in `amp_platform/events/` (same envelopes as future Redis Streams).

```
Trend → Strategy → Probability → Generation → QA → Publish → Metrics → Verify → Learn
```

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

pipeline init-db
pipeline run --vertical kids_rhymes --brief "learning colors with a friendly dog"
pipeline review
pipeline approve <id> --reviewer ishan
pipeline publish <id>
```

Stub providers are on by default (`PIPELINE_STUB_PROVIDERS=true`).

## CLIs

| CLI | Role |
|-----|------|
| `pipeline` | Generation + QA + publish |
| `trend` | Trend V1/V2 opportunities → briefs |
| `predict` | Probability registry, verify, calibrate, rank |
| `assets` | Characters, asset registry, scene resolve |
| `story` | Story blueprints (hook→CTA architecture, critic loop) |
| `storyboard` | Time-coded scenes/shots/audio specs (not prompts/video) |
| `prompt` | CGS → provider prompt packages (compiler; no media) |

```bash
trend v2 -v horror_narration
trend what-next -v horror_narration
predict list
predict rank -v horror_narration
predict verify <id> --views 190000

assets seed
assets characters
assets resolve -c ghost_kid --location "Haunted School" --emotion scared --prop Flashlight --style cinematic_horror

story generate -t "POV horror" -c ghost_kid -n 3 --approve-winner
story show <story_id>
story patterns --seed

storyboard generate -c ghost_kid --approve
storyboard scenes <storyboard_id>
storyboard show <storyboard_id>

prompt compile --bootstrap -c ghost_kid -p veo
prompt compile -b <storyboard_id> --all
prompt providers -m video
prompt show <package_id>
```

## Repo layout (AMP-aligned)

| Path | Role |
|------|------|
| `docs/AMP.md` | Architecture constitution |
| `amp_platform/` | Events, artifacts (shared platform layer) |
| `trend_engine/` | → Trend + Strategy services |
| `prediction/` | → Probability + Verification + Learning |
| `asset_engine/` | → Asset & Character Management Engine |
| `story_engine/` | → Story Engine (blueprints only; not video/prompts) |
| `storyboard_engine/` | → Storyboard Engine (scenes/shots/audio; not generation) |
| `prompt_engine/` | → Prompt Engine (CGS + provider adapters; not generation) |
| `agents/`, `rigs/`, `orchestration/` | → Generation + QA + Publishing |
| `metrics/` | → Metrics service |
| `services/`, `apps/`, `shared/`, `infrastructure/` | Target mono-repo homes (scaffolded) |

## Architecture rules (short)

- No cross-service workflow RPC — use events (`amp_platform.events`)
- Human QA gate is mandatory before publish
- Providers wrap all external APIs
- Predictions are registered for every consequential AI decision
- Future PRPs must cite AMP + list events/artifacts/providers touched

## Tests

```bash
pytest
```

## Status

- [x] AMP constitution + service map
- [x] In-process event bus + canonical event types
- [x] Content pipeline + QA gate
- [x] Trend Engine V1/V2
- [x] Probability + Verification engines
- [x] Asset & Character Engine (registry, versions, resolve, seed)
- [x] Story Engine (schema, generator, critic/revise, patterns, CLI)
- [x] Storyboard Engine (scenes/shots/audio, critic, assets, CLI)
- [x] Prompt Engine (CGS, adapters, critic, experiments, CLI)
- [ ] Redis Streams / Temporal extraction
- [ ] Real provider clients (Anthropic, ElevenLabs, YouTube OAuth, …)
- [ ] Dashboard / API gateway
