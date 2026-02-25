import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.config.app_config import get_app_config
from src.skills import load_skills
from src.tools import get_available_tools

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["agent"])


class ToolSummary(BaseModel):
    """Summary of a tool available to the agent."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")


class SkillSummary(BaseModel):
    """Summary of an enabled skill available to the agent."""

    name: str = Field(..., description="Skill name")
    description: str = Field(..., description="Skill description")


class AgentContextResponse(BaseModel):
    """Response model for the agent context panel."""

    tools: list[ToolSummary]
    skills: list[SkillSummary]
    model_name: str | None = Field(None, description="Resolved model name")
    subagent_enabled: bool = Field(..., description="Whether subagent tool is enabled")


def _resolve_model_name(model_name: str | None) -> str | None:
    if model_name:
        return model_name
    app_config = get_app_config()
    if app_config.models:
        return app_config.models[0].name
    return None


@router.get(
    "/agent/context",
    response_model=AgentContextResponse,
    summary="Get agent context",
    description="Retrieve the currently enabled skills and resolved tool list for the agent.",
)
async def get_agent_context(
    model_name: str | None = Query(None, description="Model name to resolve available tools"),
    subagent_enabled: bool | None = Query(
        None,
        description="Whether to include the subagent tool in the tool list",
    ),
) -> AgentContextResponse:
    try:
        resolved_model_name = _resolve_model_name(model_name)
        resolved_subagent_enabled = bool(subagent_enabled) if subagent_enabled is not None else False
        tools = get_available_tools(
            model_name=resolved_model_name,
            subagent_enabled=resolved_subagent_enabled,
        )
        tool_items: list[ToolSummary] = []
        seen_tools: set[str] = set()
        for tool in tools:
            name = tool.name
            if name in seen_tools:
                continue
            seen_tools.add(name)
            description = getattr(tool, "description", "") or ""
            tool_items.append(ToolSummary(name=name, description=description))

        skills = load_skills(enabled_only=True)
        skill_items = [SkillSummary(name=skill.name, description=skill.description) for skill in skills]

        return AgentContextResponse(
            tools=tool_items,
            skills=skill_items,
            model_name=resolved_model_name,
            subagent_enabled=resolved_subagent_enabled,
        )
    except Exception as e:
        logger.error("Failed to build agent context response", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load agent context: {str(e)}")
