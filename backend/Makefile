DB_URL ?= postgresql://thinktank:matterhorn@localhost:5432/thinktank

install:
	uv sync

dev:
	uv run langgraph dev --no-browser --allow-blocking

dev-db:
	DATABASE_URL=$(DB_URL) uv run langgraph dev --no-browser --allow-blocking

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
