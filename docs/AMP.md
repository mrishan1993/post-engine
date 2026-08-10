# AI Media Platform Architecture (AMP v1)

**Status:** Constitution — Draft v1  
**Owner:** Ishan  
**Role:** Master architecture document. Every future PRP must reference AMP rather than redefining storage, providers, events, or orchestration.

---

## 1. Vision

```
                    AI Media Platform

          ┌───────────────────────────────┐
          │        API Gateway            │
          └──────────────┬────────────────┘
                         │
      ┌──────────────────┼──────────────────┐
      │                  │                  │
 Strategy           Content            Analytics
 Services           Services            Services
      │                  │                  │
      └──────────────Event Bus──────────────┘
                         │
                Shared Platform Layer
                         │
         PostgreSQL + Redis + Object Storage
         (+ pgvector / Neo4j / ClickHouse as scale demands)
```

We do **not** build one forever-monolith. We build **platform services** that share infrastructure and communicate through events.

The current `post-engine` codebase is the **Phase-0 modular monolith** that already contains logic destined for these services. AMP defines the target shape; extraction happens service-by-service without rewriting working paths prematurely.

---

## 2. Architecture Philosophy

Every service follows the same pattern:

```
Input → Processing → Artifacts → Events → Storage
```

### Hard rules

1. **No direct service-to-service calls** for business workflow. Services publish and subscribe to events.
2. **Providers are the only outbound I/O** to third parties (LLM, TTS, music, social APIs).
3. **Artifacts are first-class** — every generated object has type, version, source, and lineage.
4. **Predictions are first-class** — every consequential AI decision is registered (see Prediction Registry).
5. **Human QA is mandatory before publish** — enforced by state/events, not convention.
6. **Config is data** — YAML → Pydantic → runtime; verticals/characters/prompts are not hardcoded.
7. **Future PRPs reference AMP** — they may add events/tables/providers; they must not invent a parallel architecture.

### Allowed sync calls

- Service → Shared Platform SDK (auth, config, model manager, artifact registry)
- Service → its own database schema (or shared DB with clear ownership)
- API Gateway → service HTTP for request/response UX (dashboard, CLI, admin)

Workflow *coordination* still goes through the event bus / orchestrator, not ad-hoc RPC chains.

---

## 3. Core Services

| # | Service | Responsibility | Consumes | Produces |
|---|---------|----------------|----------|----------|
| 1 | **Trend Service** | Collect, normalize, cluster, score, opportunities | schedule / manual trigger | `TrendOpportunityCreated` |
| 2 | **Strategy Service** | Opportunity → vertical/character briefs | `TrendOpportunityCreated` | `ContentBriefCreated` |
| 3 | **Probability Service** | Predict success metrics + confidence | `ContentBriefCreated` | `PredictionCreated` |
| 4 | **Prompt Service** | Script/visual/music/thumb/metadata prompts | `PredictionCreated` (or ranked brief ready) | `PromptPackCreated` |
| 5 | **Generation Service** | Script, voice, music, images, video | `PromptPackCreated` | `VideoCreated` |
| 6 | **QA Service** | Automated safety + human gate | `VideoCreated` | `VideoApproved` / `VideoRejected` |
| 7 | **Publishing Service** | Platform uploads | `VideoApproved` | `VideoPublished` |
| 8 | **Metrics Service** | Poll YT/IG/TikTok | schedule | `MetricsUpdated` |
| 9 | **Verification Service** | Predicted vs actual | `MetricsUpdated` + prediction linkage | `PredictionVerified` |
| 10 | **Learning Service** | Weights, embeddings, KG, models | `PredictionVerified` | `ModelUpdated` / internal state |
| — | **Asset Engine** (shared capability) | Characters, worlds, props, styles, voices, references, memory, resolution | resolve requests from Strategy/Prompt/Generation | `AssetCreated`, `CharacterCreated`, `GenerationContextResolved` |

Asset Engine is not a workflow stage between Trend and Publish; it is a **shared creative-identity substrate** that Strategy/Prompt/Generation call (via SDK today, events later) to resolve generation context. See PRP: Asset & Character Management Engine.

### Service invariants

- A service owns its **processing logic** and the **events it emits**.
- A service may read shared registries (prompts, models, artifacts) via platform SDK.
- A service must implement: health check, idempotent event handlers, structured logging, cost reporting.

---

## 4. Canonical Event Catalog

Events are versioned: `amp.<domain>.<name>.v1`.

| Event | Payload (minimum) | Emitter |
|-------|-------------------|---------|
| `TrendOpportunityCreated` | opportunity_id, vertical_slugs, score, lifecycle, pattern_key, dna_summary | Trend |
| `ContentBriefCreated` | brief_id, opportunity_id?, vertical_slug, character_slug?, priority, source | Strategy |
| `PredictionCreated` | prediction_id, brief_id, virality_probability, expected_views, confidence, model_version | Probability |
| `PromptPackCreated` | pack_id, brief_id, prediction_id, prompt_artifact_ids[] | Prompt |
| `VideoCreated` | video_run_id, brief_id, artifact_ids[], rendered_path | Generation |
| `VideoApproved` | video_run_id, reviewer, qa_notes? | QA |
| `VideoRejected` | video_run_id, reviewer, reason | QA |
| `VideoPublished` | video_run_id, publications[] | Publishing |
| `MetricsUpdated` | publication_id, video_run_id, metrics{}, pulled_at | Metrics |
| `PredictionVerified` | prediction_id, verification_id, mape, lesson? | Verification |
| `ModelUpdated` | model_version, subsystem, calibration/weights ref | Learning |

### Event envelope (all events)

```json
{
  "event_id": "uuid",
  "event_type": "amp.trend.opportunity_created.v1",
  "occurred_at": "ISO-8601",
  "producer": "trend-service",
  "correlation_id": "uuid",
  "causation_id": "uuid | null",
  "payload": {}
}
```

Idempotency key = `(event_type, aggregate_id, producer_version)` or explicit `event_id` dedupe in consumers.

---

## 5. Shared Platform Layer

### 5.1 Authentication

- JWT for users/dashboard
- OAuth for platform publishing (YouTube, etc.)
- API keys for machine/CLI automation

### 5.2 Configuration

```
YAML → Pydantic models → Runtime Config
```

Owned paths: verticals, characters, source collectors, scoring weights, provider keys (via env).

### 5.3 Prompt Registry

Every AI prompt is versioned:

| Field | Purpose |
|-------|---------|
| name | Stable identity |
| version | Immutable revision |
| owner | Service/team |
| variables | Declared inputs |
| model_hint | Preferred model |
| performance | Optional quality/cost metrics |

No raw prompt strings buried only in application code for production paths.

### 5.4 Model Registry / ModelManager

```text
ModelManager.generate(task, messages, schema?, model_hint?)
```

Internally routes to Claude / GPT / Gemini / etc. Services never hardcode a vendor client for reasoning tasks.

### 5.5 Provider Layer

Every external system is a provider implementing:

```text
health()
generate() | publish() | collect()
estimate_cost()
estimate_latency()
fallback()
```

Domains: LLM, music, video, voice, image, publishing, trend sources.

### 5.6 Artifact Registry

Everything generated is an artifact with lineage:

```
Prompt → Script → Voice → Music → Video → Thumbnail
```

| Field | Purpose |
|-------|---------|
| artifact_id | Unique |
| type | script / audio / image / video / prompt_pack / report |
| version | Revision |
| source_service | Producer |
| parent_ids | Lineage |
| uri | S3/R2/local path |
| content_hash | Integrity |
| metadata | Freeform JSON |

### 5.7 Prediction Registry

Every consequential AI decision creates a prediction record:

- what / why / confidence / expected outcome  
- later: actual / error / lesson  

Used by Probability, Verification, Learning — and any future Experiment / Character engines.

---

## 6. Event Bus

**Heart of the platform.** Services subscribe; they do not chain-call.

| Scale | Choice |
|-------|--------|
| Now → early multi-service | **Redis Streams** |
| Later (ops maturity) | NATS |
| High-throughput analytics fanout | Kafka (only if needed) |

### Phase-0 (current monolith)

In-process event bus (same envelope schemas) so handlers can be extracted to services without changing event contracts.

---

## 7. Storage Responsibilities

| Store | Owns | Phase |
|-------|------|-------|
| **PostgreSQL** | Users, videos/runs, briefs, predictions, experiments, transactional metrics refs | Now (SQLite → Postgres) |
| **pgvector** | Embeddings: hooks, scripts, stories, characters, comments | When semantic search lands |
| **Neo4j** | Knowledge graph (trend → emotion → audience → character) | When graph queries outgrow SQL |
| **ClickHouse** | High-volume analytics events, verification time-series | When volume justifies |
| **Object storage (R2/S3)** | Videos, images, audio, prompt packs, reports | Local `storage/` now; prefix-compatible |

**Rule:** Do not put blob bytes in Postgres. Store URIs + hashes in Artifact Registry.

---

## 8. Orchestration

Target: **Temporal** (or equivalent) for durable workflows:

- Activities with retry / timeout  
- Checkpoints / resume  
- Human approval gates (QA)  

Phase-0: hand-rolled DAG + state machine in `orchestration/` (already present). Migration criterion: parallel verticals, long-running waits, or need for first-class workflow UI.

---

## 9. Monitoring & Observability

Every service reports:

- Latency, tokens, cost, failures, retries  
- Queue depth, success rate  

Stack target:

| Concern | Tool |
|---------|------|
| LLM traces | Langfuse |
| Errors | Sentry |
| Metrics | Prometheus + Grafana |
| Alerts | Webhook (Slack/Discord) — already stubbed |

---

## 10. Technology Stack (target)

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12 + FastAPI |
| Workflow | Temporal |
| Event Bus | Redis Streams |
| Cache | Redis |
| Primary DB | PostgreSQL |
| Vector | pgvector |
| Knowledge Graph | Neo4j |
| Analytics | ClickHouse |
| Object Storage | Cloudflare R2 |
| ORM | SQLAlchemy |
| Validation | Pydantic |
| Migrations | Alembic |

### AI providers (defaults)

| Domain | Primary | Fallback |
|--------|---------|----------|
| Reasoning | Claude Sonnet | GPT |
| Structured outputs | GPT | Claude |
| Multimodal | Gemini | GPT |
| Image | GPT Image / Flux | — |
| Video gen | Veo / Runway | — |
| Voice | ElevenLabs | Cartesia |
| Music | Suno | Udio |
| Captions | Whisper | Gemini |
| Embeddings | OpenAI | Gemini |

Provider choices may change; **ModelManager + Provider interfaces must not.**

---

## 11. Target Repository Structure

```text
ai-media-platform/
├── platform/           # auth, events, prompts, providers, models, artifacts, sdk
├── services/           # one package per AMP service
├── shared/             # database, schemas, utils, config
├── apps/               # dashboard, admin, api gateway
└── infrastructure/     # docker, terraform, monitoring, deployment
```

### Phase-0 layout (this repo today)

Logic lives in modular packages (`trend_engine/`, `prediction/`, `agents/`, `orchestration/`, …).  
AMP scaffolds under `amp_platform/` (Python package name — avoids clashing with stdlib `platform`) and `docs/`. Physical extraction into `services/*` happens when a domain has clear event boundaries and independent deploy need.

See [AMP_SERVICE_MAP.md](./AMP_SERVICE_MAP.md).

---

## 12. End-to-End Happy Path

```text
Schedule/Trigger
    → TrendService        → TrendOpportunityCreated
    → StrategyService     → ContentBriefCreated
    → ProbabilityService  → PredictionCreated
    → (rank / threshold gate)
    → PromptService       → PromptPackCreated
    → GenerationService   → VideoCreated
    → QAService           → VideoApproved  (human gate)
    → PublishingService   → VideoPublished
    → MetricsService      → MetricsUpdated  (async, recurring)
    → VerificationService → PredictionVerified
    → LearningService     → ModelUpdated
```

**No publish without `VideoApproved`.**  
**No learning without verified predictions.**

---

## 13. Migration Principles (from monolith → services)

1. **Events first** — adopt envelope + catalog in-process before splitting processes.  
2. **One service at a time** — extract Trend or Metrics before Generation.  
3. **Shared DB until painful** — schema ownership comments; split databases later.  
4. **Keep CLIs** — `pipeline`, `trend`, `predict` become thin clients of the API/event bus.  
5. **Never break the QA gate** during extraction.  
6. **Every new PRP** must list: events touched, artifacts produced, providers used, AMP section referenced.

---

## 14. PRP Compliance Checklist

Future PRPs must include:

- [ ] AMP sections referenced  
- [ ] New/changed events (name + payload)  
- [ ] Owning service  
- [ ] Artifacts produced  
- [ ] Providers used  
- [ ] Storage impact (which store)  
- [ ] Prediction Registry impact (if any decision is made)  
- [ ] Explicit non-goals  

PRs that introduce direct cross-service imports for workflow control are out of compliance unless justified as temporary Phase-0 coupling with an extraction issue filed.

---

## 15. Non-Goals (AMP v1)

- Full Temporal / Neo4j / ClickHouse deployment on day one  
- Scraping platforms outside sanctioned APIs  
- Publishing without human QA  
- Per-service custom provider stacks  
- Rewriting the working monolith before event contracts stabilize  

---

## 16. Open Decisions

| Topic | Default until decided |
|-------|------------------------|
| Event bus productization | Redis Streams |
| Object storage | Local → R2 |
| Orchestrator | Hand-rolled → Temporal when needed |
| Graph DB | SQL KG tables → Neo4j when query patterns demand |
| Multi-tenant | Single operator (Ishan) first |

---

*AMP v1 is the constitution. Change it deliberately; implement features in service PRPs that cite it.*
