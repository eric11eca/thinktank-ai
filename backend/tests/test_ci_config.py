"""Tests for CI/CD pipeline configuration files.

Validates that GitHub Actions workflow YAML files are syntactically correct,
contain required jobs, and have properly configured triggers.
"""

from pathlib import Path

import yaml
import pytest


WORKFLOWS_DIR = Path(__file__).parent.parent.parent / ".github" / "workflows"


def _load_workflow(name: str) -> dict:
    """Load and parse a GitHub Actions workflow YAML file."""
    path = WORKFLOWS_DIR / name
    assert path.exists(), f"Workflow file not found: {path}"
    with open(path) as f:
        return yaml.safe_load(f)


def _get_triggers(workflow: dict) -> dict:
    """Get the triggers ('on' key) from a workflow.

    PyYAML parses the YAML key 'on' as boolean True, so we need to
    check for both 'on' (string) and True (boolean) as keys.
    """
    return workflow.get("on") or workflow.get(True) or {}


class TestCIWorkflow:
    """Tests for .github/workflows/ci.yml."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.workflow = _load_workflow("ci.yml")

    def test_workflow_parses_as_valid_yaml(self):
        """ci.yml should parse without errors."""
        assert self.workflow is not None
        assert isinstance(self.workflow, dict)

    def test_workflow_has_name(self):
        """Workflow should have a human-readable name."""
        assert "name" in self.workflow
        assert isinstance(self.workflow["name"], str)

    def test_triggers_on_push_and_pr(self):
        """CI should trigger on push to main and pull requests."""
        triggers = _get_triggers(self.workflow)
        assert "push" in triggers or "pull_request" in triggers

    def test_has_concurrency_group(self):
        """Workflow should have concurrency settings to avoid duplicate runs."""
        assert "concurrency" in self.workflow
        assert "cancel-in-progress" in self.workflow["concurrency"]

    def test_lint_job_exists(self):
        """CI pipeline should have a lint stage."""
        jobs = self.workflow.get("jobs", {})
        assert "lint" in jobs, "Missing 'lint' job in CI pipeline"

    def test_typecheck_job_exists(self):
        """CI pipeline should have a type check stage."""
        jobs = self.workflow.get("jobs", {})
        assert "typecheck" in jobs, "Missing 'typecheck' job in CI pipeline"

    def test_unit_tests_job_exists(self):
        """CI pipeline should have a unit tests stage."""
        jobs = self.workflow.get("jobs", {})
        assert "unit-tests" in jobs, "Missing 'unit-tests' job in CI pipeline"

    def test_build_images_job_exists(self):
        """CI pipeline should have a Docker image build stage."""
        jobs = self.workflow.get("jobs", {})
        assert "build-images" in jobs, "Missing 'build-images' job in CI pipeline"

    def test_e2e_smoke_job_exists(self):
        """CI pipeline should have an E2E smoke test stage."""
        jobs = self.workflow.get("jobs", {})
        assert "e2e-smoke" in jobs, "Missing 'e2e-smoke' job in CI pipeline"

    def test_job_dependency_chain(self):
        """Jobs should have proper dependency chain: lint → typecheck/tests → build → e2e."""
        jobs = self.workflow.get("jobs", {})

        # typecheck depends on lint
        typecheck_needs = jobs.get("typecheck", {}).get("needs", [])
        assert "lint" in typecheck_needs, "typecheck should depend on lint"

        # unit-tests depends on lint
        tests_needs = jobs.get("unit-tests", {}).get("needs", [])
        assert "lint" in tests_needs, "unit-tests should depend on lint"

        # build-images depends on unit-tests and typecheck
        build_needs = jobs.get("build-images", {}).get("needs", [])
        assert "unit-tests" in build_needs, "build-images should depend on unit-tests"
        assert "typecheck" in build_needs, "build-images should depend on typecheck"

    def test_all_jobs_have_timeout(self):
        """All jobs should have a timeout to prevent hung runs."""
        jobs = self.workflow.get("jobs", {})
        for name, job in jobs.items():
            assert "timeout-minutes" in job, f"Job '{name}' is missing timeout-minutes"

    def test_all_jobs_skip_drafts(self):
        """All jobs should skip draft PRs."""
        jobs = self.workflow.get("jobs", {})
        for name, job in jobs.items():
            if_condition = job.get("if", "")
            assert "draft == false" in if_condition, (
                f"Job '{name}' should skip draft PRs"
            )


class TestDockerPublishWorkflow:
    """Tests for .github/workflows/docker-publish.yml."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.workflow = _load_workflow("docker-publish.yml")

    def test_workflow_parses(self):
        assert self.workflow is not None

    def test_triggers_on_push_to_main(self):
        triggers = _get_triggers(self.workflow)
        push_config = triggers.get("push", {})
        branches = push_config.get("branches", [])
        assert "main" in branches

    def test_triggers_on_tag_push(self):
        triggers = _get_triggers(self.workflow)
        push_config = triggers.get("push", {})
        tags = push_config.get("tags", [])
        assert any("v*" in tag for tag in tags), "Should trigger on version tags"

    def test_supports_manual_dispatch(self):
        triggers = _get_triggers(self.workflow)
        assert "workflow_dispatch" in triggers

    def test_uses_ghcr_registry(self):
        env = self.workflow.get("env", {})
        assert env.get("REGISTRY") == "ghcr.io"

    def test_builds_all_images(self):
        """Should build gateway, nginx, and backup images."""
        jobs = self.workflow.get("jobs", {})
        build_job = jobs.get("build-and-push", {})
        strategy = build_job.get("strategy", {})
        matrix = strategy.get("matrix", {})
        includes = matrix.get("include", [])
        image_names = {item["image"] for item in includes}
        assert "gateway" in image_names
        assert "nginx" in image_names
        assert "backup" in image_names

    def test_has_packages_write_permission(self):
        """Job must have packages:write to push to GHCR."""
        jobs = self.workflow.get("jobs", {})
        build_job = jobs.get("build-and-push", {})
        perms = build_job.get("permissions", {})
        assert perms.get("packages") == "write"


class TestDeployWorkflow:
    """Tests for .github/workflows/deploy.yml."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.workflow = _load_workflow("deploy.yml")

    def test_workflow_parses(self):
        assert self.workflow is not None

    def test_manual_dispatch_only(self):
        """Deploy should only trigger manually (not on push/PR)."""
        triggers = _get_triggers(self.workflow)
        assert "workflow_dispatch" in triggers
        # Should NOT auto-deploy on push
        assert "push" not in triggers
        assert "pull_request" not in triggers

    def test_environment_input_choices(self):
        """Should offer staging and production environments."""
        inputs = (
            _get_triggers(self.workflow)
            .get("workflow_dispatch", {})
            .get("inputs", {})
        )
        env_input = inputs.get("environment", {})
        options = env_input.get("options", [])
        assert "staging" in options
        assert "production" in options

    def test_uses_github_environment(self):
        """Deploy job should use GitHub Environments for secrets."""
        jobs = self.workflow.get("jobs", {})
        deploy_job = jobs.get("deploy", {})
        assert "environment" in deploy_job

    def test_no_concurrent_deploys_to_same_env(self):
        """Concurrent deploys to the same environment should be prevented."""
        concurrency = self.workflow.get("concurrency", {})
        group = concurrency.get("group", "")
        assert "environment" in group or "inputs" in group


class TestAllWorkflows:
    """Cross-cutting tests for all workflow files."""

    def test_all_workflow_files_are_valid_yaml(self):
        """All .yml files in .github/workflows/ should be valid YAML."""
        if not WORKFLOWS_DIR.exists():
            pytest.skip("No workflows directory found")

        for yml_file in WORKFLOWS_DIR.glob("*.yml"):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            assert isinstance(data, dict), f"{yml_file.name} is not a valid workflow"
            # PyYAML parses 'on' as boolean True
            assert "on" in data or True in data, f"{yml_file.name} has no trigger ('on' key)"
            assert "jobs" in data, f"{yml_file.name} has no jobs"

    def test_no_hardcoded_secrets(self):
        """Workflow files should not contain hardcoded secrets."""
        if not WORKFLOWS_DIR.exists():
            pytest.skip("No workflows directory found")

        secret_patterns = [
            "ghp_",  # GitHub personal access tokens
            "sk-",   # OpenAI API keys
            "AKIA",  # AWS access keys
        ]

        for yml_file in WORKFLOWS_DIR.glob("*.yml"):
            content = yml_file.read_text()
            for pattern in secret_patterns:
                assert pattern not in content, (
                    f"{yml_file.name} contains potential hardcoded secret: {pattern}"
                )
