from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
import json
import hashlib
from pathlib import Path

from src.notification.mock_email import MockEmailNotifier
from src.utils import write_text


class CodexRepairAgent:
    def __init__(
        self,
        diagnostics_dir: Path,
        repair_timeout: int,
        notifier: MockEmailNotifier,
        repair_command: str | None = None,
    ):
        self.diagnostics_dir = diagnostics_dir
        self.repair_timeout = repair_timeout
        self.notifier = notifier
        self.repair_command = repair_command

    def run(self) -> dict[str, object]:
        repair_prompt_path = self.diagnostics_dir / "repair_prompt.md"
        if not repair_prompt_path.exists():
            raise RuntimeError(f"Repair prompt does not exist: {repair_prompt_path}")

        command = self._build_repair_command()
        prompt = repair_prompt_path.read_text()
        log_path = self.diagnostics_dir / "codex_repair.log"
        changed_files_before = self._changed_files()
        file_hashes_before = self._project_file_hashes()

        print(
            json.dumps(
                {
                    "status": "repair_started",
                    "command": command,
                    "prompt": str(repair_prompt_path),
                    "log": str(log_path),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        self.notifier.send(
            subject="[MCP-PW-SCRAPPER] Repair attempt started",
            body=(
                "The scraper failed and auto-repair is starting.\n\n"
                f"Diagnostics: {self.diagnostics_dir.resolve()}\n"
                f"Repair prompt: {repair_prompt_path.resolve()}\n"
                f"Codex log: {log_path.resolve()}\n"
            ),
            metadata={"diagnostics_dir": str(self.diagnostics_dir), "command": command},
        )

        try:
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                cwd=Path.cwd(),
                check=False,
                timeout=self.repair_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            write_text(
                log_path,
                "\n".join(
                    [
                        "$ " + " ".join(shlex.quote(part) for part in command),
                        "",
                        f"Repair timed out after {self.repair_timeout} seconds.",
                        "",
                        "## stdout",
                        exc.stdout or "",
                        "",
                        "## stderr",
                        exc.stderr or "",
                    ]
                ),
            )
            raise RuntimeError(f"Repair agent timed out. See {log_path}.") from exc

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

        if completed.returncode != 0:
            raise RuntimeError(
                f"Repair agent failed with exit code {completed.returncode}. "
                f"See {log_path}."
            )

        self.notifier.send(
            subject="[MCP-PW-SCRAPPER] Repair agent finished",
            body=(
                "Codex repair agent finished with exit code 0.\n\n"
                "The scraper pipeline will now be retried.\n"
                f"Codex log: {log_path.resolve()}\n"
            ),
            metadata={"diagnostics_dir": str(self.diagnostics_dir), "log": str(log_path)},
        )
        changed_files_after = self._changed_files()
        changed_project_files = self._changed_project_files(file_hashes_before)
        return {
            "command": command,
            "log": str(log_path),
            "returncode": completed.returncode,
            "stdout_chars": len(completed.stdout),
            "stderr_chars": len(completed.stderr),
            "changed_files_before_repair": changed_files_before,
            "changed_files_after_repair": changed_files_after,
            "changed_project_files": changed_project_files,
        }

    def _build_repair_command(self) -> list[str]:
        if self.repair_command:
            return shlex.split(self.repair_command)

        codex_path = shutil.which("codex")
        if codex_path is None:
            raise RuntimeError(
                "Auto-repair requested, but the 'codex' command is not available in PATH. "
                "Install Codex CLI or set SCRAPER_REPAIR_COMMAND."
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
