# CLAUDE.md

Guidance for AI-assisted work in this repository.

## What this repo is
FastAPI + Beanie (MongoDB) + Taskiq (NATS) backend boilerplate. `src/items` is
the reference feature module; copy it for new features. Read
`docs/ADDING_A_MODULE.md` before creating a module.

## Commands
- `make test` - pytest (hermetic, no services needed)
- `make lint` - ruff check + format check
- `make run` / `make worker` - local API / worker (needs Mongo, Redis, NATS)
- `make start` - full docker compose stack

## Layering rules (enforce in every change)
- `router.py`: parse input, `Depends(get_current_user)`, call one service method. No logic.
- `services/`: business rules, org scoping, `HTTPException`, task dispatch.
- `repositories/`: Mongo queries only. Subclass `BaseRepository[Model]`. No HTTP.
- `models/`: Beanie documents inheriting `BaseDocument`, always `org_id` + `uploaded_by`.
- `schemas/requests|responses|internal`: pydantic only.
- `tasks.py`: `@<broker>.task` wrapper + `_private()` body; progress via `JobTracker`.
- Env vars only in `src/core/config.py`; document new ones in `.env.example`.

## When adding a module
1. Copy `src/items` → `src/<name>`, rename classes.
2. Register repo + service in `src/core/container.py`.
3. `include_router` + `container.wire` in `main.py`.
4. Add owned models to `OWNED_MODELS` in `src/internal/router.py`.
5. Add a queue id in `src/taskiq_brokers.py` if it has tasks; add a worker service in `docker-compose.yml`.
6. Add tests under `tests/` mirroring `test_item_*.py`.

## Style
- Python 3.12, type hints, ruff (line length 100, isort rules).
- Docstrings with usage examples at module top; keep them current.
- Log with `logging.getLogger(__name__)`; no `print`.
- LLM calls go through `get_default_llm_util()` with a pydantic `structure`.
