DB_URL ?= postgresql://deerflow:deerflow@localhost:5432/deerflow

install:
	uv sync

dev:
	uv run langgraph dev --no-browser --allow-blocking

gateway:
	uv run uvicorn src.gateway.app:app --host 0.0.0.0 --port 8001

gateway-db:
	DATABASE_URL=$(DB_URL) uv run uvicorn src.gateway.app:app --host 0.0.0.0 --port 8001

migrate:
	DATABASE_URL=$(DB_URL) uv run alembic upgrade head

lint:
	uvx ruff check .

format:
	uvx ruff check . --fix && uvx ruff format .
