from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Sequence

from ..core.config import Profile
from .consul_backend import ConsulBackendError


ENV_NAME = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")
RAKE_TASK = re.compile(r"\A[A-Za-z0-9_.:-]+\Z")
RAKE_TASK_LINE = re.compile(r"^rake\s+(\S+?)(?:\s+#\s?(.*))?$")


class ConsulRuntimeBackend:
    """Run the application's native Rails and Rake interfaces without a shell."""

    def __init__(self, profile: Profile, *, timeout: float = 300.0):
        self.profile = profile
        self.timeout = timeout
        if not profile.container and not profile.app_path:
            raise ConsulBackendError(
                "This profile needs --container or --app-path for runtime commands"
            )

    def rake_tasks(self) -> dict[str, Any]:
        result = self.run(["bundle", "exec", "rake", "-AT"])
        tasks: list[dict[str, str | None]] = []
        for line in result["stdout"].splitlines():
            match = RAKE_TASK_LINE.match(line.strip())
            if not match:
                continue
            declaration, description = match.groups()
            name, arguments = self._split_task_declaration(declaration)
            tasks.append(
                {
                    "name": name,
                    "arguments": arguments,
                    "description": description or None,
                }
            )
        return {
            "count": len(tasks),
            "tasks": tasks,
            "runtime": result["runtime"],
        }

    def run_rake(
        self,
        task: str,
        *,
        arguments: Sequence[str] = (),
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if not RAKE_TASK.fullmatch(task):
            raise ConsulBackendError(f"Invalid Rake task name: {task}")
        declaration = task
        if arguments:
            declaration += (
                "["
                + ",".join(self._escape_rake_argument(item) for item in arguments)
                + "]"
            )
        return self.run(
            ["bundle", "exec", "rake", declaration],
            env=env,
            timeout=timeout,
        )

    def rails_runner(
        self,
        code: str,
        *,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if not code.strip():
            raise ConsulBackendError("Rails runner code cannot be empty")
        return self.run(
            ["bundle", "exec", "rails", "runner", code],
            env=env,
            timeout=timeout,
        )

    def run(
        self,
        argv: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        values = {str(key): str(value) for key, value in (env or {}).items()}
        invalid = [key for key in values if not ENV_NAME.fullmatch(key)]
        if invalid:
            raise ConsulBackendError(f"Invalid environment variable names: {invalid}")

        if self.profile.container:
            command = ["docker", "exec", "-w", self.profile.container_workdir]
            for key, value in values.items():
                command.extend(["-e", f"{key}={value}"])
            command.extend([self.profile.container, *argv])
            cwd = None
            runtime = {
                "type": "docker",
                "container": self.profile.container,
                "workdir": self.profile.container_workdir,
                "argv": list(argv),
                "environment": sorted(values),
            }
            process_env = None
        else:
            cwd = str(Path(self.profile.app_path or "").resolve())
            command = list(argv)
            process_env = {**os.environ, **values}
            runtime = {
                "type": "local",
                "workdir": cwd,
                "argv": list(argv),
                "environment": sorted(values),
            }

        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=process_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout or self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ConsulBackendError(
                f"Runtime executable was not found: {exc}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ConsulBackendError(f"Runtime command timed out: {exc}") from exc

        result = {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "runtime": runtime,
        }
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ConsulBackendError(
                f"CONSUL runtime command failed with exit code {completed.returncode}: {detail[-2000:]}"
            )
        return result

    @staticmethod
    def _escape_rake_argument(value: str) -> str:
        return str(value).replace("\\", "\\\\").replace(",", "\\,").replace("]", "\\]")

    @staticmethod
    def _split_task_declaration(value: str) -> tuple[str, str | None]:
        if "[" not in value:
            return value, None
        name, arguments = value.split("[", 1)
        return name, arguments.rstrip("]") or None
