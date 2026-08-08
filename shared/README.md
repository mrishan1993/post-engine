# Shared

Cross-cutting code that is not the platform SDK:

- database models/migrations (today: root `db/`)
- pydantic schemas shared across apps
- utils / config helpers

Migrate carefully; prefer `amp_platform` for events, artifacts, providers, prompts.
