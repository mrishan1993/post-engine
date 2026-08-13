# AMP Service Map — Current Code → Target Services

This maps today's Phase-0 modular monolith (`post-engine`) onto AMP services.  
Use this when extracting packages; do not invent parallel modules.

| AMP Service | Current packages / modules | Notes |
|-------------|---------------------------|--------|
| **Trend Service** | `trend_engine/collectors/`, `processing/`, `v2/discovery.py`, `v2/features/`, `v2/patterns/`, `v2/opportunity.py`, `v2/graph.py` | Emits opportunities; stop writing briefs here long-term |
| **Strategy Service** | `trend_engine/v2/characters.py`, `trend_engine/v2/briefs.py` (brief text/character adaptation), parts of `brief_generator/` | Owns `ContentBriefCreated`; character selection lives here |
| **Probability Service** | `prediction/probability.py`, `features.py`, `explainability.py`, `ranking.py`, `registry.py` | Already closest to AMP shape |
| **Prompt Service** | `prompt_engine/` (CGS, compiler, adapters, critic); legacy `prompts/*.txt` in agents | Compiles storyboard→provider packages; does not generate media |
| **Generation Service** | `generation_engine/` + `video_generation_engine/` + `image_generation_engine/` + `music_sfx_engine/` + `voice_generation_engine/`; legacy `agents/*` | Multi-modal generation + P0 specialized paths |
| **Assembly Service** | `assembly_engine/` (spec, timeline, FFmpeg/stub render, tech QA) | Combines generated assets into final reel; does not invent story |
| **QA Service** | `agents/safety_qa_agent.py`, `qa/`, CLI approve/reject, `orchestration/state_machine.py` QA transitions | Must remain mandatory gate |
| **Publishing Service** | `agents/publishing_agent.py`, `providers/{youtube,instagram}` | Needs public URL strategy for IG |
| **Metrics Service** | `metrics/collector.py`, `metrics/reporting.py` | Expand to real platform APIs |
| **Verification Service** | `prediction/verification.py`, `prediction/calibration.py` | Consumes metrics + predictions |
| **Learning Service** | `prediction/learning.py`, trend feedback calibrator | Phase-3; keep thin until data volume |
| **Asset Engine** | `asset_engine/` (characters, assets, resolver, memory) | Underpins Strategy + Generation; not a video generator |
| **Story Engine** | `story_engine/` (schemas, generator, critic, patterns, service) | Narrative blueprints only; feeds Storyboard; uses Asset canon + Probability hints |
| **Storyboard Engine** | `storyboard_engine/` (scenes, shots, audio, continuity, critic) | Visual/audio contract for Prompt/Generation; never emits provider prompts |
| **Prompt Engine** | `prompt_engine/` (CGS, components, registry, adapters, critic) | Translator only; creative truth stays in Story/Storyboard/Asset |
| **Generation Engine** | `generation_engine/` (requests, jobs, router, stubs, artifacts) | Boring multi-modal execution |
| **Video Generation Engine** | `video_generation_engine/` (video requests/jobs/artifacts, refs, ffprobe/stub QA) | P0 clip path; provider-agnostic; does not invent creative intent |
| **Image Generation Engine** | `image_generation_engine/` (image requests/jobs/artifacts, refs, edits, stub QA) | P0 keyframe/thumbnail/cover path; shares generation platform primitives with video |
| **Music & SFX Engine** | `music_sfx_engine/` (blueprint, music jobs, SFX library, audio timeline) | P0 audio path; library-first SFX; Assembly-ready timeline |
| **Voice Generation Engine** | `voice_generation_engine/` (voice registry, jobs, artifacts, word timestamps, timeline) | P0 dialogue/narration performance; does not invent script |
| **Assembly Engine** | `assembly_engine/` (AssemblySpecification, tracks, ducking, captions, render jobs, artifacts) | P0 reel assembly; executes storyboard timing; FFmpeg + stub; never invents creative intent |

## Shared platform (current → target)

| Platform capability | Current | Target (`amp_platform/`) |
|---------------------|---------|--------------------------|
| Config | `config/` | `shared/config` + amp loaders |
| Providers | `providers/` | `amp_platform/providers` |
| Events | in-process bus | `amp_platform/events` → Redis Streams |
| Artifacts | `storage/` paths ad hoc | `amp_platform/artifacts` |
| Prompts | `prompts/*.txt` | `amp_platform/prompts` |
| Models | direct provider classes | `amp_platform/models` ModelManager |
| Auth | `.env` secrets | `amp_platform/auth` |
| DB | `db/` | `shared/database` (same schemas initially) |
| Orchestration | `orchestration/` | Temporal later; keep DAG until then |
| Observability | `monitoring/` | Langfuse/Sentry/Prom later |

## Event ownership today (Phase-0)

Until services are split, the in-process bus in `amp_platform/events/` is the source of truth for event names/payloads. Publishers:

| Event | Phase-0 publisher module |
|-------|--------------------------|
| `TrendOpportunityCreated` | `trend_engine/v2/pipeline.py` (after persist_opportunities) |
| `ContentBriefCreated` | `trend_engine/v2/briefs.py` |
| `PredictionCreated` | `prediction/registry.py` |
| `VideoCreated` | `orchestration/pipeline.py` (assembled → qa_pending path) |
| `VideoApproved` / `VideoRejected` | `orchestration/pipeline.py` approve/reject |
| `VideoPublished` | `orchestration/pipeline.py` publish |
| `MetricsUpdated` | `metrics/collector.py` |
| `PredictionVerified` | `prediction/verification.py` |
| `StoryCreated` / `StoryApproved` | `story_engine/service.py` |
| `StoryboardCreated` / `StoryboardApproved` | `storyboard_engine/service.py` |
| `PromptPackCreated` | `prompt_engine/service.py` |
| `GenerationRequested`…`ArtifactCreated` | `generation_engine/` |
| `VideoGenerationRequested`…`VideoArtifactCreated` | `video_generation_engine/` |
| `ImageGenerationRequested`…`ImageArtifactCreated` / `ImageEdited` | `image_generation_engine/` |
| `MusicGenerationRequested`…`MusicArtifactCreated` / `SFX*` / `AudioTimelineCreated` | `music_sfx_engine/` |
| `VoiceGenerationRequested`…`VoiceArtifactCreated` / `VoiceTimelineCreated` | `voice_generation_engine/` |
| `AssemblyCreated`…`RenderCompleted` / `RenderArtifactCreated` / `RenderTechnicalQACompleted` | `assembly_engine/` |

## Extraction order (recommended)

1. Events + Artifact Registry (contracts)  
2. Metrics Service (read-mostly, low coupling)  
3. Probability / Verification (already isolated)  
4. Trend Service  
5. Generation + QA + Publishing (keep together until Temporal)  
6. Strategy + Prompt (thin, after Trend emits clean opportunities)  
7. Learning (last — needs verified volume)

## Rule

If a future PR adds a package that duplicates one of these services under a new name, it is **AMP-noncompliant**. Extend the mapped module or extract the mapped service.
