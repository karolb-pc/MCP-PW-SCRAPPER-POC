from __future__ import annotations

import hashlib
import shlex
import subprocess
from pathlib import Path

from src.notification.mock_email import MockEmailNotifier
from src.agents.credentials import Credentials, credentials_prompt_block, redact_values
from src.agents.process_runner import run_logged_process
from src.agents.provider import (
    agent_display_name,
    agent_log_name,
    build_agent_command,
)
from src.agents.terminal import emit_summary
from src.utils import write_text


class CodexRepairAgent:
    agent_provider = "openai"

    def __init__(
        self,
        diagnostics_dir: Path,
        repair_timeout: int,
        notifier: MockEmailNotifier,
        credentials: Credentials | None = None,
        repair_command: str | None = None,
    ):
        self.diagnostics_dir = diagnostics_dir
        self.repair_timeout = repair_timeout
        self.notifier = notifier
        self.credentials = credentials
        self.repair_command = repair_command

    def run(self) -> dict[str, object]:
        repair_prompt_path = self.diagnostics_dir / "repair_prompt.md"
        if not repair_prompt_path.exists():
            raise RuntimeError(f"Repair prompt does not exist: {repair_prompt_path}")

        command = self._build_repair_command()
        prompt = self._build_runtime_prompt(repair_prompt_path.read_text())
        log_path = self.diagnostics_dir / agent_log_name(self.agent_provider, "repair")
        changed_files_before = self._changed_files()
        file_hashes_before = self._project_file_hashes()
        agent_name = agent_display_name(self.agent_provider)

        self.notifier.send(
            subject="[MCP-PW-SCRAPPER] Repair attempt started",
            body=(
                "The scraper failed and auto-repair is starting.\n\n"
                f"Agent provider: {agent_name}\n"
                f"Credentials provided: {self.credentials is not None}\n"
                f"Diagnostics: {self.diagnostics_dir.resolve()}\n"
                f"Repair prompt: {repair_prompt_path.resolve()}\n"
                f"Agent log: {log_path.resolve()}\n"
            ),
            metadata={
                "agent_provider": self.agent_provider,
                "diagnostics_dir": str(self.diagnostics_dir),
                "command": command,
            },
        )

        try:
            completed = run_logged_process(
                command=command,
                input_text=prompt,
                log_path=log_path,
                timeout=self.repair_timeout,
                status_prefix=f"{self.agent_provider}_repair",
                task_title="Repair agent",
                task_details={
                    "provider": agent_name,
                    "prompt": str(repair_prompt_path),
                    "diagnostics": str(self.diagnostics_dir),
                    "credentials": "provided" if self.credentials else "not provided",
                },
                redact_values=redact_values(self.credentials),
                show_output_lines=True,
            )
        except TimeoutError as exc:
            raise RuntimeError(f"Repair agent timed out. See {log_path}.") from exc
        except Exception as exc:
            if exc.__class__.__name__ == "TimeoutExpired":
                raise RuntimeError(f"Repair agent timed out. See {log_path}.") from exc
            raise

        if completed.returncode != 0:
            raise RuntimeError(
                f"Repair agent failed with exit code {completed.returncode}. "
                f"See {log_path}."
            )

        self.notifier.send(
            subject="[MCP-PW-SCRAPPER] Repair agent finished",
            body=(
                f"{agent_name} repair agent finished with exit code 0.\n\n"
                "The scraper pipeline will now be retried.\n"
                f"Agent log: {log_path.resolve()}\n"
            ),
            metadata={
                "agent_provider": self.agent_provider,
                "diagnostics_dir": str(self.diagnostics_dir),
                "log": str(log_path),
            },
        )
        changed_files_after = self._changed_files()
        changed_files_during_repair = sorted(set(changed_files_after) - set(changed_files_before))
        changed_project_files = self._changed_project_files(file_hashes_before)
        summary_path = self.diagnostics_dir / "repair_summary.md"
        summary_details = {
            "provider": agent_name,
            "elapsed": f"{completed.elapsed_seconds:.1f}s",
            "returncode": completed.returncode,
            "changed_project_files": changed_project_files,
            "changed_files_during_repair": changed_files_during_repair,
            "dirty_files_after_repair": changed_files_after,
            "credentials_used": self.credentials is not None,
            "log": str(log_path),
            "summary": str(summary_path),
        }
        write_text(summary_path, self._build_summary(summary_details))
        emit_summary(
            f"{self.agent_provider}_repair",
            "Repair",
            {
                "provider": agent_name,
                "elapsed": f"{completed.elapsed_seconds:.1f}s",
                "returncode": completed.returncode,
                "changed_project_files": changed_project_files,
                "changed_files_during_repair": changed_files_during_repair,
                "credentials_used": self.credentials is not None,
                "log": str(log_path),
                "summary": str(summary_path),
            },
        )
        return {
            "agent_provider": self.agent_provider,
            "command": command,
            "log": str(log_path),
            "summary": str(summary_path),
            "returncode": completed.returncode,
            "stdout_chars": len(completed.stdout),
            "stderr_chars": len(completed.stderr),
            "elapsed_seconds": round(completed.elapsed_seconds, 1),
            "changed_files_before_repair": changed_files_before,
            "changed_files_after_repair": changed_files_after,
            "changed_files_during_repair": changed_files_during_repair,
            "changed_project_files": changed_project_files,
            "credentials_used": self.credentials is not None,
        }

    def _build_repair_command(self) -> list[str]:
        if self.repair_command:
            return shlex.split(self.repair_command)
        return build_agent_command(self.agent_provider)

    def _build_runtime_prompt(self, saved_prompt: str) -> str:
        return "\n\n".join(
            [
                saved_prompt,
                "Credential and login instructions:",
                credentials_prompt_block(self.credentials, redacted=False),
            ]
        )

    @staticmethod
    def _changed_files() -> list[str]:
        completed = subprocess.run(
            ["git", "diff", "--name-only"],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return []
        return [line for line in completed.stdout.splitlines() if line.strip()]

    @staticmethod
    def _project_file_hashes() -> dict[str, str]:
        paths = [
            Path("main.py"),
            *Path("src").rglob("*.py"),
            *Path("scrapers").rglob("*.py"),
            *Path("scrapers").rglob("scraper_target.json"),
        ]
        hashes: dict[str, str] = {}
        for path in paths:
            if not path.exists():
                continue
            hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return hashes

    @classmethod
    def _changed_project_files(cls, before: dict[str, str]) -> list[str]:
        after = cls._project_file_hashes()
        paths = sorted(set(before) | set(after))
        return [path for path in paths if before.get(path) != after.get(path)]

    @staticmethod
    def _build_summary(details: dict[str, object]) -> str:
        lines = [
            "# Repair Summary",
            "",
            f"- Provider: {details['provider']}",
            f"- Elapsed: {details['elapsed']}",
            f"- Return code: {details['returncode']}",
            f"- Credentials used: {details['credentials_used']}",
            f"- Log: {details['log']}",
            "",
            "## Changed Project Files",
            "",
        ]
        changed = details.get("changed_project_files")
        if isinstance(changed, list) and changed:
            lines.extend(f"- {path}" for path in changed)
        else:
            lines.append("- none")
        lines.extend(["", "## Changed Files During Repair", ""])
        changed_during = details.get("changed_files_during_repair")
        if isinstance(changed_during, list) and changed_during:
            lines.extend(f"- {path}" for path in changed_during)
        else:
            lines.append("- none")
        lines.extend(["", "## Dirty Files After Repair", ""])
        dirty_after = details.get("dirty_files_after_repair")
        if isinstance(dirty_after, list) and dirty_after:
            lines.extend(f"- {path}" for path in dirty_after)
        else:
            lines.append("- none")
        lines.append("")
        return "\n".join(lines)


class ClaudeRepairAgent(CodexRepairAgent):
    agent_provider = "claude"
