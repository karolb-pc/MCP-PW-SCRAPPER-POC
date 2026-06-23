from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.repair.process_runner import run_logged_process
from src.utils import write_json, write_text


class CodexSourceAuditor:
    def __init__(
        self,
        diagnostics_dir: Path,
        timeout: int,
        source_url: str,
        browser: str,
        fix: bool,
        credentials: tuple[str, str] | None = None,
        audit_command: str | None = None,
    ):
        self.diagnostics_dir = diagnostics_dir
        self.timeout = timeout
        self.source_url = source_url
        self.browser = browser
        self.fix = fix
        self.credentials = credentials
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
        before = self._project_file_hashes()

        write_text(prompt_path, redacted_prompt)
        self._record(
            "source_audit_started",
            command=command,
            source_url=self.source_url,
            browser=self.browser,
            fix=self.fix,
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
                redact_values=self.credentials or (),
            )
        except Exception as exc:
            if exc.__class__.__name__ == "TimeoutExpired":
                self._record("source_audit_timeout", timeout=self.timeout)
                raise RuntimeError(f"Source audit timed out. See {log_path}.") from exc
            self._record("source_audit_failed_before_finish", error=repr(exc))
            raise

        changed_project_files = self._changed_project_files(before)
        self._record(
            "source_audit_finished",
            returncode=completed.returncode,
            stdout_chars=len(completed.stdout),
            stderr_chars=len(completed.stderr),
            elapsed_seconds=round(completed.elapsed_seconds, 1),
            changed_project_files=changed_project_files,
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
        print(json.dumps({"status": event, **details}, indent=2), file=sys.stderr)

    def _build_command(self) -> list[str]:
        if self.audit_command:
            return shlex.split(self.audit_command)

        codex_path = shutil.which("codex")
        if codex_path is None:
            raise RuntimeError(
                "Source audit requested, but the 'codex' command is not available in PATH. "
                "Install Codex CLI or pass --audit-command."
            )

        return [
            codex_path,
            "exec",
            "--cd",
            str(Path.cwd()),
            "--sandbox",
            "workspace-write",
            "--skip-git-repo-check",
            "-",
        ]

    def _run_fresh_verification(self) -> None:
        verification_diagnostics_dir = self.diagnostics_dir / "fresh-verification"
        command = [
            sys.executable,
            "main.py",
            "run",
            "--quiet",
            "--browser",
            self.browser,
            "--diagnostics-dir",
            str(verification_diagnostics_dir),
        ]
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
        credentials_block = self._credentials_block(redacted)
        write_policy = (
            "If the current scraper code is stale or incompatible with the source HTML, patch only the minimal files under src/etl/extractor/ or src/etl/transformer/."
            if self.fix
            else "Do not edit files. Produce findings only."
        )
        verification_command = f"uv run python main.py run --quiet --browser {self.browser}"
        return f"""You are running a proactive source audit for MCP-PW-SCRAPPER.

Goal:
- Open and inspect the live source page.
- Analyze the current HTML/DOM and important product-card selectors.
- Compare the source page with the scraper code in src/etl/extractor/books.py and src/etl/transformer/books.py.
- {mode}.

Source URL:
{self.source_url}

Browser mode for local verification:
{self.browser}

Credentials:
{credentials_block}

Rules:
- Use credentials only if the source page requires login.
- Never print, save, or echo credentials.
- Do not change diagnostics, repair, notifier, runner, config, docs, output files, or unrelated code.
- {write_policy}
- Keep changes minimal and specific to source-page compatibility.
- If you patch code, run: {verification_command}
- Also run: uv run python -m compileall main.py src
- Do not run --auto-repair from inside this audit.

Expected data contract:
- payload.items must contain at least one record
- every item must have title, price_gbp, rating, availability, and absolute_url
- price_gbp must be numeric
- rating must be null or an integer from 1 to 5
- absolute_url must be an https URL

Final response requirements:
- source page status
- whether login was needed
- selectors/DOM facts checked
- files changed, if any
- root cause, if a fix was needed
- verification commands and results
"""

    def _credentials_block(self, redacted: bool) -> str:
        if self.credentials is None:
            return "No credentials were provided."
        login, password = self.credentials
        if redacted:
            return "Credentials were provided but are redacted in saved artifacts."
        return (
            "Credentials were provided for optional login.\n"
            f"Login: {login}\n"
            f"Password: {password}"
        )

    def _redact(self, value: str) -> str:
        if self.credentials is None:
            return value
        redacted = value
        for secret in self.credentials:
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        return redacted

    @staticmethod
    def _project_file_hashes() -> dict[str, str]:
        paths = [Path("main.py"), Path("scraper.py"), *Path("src").rglob("*.py")]
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
