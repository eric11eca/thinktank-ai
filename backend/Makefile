DB_URL ?= postgresql://thinktank:matterhorn@localhost:5432/thinktank
MCP_CONFIG_PATH ?=/Users/zechen/EPFL/thinktank-ai/docker/extensions_config.mcp-dev.json

install:
	uv sync

dev:
	DATABASE_URL=$(DB_URL) DEER_FLOW_EXTENSIONS_CONFIG_PATH=$(MCP_CONFIG_PATH) uv run langgraph dev --no-browser --allow-blocking

gateway:
	DATABASE_URL=$(DB_URL) DEER_FLOW_EXTENSIONS_CONFIG_PATH=$(MCP_CONFIG_PATH) uv run uvicorn src.gateway.app:app --host 0.0.0.0 --port 8001

gateway-db:
	DATABASE_URL=$(DB_URL) uv run uvicorn src.gateway.app:app --host 0.0.0.0 --port 8001

migrate:
	DATABASE_URL=$(DB_URL) uv run alembic upgrade head

lint:
	uvx ruff check .

format:
	uvx ruff check . --fix && uvx ruff format .
