from __future__ import annotations

import hashlib
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agents.credentials import Credentials, credentials_prompt_block, redact_values
from src.agents.process_runner import run_logged_process
from src.agents.provider import (
    agent_display_name,
    build_agent_command,
    normalize_agent_provider,
)
from src.agents.terminal import emit_json_event, emit_summary
from src.scraper_target import ScraperTarget
from src.utils import write_json, write_text


class DemoBreaker:
    def __init__(
        self,
        diagnostics_dir: Path,
        timeout: int,
        target: ScraperTarget,
        agent_provider: str = "openai",
        credentials: Credentials | None = None,
        break_command: str | None = None,
    ):
        self.diagnostics_dir = diagnostics_dir
        self.timeout = timeout
        self.agent_provider = normalize_agent_provider(agent_provider)
        self.target = target
        self.credentials = credentials
        self.break_command = break_command
        self.report_path = diagnostics_dir / "llm_break_report.json"
        self.events: list[dict[str, Any]] = []

    def run(self) -> None:
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        command = self._build_command()
        prompt = self._build_prompt(redacted=False)
        redacted_prompt = self._build_prompt(redacted=True)
        prompt_path = self.diagnostics_dir / "llm_break_prompt.md"
        log_path = self.diagnostics_dir / "llm_break.log"
        before = self._target_file_hashes()

        write_text(prompt_path, redacted_prompt)
        self._record(
            "llm_break_started",
            command=command,
            agent_provider=self.agent_provider,
            target=self.target.name,
            target_kind=self.target.kind,
            target_root=str(self.target.root_dir),
            credentials_provided=self.credentials is not None,
            prompt=str(prompt_path),
            log=str(log_path),
        )

        try:
            completed = run_logged_process(
                command=command,
                input_text=prompt,
                log_path=log_path,
                timeout=self.timeout,
                status_prefix="llm_break",
                task_title="LLM break demo",
                task_details={
                    "provider": agent_display_name(self.agent_provider),
                    "target": self.target.name,
                    "target_kind": self.target.kind,
                    "prompt": str(prompt_path),
                    "diagnostics": str(self.diagnostics_dir),
                    "credentials": "provided" if self.credentials else "not provided",
                },
                redact_values=redact_values(self.credentials),
                show_output_lines=True,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "TimeoutExpired":
                self._record("llm_break_timeout", timeout=self.timeout)
                raise RuntimeError(f"LLM break timed out. See {log_path}.") from exc
            self._record("llm_break_failed_before_finish", error=repr(exc))
            raise

        changed_project_files = self._changed_target_files(before)
        scraper_diff = self._scraper_diff()
        summary_path = self.diagnostics_dir / "llm_break_summary.md"
        write_text(
            summary_path,
            self._build_summary(
                changed_project_files=changed_project_files,
                scraper_diff=scraper_diff,
                provider=agent_display_name(self.agent_provider),
                elapsed_seconds=completed.elapsed_seconds,
                log_path=log_path,
            ),
        )
        emit_summary(
            "llm_break",
            "Break demo",
            {
                "provider": agent_display_name(self.agent_provider),
                "elapsed": f"{completed.elapsed_seconds:.1f}s",
                "returncode": completed.returncode,
                "changed_project_files": changed_project_files,
                "summary": str(summary_path),
                "log": str(log_path),
            },
        )
        self._record(
            "llm_break_finished",
            returncode=completed.returncode,
            stdout_chars=len(completed.stdout),
            stderr_chars=len(completed.stderr),
            elapsed_seconds=round(completed.elapsed_seconds, 1),
            agent_provider=self.agent_provider,
            changed_project_files=changed_project_files,
            summary=str(summary_path),
            scraper_diff=scraper_diff,
        )

        if completed.returncode != 0:
            raise RuntimeError(f"LLM break failed with exit code {completed.returncode}. See {log_path}.")

    def _record(self, event: str, **details: Any) -> None:
        entry = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **details,
        }
        self.events.append(entry)
        write_json(
            self.report_path,
            {
                "status": event,
                "diagnostics_dir": str(self.diagnostics_dir),
                "report_path": str(self.report_path),
                "events": self.events,
            },
        )
        emit_json_event("llm_break", event, **details)

    def _build_command(self) -> list[str]:
        if self.break_command:
            return shlex.split(self.break_command)
        return build_agent_command(self.agent_provider)

    def _build_prompt(self, redacted: bool) -> str:
        agent_name = agent_display_name(self.agent_provider)
        target_files = "\n".join(f"- {path}" for path in self.target.files)
        allowed_paths = "\n".join(f"- {path}" for path in self.target.allowed_paths)
        verification = " ".join(self.target.verification_command)
        return f"""You are preparing a controlled self-repair demo for MCP-PW-SCRAPPER.

Agent provider:
{agent_name}

Credentials:
{credentials_prompt_block(self.credentials, redacted=redacted)}

Introduce exactly one realistic scraper bug that will make:

{verification}

fail against the current source page: {self.target.source_url}

Scraper target:
- name: {self.target.name}
- kind: {self.target.kind}
- root: {self.target.root_dir}

Scraper files to inspect:
{target_files}

Allowed files to edit:
{allowed_paths}

Rules:
- You are running unattended from the host process; do not ask the user to approve MCP/tool calls.
- Edit only the allowed scraper target files listed above.
- Do not edit diagnostics, repair, notifier, runner, config, docs, output, or tests.
- Do not use --simulate-failure or add an explicit artificial exception.
- Prefer a realistic bug: a stale CSS selector, wrong DOM attribute, wrong mapping key, broken price/rating parsing, or URL mapping drift.
- Keep the code syntactically valid.
- Do not add comments that reveal the fix.
- After editing, run only: uv run python -m compileall main.py src
- Do not run the scraper and do not repair the bug.

In your final response, summarize:
- which file changed
- what kind of realistic scraper drift you introduced
- compile verification result
"""

    def _scraper_diff(self) -> str:
        completed = subprocess.run(
            ["git", "diff", "--", *(str(path) for path in self.target.allowed_paths)],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return ""
        return completed.stdout

    @staticmethod
    def _build_summary(
        changed_project_files: list[str],
        scraper_diff: str,
        provider: str,
        elapsed_seconds: float,
        log_path: Path,
    ) -> str:
        changed = "\n".join(f"- {path}" for path in changed_project_files) or "- none"
        diff = scraper_diff.strip() or "No scraper diff was available."
        return "\n".join(
            [
                "# LLM Break Summary",
                "",
                f"- Provider: {provider}",
                f"- Elapsed: {elapsed_seconds:.1f}s",
                f"- Log: {log_path}",
                "",
                "## Changed Files",
                "",
                changed,
                "",
                "## Scraper Diff",
                "",
                "```diff",
                diff,
                "```",
                "",
            ]
        )

    def _target_file_hashes(self) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for path in self.target.allowed_paths:
            if not path.exists():
                continue
            hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return hashes

    def _changed_target_files(self, before: dict[str, str]) -> list[str]:
        after = self._target_file_hashes()
        paths = sorted(set(before) | set(after))
        return [path for path in paths if before.get(path) != after.get(path)]
