from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

from src.agents.credentials import Credentials
from src.agents.repair import ClaudeRepairAgent, CodexRepairAgent
from src.notification.mock_email import MockEmailNotifier
from src.scraper_target import ScraperTarget
from src.utils import write_text


class TargetAutoRepairRunner:
    def __init__(
        self,
        target: ScraperTarget,
        diagnostics_dir: Path,
        notifier: MockEmailNotifier,
        repair_attempts: int,
        repair_timeout: int,
        agent_provider: str,
        credentials: Credentials | None,
        repair_command: str | None,
    ):
        self.target = target
        self.diagnostics_dir = diagnostics_dir
        self.notifier = notifier
        self.repair_attempts = repair_attempts
        self.repair_timeout = repair_timeout
        self.agent_provider = agent_provider
        self.credentials = credentials
        self.repair_command = repair_command

    async def run(self, run_once: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
        last_error: BaseException | None = None
        for attempt in range(self.repair_attempts + 1):
            try:
                return await run_once()
            except Exception as exc:
                last_error = exc
                self._write_repair_prompt(exc)
                if attempt >= self.repair_attempts:
                    raise
                self._build_repair_agent().run()
        assert last_error is not None
        raise last_error

    def _build_repair_agent(self):
        kwargs = {
            "diagnostics_dir": self.diagnostics_dir,
            "repair_timeout": self.repair_timeout,
            "notifier": self.notifier,
            "credentials": self.credentials,
            "repair_command": self.repair_command,
        }
        if self.agent_provider == "claude":
            return ClaudeRepairAgent(**kwargs)
        return CodexRepairAgent(**kwargs)

    def _write_repair_prompt(self, error: BaseException) -> None:
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        files = "\n".join(f"- {path}" for path in self.target.files)
        allowed_paths = "\n".join(f"- {path}" for path in self.target.allowed_paths)
        verification = " ".join(self.target.verification_command)
        write_text(
            self.diagnostics_dir / "repair_prompt.md",
            f"""Analyze and repair this MCP-PW-SCRAPPER scraper target.

The scraper failed during an automated run.

Scraper target:
- name: {self.target.name}
- kind: {self.target.kind}
- root: {self.target.root_dir}
- source_url: {self.target.source_url}

Scraper files to inspect:
{files}

Allowed files to patch:
{allowed_paths}

Rules:
- Use Playwright MCP/browser MCP to inspect the live source page before patching scraper code.
- You are running unattended from the host process; do not ask the user to approve MCP/tool calls.
- Patch only the allowed files listed above.
- Keep the existing Extract / Transform / Load architecture.
- Do not change unrelated source files, docs, diagnostics, notifications, or generated outputs.
- Do not print, save, or echo credentials.

After patching, run:
{verification}

Also run:
uv run python -m compileall main.py src

Original error:
{repr(error)}
""",
        )
