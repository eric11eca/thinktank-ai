"""Sandbox implementation backed by the Daytona cloud sandbox SDK."""

import logging

from daytona import Sandbox as DaytonaSandboxInstance

from src.sandbox.sandbox import Sandbox

logger = logging.getLogger(__name__)


class DaytonaSandbox(Sandbox):
    """Sandbox implementation using the Daytona cloud sandbox.

    Wraps a ``daytona.Sandbox`` instance and exposes it through the
    project's abstract ``Sandbox`` interface so that the agent can
    execute commands, read/write files, and list directories inside
    a remote Daytona workspace.
    """

    def __init__(self, id: str, daytona_sandbox: DaytonaSandboxInstance):
        super().__init__(id)
        self._sandbox = daytona_sandbox

    @property
    def daytona_sandbox(self) -> DaytonaSandboxInstance:
        return self._sandbox

    def execute_command(self, command: str) -> str:
        try:
            response = self._sandbox.process.exec(command, timeout=600)
            output = response.result or ""
            if response.exit_code != 0:
                output += f"\nExit Code: {response.exit_code}"
            return output if output else "(no output)"
        except Exception as e:
            logger.error("Failed to execute command in Daytona sandbox: %s", e)
            return f"Error: {e}"

    def read_file(self, path: str) -> str:
        try:
            content: bytes = self._sandbox.fs.download_file(path)
            return content.decode("utf-8")
        except Exception as e:
            logger.error("Failed to read file in Daytona sandbox: %s", e)
            return f"Error: {e}"

    def list_dir(self, path: str, max_depth: int = 2) -> list[str]:
        try:
            response = self._sandbox.process.exec(
                f"find {path} -maxdepth {max_depth} -type f -o -type d 2>/dev/null | head -500"
            )
            output = response.result or ""
            if output:
                return [line.strip() for line in output.strip().split("\n") if line.strip()]
            return []
        except Exception as e:
            logger.error("Failed to list directory in Daytona sandbox: %s", e)
            return []

    def write_file(self, path: str, content: str, append: bool = False) -> None:
        try:
            if append:
                existing = self.read_file(path)
                if not existing.startswith("Error:"):
                    content = existing + content
            self._sandbox.fs.upload_file(content.encode("utf-8"), path)
        except Exception as e:
            logger.error("Failed to write file in Daytona sandbox: %s", e)
            raise

    def update_file(self, path: str, content: bytes) -> None:
        try:
            self._sandbox.fs.upload_file(content, path)
        except Exception as e:
            logger.error("Failed to update file in Daytona sandbox: %s", e)
            raise
