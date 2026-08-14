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
| `generate` | Execute PromptPackages → local stub media artifacts |
| `videogen` | Video-specialized path (refs, duration strategy, tech QA) |
| `imagegen` | Image-specialized path (keyframes, refs, edits, tech QA) |
| `musicgen` | Music & SFX (blueprint, library SFX, timeline) |
| `voicegen` | Voice generation (profiles, takes, timestamps, timeline) |
| `assemble` | Assembly (timeline → FFmpeg/stub → final reel + tech QA) |
| `publish` | Publishing (accounts, QA-gated plans, multi-platform receipts) |
| `qa` | QA (multi-dimension gate: PASS / REPAIR / REGENERATE / BLOCK) |
| `perf` | Performance & Analytics (actuals, curves, virality, benchmarks) |
| `verify` | Verification (predicted vs actual, calibration, learning signals) |
| `learn` | Learning & Optimization (patterns, profiles, briefs, experiments) |

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

generate run --bootstrap -c ghost_kid -n 2
generate show <request_id>
generate artifacts <request_id>
generate providers

videogen run --bootstrap -c ghost_kid -n 2 --provider provider_a
videogen artifacts <request_id>
videogen providers

imagegen run --bootstrap -c ghost_kid -n 2 --provider provider_a --purpose storyboard_keyframe
imagegen artifacts <request_id>
imagegen edit <artifact_id> -i "soften expression, keep identity"
imagegen providers

musicgen run --bootstrap -c ghost_kid --provider provider_a
musicgen timeline <request_id>
musicgen sfx-search door
musicgen providers

voicegen run --bootstrap -c ghost_kid -n 2 --provider provider_a
voicegen run -c ghost_kid -t "Wait... did you hear that?" --emotion fear -n 3 --json
voicegen profiles
voicegen character ghost_kid
voicegen providers

assemble run --bootstrap -c ghost_kid --quality final
assemble profiles
assemble list
assemble artifacts <assembly_id>
assemble render-status <render_id>

publish run --bootstrap -c ghost_kid --platforms instagram,youtube
publish connect instagram -e ig_1 -u ghost_kid_ig --token stub
publish accounts
publish profiles
publish list
publish show <plan_id>
publish receipt <job_id>

qa run --bootstrap -c ghost_kid
qa run --assembly <assembly_id>
qa issues <qa_run_id>
qa approval <qa_run_id>
qa approve <qa_run_id> --reviewer ishan
qa list

perf run --bootstrap --profile viral
perf show <publication_id>
perf timeseries <publication_id> -m views
perf retention <publication_id>
perf benchmarks <publication_id>
perf refresh <publication_id> --age 3600 --profile viral

verify run --bootstrap
verify show <verification_id>
verify prediction <prediction_ref>
verify calibration virality_predictor --version v4
verify performance virality_predictor
verify signals --prediction <prediction_ref>
verify compare virality_predictor:v4 virality_predictor:v5

learn run --bootstrap
learn profile -c ravi -p instagram
learn patterns -c ravi
learn recommend -c ravi
learn character ravi
learn trends
learn experiment --create
learn train --model virality_predictor
learn models
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
| `generation_engine/` | → Generation Engine (jobs/router/artifacts; stub providers) |
| `video_generation_engine/` | → Video Generation Engine (clips, refs, technical QA) |
| `image_generation_engine/` | → Image Generation Engine (keyframes, refs, edits, tech QA) |
| `music_sfx_engine/` | → Music & SFX Engine (blueprint, music, SFX library, timeline) |
| `voice_generation_engine/` | → Voice Generation Engine (profiles, dialogue takes, timestamps) |
| `assembly_engine/` | → Assembly Engine (spec → timeline → final reel) |
| `publishing_engine/` | → Publishing Engine (QA-gated multi-platform publish) |
| `qa_engine/` | → QA Engine (multi-dimension gate before publish) |
| `performance_engine/` | → Performance & Analytics (actuals after publish) |
| `verification_engine/` | → Verification (error, calibration, learning signals; not causality) |
| `learning_engine/` | → Learning & Optimization (observations, patterns, briefs; not content gen) |
| `agents/`, `rigs/`, `orchestration/` | → Legacy pipeline + QA + Publishing |
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
- [x] Generation Engine (jobs, routing, retry/fallback, stub artifacts, CLI)
- [x] Video Generation Engine (provider A stub, refs, duration strategy, tech QA)
- [ ] Redis Streams / Temporal extraction
- [ ] Real provider clients (Anthropic, ElevenLabs, YouTube OAuth, …)
- [ ] Dashboard / API gateway
