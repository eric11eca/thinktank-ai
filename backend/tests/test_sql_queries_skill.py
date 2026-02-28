"""Unit tests for the sql-queries skill loading.

Verifies that the sql-queries skill is properly discovered, parsed,
and enabled by default for the agent's system prompt.
"""

from src.config.extensions_config import ExtensionsConfig
from src.skills.loader import load_skills


class TestSqlQueriesSkillLoading:
    """Verify the sql-queries skill is discoverable and enabled."""

    def test_skill_exists(self):
        """The sql-queries skill should be found in the public skills directory."""
        skills = load_skills(use_config=False)
        skill_names = [s.name for s in skills]
        assert "sql-queries" in skill_names, f"sql-queries not found in skills: {skill_names}"

    def test_skill_has_description(self):
        """The sql-queries skill should have a meaningful description."""
        skills = load_skills(use_config=False)
        sql_skill = next(s for s in skills if s.name == "sql-queries")
        assert sql_skill.description, "Skill description should not be empty"
        assert "sql" in sql_skill.description.lower(), "Description should mention SQL"

    def test_skill_category_is_public(self):
        """The sql-queries skill should be in the public category."""
        skills = load_skills(use_config=False)
        sql_skill = next(s for s in skills if s.name == "sql-queries")
        assert sql_skill.category == "public"

    def test_skill_file_exists(self):
        """The skill's SKILL.md file should exist on disk."""
        skills = load_skills(use_config=False)
        sql_skill = next(s for s in skills if s.name == "sql-queries")
        assert sql_skill.skill_file.exists(), f"SKILL.md not found at {sql_skill.skill_file}"

    def test_skill_enabled_by_default(self):
        """Public skills should be enabled by default when not listed in config."""
        config = ExtensionsConfig(mcp_servers={}, skills={})
        # sql-queries is not in the skills dict, so it should default to enabled for public
        assert config.is_skill_enabled("sql-queries", "public") is True

    def test_skill_enabled_when_explicitly_set(self):
        """The skill should respect explicit enabled=true in config."""
        from src.config.extensions_config import SkillStateConfig

        config = ExtensionsConfig(
            mcp_servers={},
            skills={"sql-queries": SkillStateConfig(enabled=True)},
        )
        assert config.is_skill_enabled("sql-queries", "public") is True

    def test_skill_disabled_when_explicitly_set(self):
        """The skill should respect explicit enabled=false in config."""
        from src.config.extensions_config import SkillStateConfig

        config = ExtensionsConfig(
            mcp_servers={},
            skills={"sql-queries": SkillStateConfig(enabled=False)},
        )
        assert config.is_skill_enabled("sql-queries", "public") is False

    def test_skill_content_mentions_postgresql(self):
        """The SKILL.md content should include PostgreSQL reference material."""
        skills = load_skills(use_config=False)
        sql_skill = next(s for s in skills if s.name == "sql-queries")
        content = sql_skill.skill_file.read_text()
        assert "PostgreSQL" in content, "SKILL.md should contain PostgreSQL dialect reference"
        assert "EXPLAIN" in content, "SKILL.md should contain EXPLAIN guidance"
