# AMP Platform Layer (`amp_platform`)

Shared infrastructure used by all services. See [docs/AMP.md](../docs/AMP.md).

> Package is named `amp_platform` (not `platform`) to avoid shadowing Python’s stdlib.

| Package | Status |
|---------|--------|
| `events/` | Phase-0 in-process bus + canonical schemas |
| `artifacts/` | Phase-0 registry stub (URI + lineage) |
| `providers/` | *Planned* — migrate from root `providers/` |
| `prompts/` | *Planned* — versioned prompt registry |
| `models/` | *Planned* — ModelManager |
| `auth/` | *Planned* |
| `sdk/` | *Planned* — cross-cutting client helpers |

**Rule:** Domain packages depend on `amp_platform.*`, not on each other for workflow control.
