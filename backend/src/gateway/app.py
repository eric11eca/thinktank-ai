import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.gateway.auth.routes import router as auth_router
from src.gateway.config import get_gateway_config
from src.gateway.routers import agent, artifacts, keys, mcp, memory, models, providers, skills, threads, uploads

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    config = get_gateway_config()
    logger.info(f"Starting API Gateway on {config.host}:{config.port}")

    # NOTE: MCP tools initialization is NOT done here because:
    # 1. Gateway doesn't use MCP tools - they are used by Agents in the LangGraph Server
    # 2. Gateway and LangGraph Server are separate processes with independent caches
    # MCP tools are lazily initialized in LangGraph Server when first needed

    yield
    logger.info("Shutting down API Gateway")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """

    app = FastAPI(
        title="DeerFlow API Gateway",
        description="""
## DeerFlow API Gateway

API Gateway for DeerFlow - A LangGraph-based AI agent backend with sandbox execution capabilities.

### Features

- **Models Management**: Query and retrieve available AI models
- **MCP Configuration**: Manage Model Context Protocol (MCP) server configurations
- **Memory Management**: Access and manage global memory data for personalized conversations
- **Skills Management**: Query and manage skills and their enabled status
- **Artifacts**: Access thread artifacts and generated files
- **Health Monitoring**: System health check endpoints

### Architecture

LangGraph requests are handled by nginx reverse proxy.
This gateway provides custom endpoints for models, MCP configuration, skills, and artifacts.
        """,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {
                "name": "auth",
                "description": "User authentication: register, login, token refresh, and logout",
            },
            {
                "name": "models",
                "description": "Operations for querying available AI models and their configurations",
            },
            {
                "name": "providers",
                "description": "Operations for listing provider models and validating API keys",
            },
            {
                "name": "agent",
                "description": "Inspect the resolved agent context (tools and skills)",
            },
            {
                "name": "mcp",
                "description": "Manage Model Context Protocol (MCP) server configurations",
            },
            {
                "name": "memory",
                "description": "Access and manage global memory data for personalized conversations",
            },
            {
                "name": "skills",
                "description": "Manage skills and their configurations",
            },
            {
                "name": "artifacts",
                "description": "Access and download thread artifacts and generated files",
            },
            {
                "name": "uploads",
                "description": "Upload and manage user files for threads",
            },
            {
                "name": "threads",
                "description": "Thread-level operations including message truncation",
            },
            {
                "name": "health",
                "description": "Health check and system status endpoints",
            },
        ],
    )

    # CORS is handled by nginx - no need for FastAPI middleware

    # Include routers
    # Auth API is mounted at /api/auth (must be first for public access)
    app.include_router(auth_router)

    # Models API is mounted at /api/models
    app.include_router(models.router)

    # Provider model discovery API
    app.include_router(providers.router)
    app.include_router(keys.router)

    # Agent context API is mounted at /api/agent
    app.include_router(agent.router)

    # MCP API is mounted at /api/mcp
    app.include_router(mcp.router)

    # Memory API is mounted at /api/memory
    app.include_router(memory.router)

    # Skills API is mounted at /api/skills
    app.include_router(skills.router)

    # Artifacts API is mounted at /api/threads/{thread_id}/artifacts
    app.include_router(artifacts.router)

    # Uploads API is mounted at /api/threads/{thread_id}/uploads
    app.include_router(uploads.router)

    # Threads API is mounted at /api/threads/{thread_id}
    app.include_router(threads.router)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """Health check endpoint.

        Returns service health status. When DATABASE_URL is configured,
        also checks database connectivity. When REDIS_URL is configured,
        also checks Redis connectivity.

        Returns:
            Service health status information with component checks.
        """
        from src.db.engine import check_db_connection, is_db_enabled
        from src.queue.redis_connection import check_redis_health, is_redis_available

        checks: dict[str, str] = {"gateway": "healthy"}

        if is_db_enabled():
            checks["database"] = check_db_connection()

        if is_redis_available():
            checks["redis"] = check_redis_health()

        all_healthy = all(v == "healthy" for v in checks.values())
        status = "healthy" if all_healthy else "degraded"

        return {"status": status, "service": "deer-flow-gateway", "checks": checks}

    return app


# Create app instance for uvicorn
app = create_app()
