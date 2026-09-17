# =========================================
# Backend boilerplate - dev commands
# =========================================
COMPOSE_FILE = docker-compose.yml
PY ?= python

GREEN  := \033[0;32m
YELLOW := \033[1;33m
RESET  := \033[0m

.PHONY: help start stop clean logs venv install run worker test lint

help:
	@echo "make start    - docker compose up --build (api + worker + mongo + redis + nats)"
	@echo "make stop     - docker compose down"
	@echo "make clean    - down -v + prune dangling images"
	@echo "make logs     - tail compose logs"
	@echo "make venv     - create .venv with uv (python 3.12)"
	@echo "make install  - install requirements-dev.txt into .venv (includes runtime deps)"
	@echo "make run      - uvicorn with reload (local)"
	@echo "make worker   - taskiq worker for the items queue (local)"
	@echo "make test     - pytest"
	@echo "make lint     - ruff check + ruff format --check"

# ---- docker ------------------------------------------------------------------
start:
	@echo "$(YELLOW)🚀 Starting dev environment...$(RESET)"
	docker compose -f $(COMPOSE_FILE) up --build

stop:
	@echo "$(YELLOW)🛑 Stopping containers...$(RESET)"
	docker compose -f $(COMPOSE_FILE) down

clean:
	@echo "$(YELLOW)🧹 Removing containers, volumes, dangling images...$(RESET)"
	docker compose -f $(COMPOSE_FILE) down -v --remove-orphans
	docker image prune -f
	@echo "$(GREEN)✅ Cleanup complete.$(RESET)"

logs:
	docker compose -f $(COMPOSE_FILE) logs -f --tail=200

# ---- local -------------------------------------------------------------------
venv:
	uv venv --python 3.12 .venv

install:
	uv pip install --python .venv/bin/python -r requirements-dev.txt

run:
	bash scripts/start_server.sh

worker:
	bash scripts/start_worker.sh

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check src tests main.py && .venv/bin/ruff format --check src tests main.py
