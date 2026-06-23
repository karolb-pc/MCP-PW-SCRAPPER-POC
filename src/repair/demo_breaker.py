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

from src.utils import write_json, write_text


class CodexDemoBreaker:
    def __init__(
        self,
        diagnostics_dir: Path,
        timeout: int,
        break_command: str | None = None,
    ):
        self.diagnostics_dir = diagnostics_dir
        self.timeout = timeout
        self.break_command = break_command
        self.report_path = diagnostics_dir / "llm_break_report.json"
        self.events: list[dict[str, Any]] = []

    def run(self) -> None:
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        command = self._build_command()
        prompt = self._build_prompt()
        prompt_path = self.diagnostics_dir / "llm_break_prompt.md"
        log_path = self.diagnostics_dir / "llm_break.log"
        before = self._project_file_hashes()

        write_text(prompt_path, prompt)
        self._record(
            "llm_break_started",
            command=command,
            prompt=str(prompt_path),
            log=str(log_path),
        )

        try:
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                cwd=Path.cwd(),
                check=False,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            write_text(
                log_path,
                "\n".join(
                    [
                        "$ " + " ".join(shlex.quote(part) for part in command),
                        "",
                        f"LLM break timed out after {self.timeout} seconds.",
                        "",
                        "## stdout",
                        exc.stdout or "",
                        "",
                        "## stderr",
                        exc.stderr or "",
                    ]
                ),
            )
            self._record("llm_break_timeout", timeout=self.timeout)
            raise RuntimeError(f"LLM break timed out. See {log_path}.") from exc

        write_text(
            log_path,
            "\n".join(
                [
                    "$ " + " ".join(shlex.quote(part) for part in command),
                    "",
                    "## stdout",
                    completed.stdout,
                    "",
                    "## stderr",
                    completed.stderr,
                    "",
                    f"## returncode\n{completed.returncode}\n",
                ]
            ),
        )

        changed_project_files = self._changed_project_files(before)
        self._record(
            "llm_break_finished",
            returncode=completed.returncode,
            stdout_chars=len(completed.stdout),
            stderr_chars=len(completed.stderr),
            changed_project_files=changed_project_files,
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
        print(json.dumps({"status": event, **details}, indent=2), file=sys.stderr)

    def _build_command(self) -> list[str]:
        if self.break_command:
            return shlex.split(self.break_command)

        codex_path = shutil.which("codex")
        if codex_path is None:
            raise RuntimeError(
                "LLM break requested, but the 'codex' command is not available in PATH. "
                "Install Codex CLI or pass --break-command."
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

    @staticmethod
    def _build_prompt() -> str:
        return """You are preparing a controlled self-repair demo for MCP-PW-SCRAPPER.

Introduce exactly one realistic scraper bug that will make:

uv run python main.py run --quiet --browser playwright

fail against the current https://books.toscrape.com/ page.

Rules:
- Edit only scraper-domain code under src/etl/extractor/ or src/etl/transformer/.
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
