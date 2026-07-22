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
    agent_log_name,
    build_agent_command,
    normalize_agent_provider,
)
from src.agents.terminal import emit_json_event, emit_summary
from src.scraper_target import ScraperTarget
from src.utils import write_json, write_text


class SemiDiscoveryExtender:
    def __init__(
        self,
        target: ScraperTarget,
        requested_data: str,
        diagnostics_dir: Path,
        timeout: int,
        verify: bool,
        credentials: Credentials | None = None,
        agent_provider: str = "openai",
        extend_command: str | None = None,
    ):
        self.target = target
        self.requested_data = requested_data
        self.diagnostics_dir = diagnostics_dir
        self.timeout = timeout
        self.verify = verify
        self.credentials = credentials
        self.agent_provider = normalize_agent_provider(agent_provider)
        self.extend_command = extend_command
        self.report_path = diagnostics_dir / "semi_discovery_report.json"
        self.events: list[dict[str, Any]] = []

    def run(self) -> None:
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        command = self._build_command()
        prompt = self._build_prompt(redacted=False)
        redacted_prompt = self._build_prompt(redacted=True)
        prompt_path = self.diagnostics_dir / "semi_discovery_prompt.md"
        log_path = self.diagnostics_dir / agent_log_name(self.agent_provider, "semi_discovery")
        before = self._tracked_file_hashes()

        write_text(prompt_path, redacted_prompt)
        self._record(
            "semi_discovery_started",
            command=command,
            target=self.target.name,
            target_kind=self.target.kind,
            target_root=str(self.target.root_dir),
            source_url=self.target.source_url,
            agent_provider=self.agent_provider,
            credentials_provided=self.credentials is not None,
            verify=self.verify,
            prompt=str(prompt_path),
            log=str(log_path),
        )

        try:
            completed = run_logged_process(
                command=command,
                input_text=prompt,
                log_path=log_path,
                timeout=self.timeout,
                status_prefix="semi_discovery",
                task_title="Semi-discovery extension agent",
                task_details={
                    "provider": agent_display_name(self.agent_provider),
                    "target": self.target.name,
                    "target_kind": self.target.kind,
                    "source_url": self.target.source_url,
                    "prompt": str(prompt_path),
                    "diagnostics": str(self.diagnostics_dir),
                    "credentials": "provided" if self.credentials else "not provided",
                },
                redact_values=redact_values(self.credentials),
                show_output_lines=True,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "TimeoutExpired":
                self._record("semi_discovery_timeout", timeout=self.timeout)
                raise RuntimeError(f"Semi-discovery timed out. See {log_path}.") from exc
            self._record("semi_discovery_failed_before_finish", error=repr(exc))
            raise

        changed_files = self._changed_tracked_files(before)
        summary_path = self.diagnostics_dir / "semi_discovery_summary.md"
        write_text(
            summary_path,
            self._build_summary(
                changed_files=changed_files,
                provider=agent_display_name(self.agent_provider),
                elapsed_seconds=completed.elapsed_seconds,
                returncode=completed.returncode,
                log_path=log_path,
            ),
        )
        emit_summary(
            "semi_discovery",
            "Semi-discovery",
            {
                "provider": agent_display_name(self.agent_provider),
                "target": self.target.name,
                "target_kind": self.target.kind,
                "elapsed": f"{completed.elapsed_seconds:.1f}s",
                "returncode": completed.returncode,
                "changed_files": changed_files,
                "summary": str(summary_path),
                "log": str(log_path),
            },
        )
        self._record(
            "semi_discovery_finished",
            returncode=completed.returncode,
            stdout_chars=len(completed.stdout),
            stderr_chars=len(completed.stderr),
            elapsed_seconds=round(completed.elapsed_seconds, 1),
            changed_files=changed_files,
            summary=str(summary_path),
        )

        if completed.returncode != 0:
            raise RuntimeError(
                f"Semi-discovery agent failed with exit code {completed.returncode}. See {log_path}."
            )

        if self.verify:
            self._run_verification()

    def _build_command(self) -> list[str]:
        if self.extend_command:
            return shlex.split(self.extend_command)
        return build_agent_command(self.agent_provider)

    def _build_prompt(self, redacted: bool) -> str:
        agent_name = agent_display_name(self.agent_provider)
        files = "\n".join(f"- {path}" for path in self.target.files)
        allowed_paths = "\n".join(f"- {path}" for path in self.target.allowed_paths)
        verification = " ".join(self.target.verification_command)
        credentials_block = credentials_prompt_block(self.credentials, redacted=redacted)

        return f"""You are extending an existing scraper in MCP-PW-SCRAPPER.

This is semi-discovery mode: do not create a brand-new scraper.
Extend the existing ETL with the requested extra data while preserving its architecture.

Requested extra data:
{self.requested_data}

Selected scraper target:
{self.target.name}

Target kind:
{self.target.kind}

Target root:
{self.target.root_dir}

Source URL:
{self.target.source_url}

Agent provider:
{agent_name}

Credentials:
{credentials_block}

Existing ETL files to inspect:
{files}

Allowed files to patch:
{allowed_paths}

Rules:
- You must use Playwright MCP/browser MCP to inspect the live source page before extending code.
- If browser MCP is not available in your agent environment, stop and report that Playwright MCP is required.
- You are running unattended from the host process; do not ask the user to approve MCP/tool calls.
- If credentials are provided and the source requires login, log in first and audit the authenticated page.
- Keep the current class-based Extract / Transform / Validate / Load architecture.
- Extend the existing extractor with raw fields for the requested data.
- Extend the existing transformer with normalized output fields.
- Update the schema and validator only if the output contract requires it.
- Keep the local JSON loader behavior intact unless the requested extension requires loader metadata changes.
- Extend the existing ETL files listed above in place.
- Do not create a second unrelated scraper.
- Do not modify unrelated domains, diagnostics, notifications, repair infrastructure, docs, or generated output files.
- Do not print, save, or echo credential values.
- Keep changes minimal and specific to the selected ETL.

After patching, run:
{verification}

Also run:
uv run python -m compileall main.py src

Final response requirements:
- data fields added
- DOM facts/selectors checked
- files changed
- whether credentials/login were needed
- verification commands and results
"""

    def _run_verification(self) -> None:
        log_path = self.diagnostics_dir / "semi_discovery_verification.log"
        command = list(self.target.verification_command)
        self._record("semi_discovery_verification_started", command=command)
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            cwd=Path.cwd(),
            check=False,
        )
        write_text(
            log_path,
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
            "semi_discovery_verification_finished",
            returncode=completed.returncode,
            stdout_chars=len(completed.stdout),
            stderr_chars=len(completed.stderr),
            log=str(log_path),
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Semi-discovery verification failed. See {log_path}.")

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
        emit_json_event("semi_discovery", event, **details)

    def _redact(self, value: str) -> str:
        if self.credentials is None:
            return value
        redacted = value
        for secret in self.credentials:
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        return redacted

    def _tracked_file_hashes(self) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for path_value in self.target.allowed_paths:
            path = Path(path_value)
            if path.exists():
                hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return hashes

    def _changed_tracked_files(self, before: dict[str, str]) -> list[str]:
        after = self._tracked_file_hashes()
        paths = sorted(set(before) | set(after))
        return [path for path in paths if before.get(path) != after.get(path)]

    @staticmethod
    def _build_summary(
        changed_files: list[str],
        provider: str,
        elapsed_seconds: float,
        returncode: int,
        log_path: Path,
    ) -> str:
        changed = "\n".join(f"- {path}" for path in changed_files) or "- none"
        return "\n".join(
            [
                "# Semi-discovery Summary",
                "",
                f"- Provider: {provider}",
                f"- Elapsed: {elapsed_seconds:.1f}s",
                f"- Return code: {returncode}",
                f"- Log: {log_path}",
                "",
                "## Changed Files",
                "",
                changed,
                "",
            ]
        )
