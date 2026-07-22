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


class SourceAuditor:
    def __init__(
        self,
        diagnostics_dir: Path,
        timeout: int,
        browser: str,
        fix: bool,
        target: ScraperTarget,
        source_url: str | None = None,
        credentials: Credentials | None = None,
        agent_provider: str = "openai",
        audit_command: str | None = None,
    ):
        self.diagnostics_dir = diagnostics_dir
        self.timeout = timeout
        self.target = target
        self.source_url = source_url or self.target.source_url
        self.browser = browser
        self.fix = fix
        self.credentials = credentials
        self.agent_provider = normalize_agent_provider(agent_provider)
        self.audit_command = audit_command
        self.report_path = diagnostics_dir / "source_audit_report.json"
        self.events: list[dict[str, Any]] = []

    def run(self) -> None:
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        command = self._build_command()
        prompt = self._build_prompt(redacted=False)
        redacted_prompt = self._build_prompt(redacted=True)
        prompt_path = self.diagnostics_dir / "source_audit_prompt.md"
        log_path = self.diagnostics_dir / "source_audit.log"
        before = self._target_file_hashes()

        write_text(prompt_path, redacted_prompt)
        self._record(
            "source_audit_started",
            command=command,
            source_url=self.source_url,
            target=self.target.name,
            target_kind=self.target.kind,
            target_root=str(self.target.root_dir),
            browser=self.browser,
            fix=self.fix,
            agent_provider=self.agent_provider,
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
                status_prefix="source_audit",
                task_title="Source audit agent",
                task_details={
                    "provider": agent_display_name(self.agent_provider),
                    "mode": "fix" if self.fix else "inspect",
                    "target": self.target.name,
                    "target_kind": self.target.kind,
                    "source_url": self.source_url,
                    "prompt": str(prompt_path),
                    "diagnostics": str(self.diagnostics_dir),
                    "credentials": "provided" if self.credentials else "not provided",
                },
                redact_values=redact_values(self.credentials),
                show_output_lines=True,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "TimeoutExpired":
                self._record("source_audit_timeout", timeout=self.timeout)
                raise RuntimeError(f"Source audit timed out. See {log_path}.") from exc
            self._record("source_audit_failed_before_finish", error=repr(exc))
            raise

        changed_project_files = self._changed_target_files(before)
        summary_path = self.diagnostics_dir / "source_audit_summary.md"
        write_text(
            summary_path,
            self._build_summary(
                changed_project_files=changed_project_files,
                provider=agent_display_name(self.agent_provider),
                mode="fix" if self.fix else "inspect",
                elapsed_seconds=completed.elapsed_seconds,
                returncode=completed.returncode,
                log_path=log_path,
            ),
        )
        emit_summary(
            "source_audit",
            "Source audit",
            {
                "provider": agent_display_name(self.agent_provider),
                "mode": "fix" if self.fix else "inspect",
                "elapsed": f"{completed.elapsed_seconds:.1f}s",
                "returncode": completed.returncode,
                "changed_project_files": changed_project_files,
                "summary": str(summary_path),
                "log": str(log_path),
            },
        )
        self._record(
            "source_audit_finished",
            returncode=completed.returncode,
            stdout_chars=len(completed.stdout),
            stderr_chars=len(completed.stderr),
            elapsed_seconds=round(completed.elapsed_seconds, 1),
            changed_project_files=changed_project_files,
            summary=str(summary_path),
        )

        if completed.returncode != 0:
            raise RuntimeError(
                f"Source audit failed with exit code {completed.returncode}. See {log_path}."
            )

        if self.fix:
            self._run_fresh_verification()

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
        emit_json_event("source_audit", event, **details)

    def _build_command(self) -> list[str]:
        if self.audit_command:
            return shlex.split(self.audit_command)
        return build_agent_command(self.agent_provider)

    def _run_fresh_verification(self) -> None:
        verification_diagnostics_dir = self.diagnostics_dir / "fresh-verification"
        command = list(self.target.verification_command)
        if "--diagnostics-dir" not in command:
            command.extend(["--diagnostics-dir", str(verification_diagnostics_dir)])
        self._record("source_audit_fresh_verification_started", command=command)
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            cwd=Path.cwd(),
            check=False,
        )
        write_text(
            self.diagnostics_dir / "source_audit_fresh_verification.log",
            "\n".join(
                [
                    "$ " + " ".join(command),
                    "",
                    "## stdout",
                    self._redact(completed.stdout),
                    "",
                    "## stderr",
                    self._redact(completed.stderr),
                    "",
                    f"## returncode\n{completed.returncode}\n",
                ]
            ),
        )
        self._record(
            "source_audit_fresh_verification_finished",
            returncode=completed.returncode,
            stdout_chars=len(completed.stdout),
            stderr_chars=len(completed.stderr),
            log=str(self.diagnostics_dir / "source_audit_fresh_verification.log"),
            diagnostics_dir=str(verification_diagnostics_dir),
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Fresh source-audit verification failed after fix. "
                f"See {self.diagnostics_dir / 'source_audit_fresh_verification.log'}."
            )

    def _build_prompt(self, redacted: bool) -> str:
        mode = "inspect and patch the scraper if needed" if self.fix else "inspect only; do not edit files"
        credentials_block = credentials_prompt_block(self.credentials, redacted=redacted)
        allowed_paths = "\n".join(f"- {path}" for path in self.target.allowed_paths)
        target_files = "\n".join(f"- {path}" for path in self.target.files)
        write_policy = (
            "If the current scraper code is stale or incompatible with the source HTML, patch only the allowed scraper target files listed below."
            if self.fix
            else "Do not edit files. Produce findings only."
        )
        verification_command = " ".join(self.target.verification_command)
        agent_name = agent_display_name(self.agent_provider)
        return f"""You are running a proactive source audit for MCP-PW-SCRAPPER.

Goal:
- Open and inspect the live source page.
- Analyze the current HTML/DOM and important product-card selectors.
- Compare the source page with the scraper target files listed below.
- {mode}.

Agent provider:
{agent_name}

Source URL:
{self.source_url}

Scraper target:
- name: {self.target.name}
- kind: {self.target.kind}
- root: {self.target.root_dir}

Scraper files to inspect:
{target_files}

Allowed files to patch:
{allowed_paths}

Browser mode for local verification:
{self.browser}

Credentials:
{credentials_block}

Rules:
- You must use Playwright MCP/browser MCP to inspect the live source page before making audit conclusions.
- If browser MCP is not available in your agent environment, stop and report that Playwright MCP is required.
- You are running unattended from the host process; do not ask the user to approve MCP/tool calls.
- Use credentials only if the source page requires login.
- Never print, save, or echo credentials.
- Do not change diagnostics, repair, notifier, runner, config, docs, output files, or unrelated code.
- {write_policy}
- Keep changes minimal and specific to source-page compatibility.
- If you patch code, run: {verification_command}
- Also run: uv run python -m compileall main.py src
- Do not run --auto-repair from inside this audit.

Expected data contract:
- Preserve the selected scraper's existing output schema unless the source changed and a minimal schema correction is required.
- The verification command above is the source of truth for whether the scraper is healthy.
- Keep the class-based Extract / Transform / Validate / Load split intact.

Final response requirements:
- source page status
- whether login was needed
- selectors/DOM facts checked
- files changed, if any
- root cause, if a fix was needed
- verification commands and results
"""

    def _redact(self, value: str) -> str:
        if self.credentials is None:
            return value
        redacted = value
        for secret in self.credentials:
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        return redacted

    @staticmethod
    def _build_summary(
        changed_project_files: list[str],
        provider: str,
        mode: str,
        elapsed_seconds: float,
        returncode: int,
        log_path: Path,
    ) -> str:
        changed = "\n".join(f"- {path}" for path in changed_project_files) or "- none"
        return "\n".join(
            [
                "# Source Audit Summary",
                "",
                f"- Provider: {provider}",
                f"- Mode: {mode}",
                f"- Elapsed: {elapsed_seconds:.1f}s",
                f"- Return code: {returncode}",
                f"- Log: {log_path}",
                "",
                "## Changed Project Files",
                "",
                changed,
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
