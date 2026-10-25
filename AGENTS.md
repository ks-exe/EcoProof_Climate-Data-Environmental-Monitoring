# AGENTS.md — EcoProof

## Goal

Verifiable air-quality data platform for a hackathon (deadline Oct 25, 2026). Real data, real tests,
no faked results. See docs/SPEC.md for the full spec.

## Rules

- Python 3.11, type hints, small functions. Run `pytest -q` before saying a task is done.
- Never commit secrets. Read keys from env (.env.example documents them).
- Bronze files are immutable. Silver/Gold must be rebuildable from Bronze with one command.
- Hashing: canonical JSON (sorted keys, no spaces, floats to 4 decimals, UTC ISO timestamps).
- SQL from any LLM path must pass src/ecoproof/sqlchat/guard.py (single SELECT, allow-list, LIMIT).
- Do not invent metrics. Evaluation numbers come from reports/eval.json produced by code.
- If a library or API detail is uncertain, check its docs or ask; do not guess endpoints.

## Commands

- make ingest | make build | make detect | make eval | make anchor | make api | make web | make test

## Definition of done (per task)

Code + unit tests + a short note in README if behavior or setup changed.

## Session working rules

- Read this file and docs/SPEC.md fully before working. docs/SPEC.md is the source of truth;
  do not delete or rewrite it. If a correction seems necessary, explain it and propose a change.
- Work on one task at a time, following the prompt sequence in section 10. Stop after each task
  for the user's review.
- After each task, update docs/PROGRESS.md with what was built, files changed, tests run and
  results, uncertainties, and the next task.
- Show actual test output. Do not claim untested behavior or invent metrics, API endpoints, or results.
- Use .env for local secrets and keep .env.example up to date.
- Keep the scope of the spec. Flag deadline risks instead of expanding scope.
