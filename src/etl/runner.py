from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.diagnostics.repair_report import RepairReport
from src.etl.books import BooksToScrapeETL, CONFIG
from src.notification.mock_email import MockEmailNotifier
from src.repair.codex import CodexRepairAgent


class BooksToScrapeAutoRepairRunner:
    def __init__(
        self,
        notifier: MockEmailNotifier,
        repair_attempts: int,
        repair_timeout: int,
        repair_command: str | None,
    ):
        self.notifier = notifier
        self.repair_attempts = repair_attempts
        self.repair_timeout = repair_timeout
        self.repair_command = repair_command

    async def run(
        self,
        browser_mode: str,
        output_path: Path,
        export_dir: Path | None,
        diagnostics_dir: Path,
        simulate_failure: str,
        quiet: bool,
    ) -> dict[str, Any]:
        last_error: BaseException | None = None
        repair_was_attempted = False
        report = RepairReport(diagnostics_dir)
        report.record(
            "auto_repair_run_started",
            browser_mode=browser_mode,
            output_path=str(output_path),
            export_dir=str(export_dir) if export_dir else None,
            repair_attempts=self.repair_attempts,
            repair_timeout=self.repair_timeout,
            simulate_failure=simulate_failure,
        )

        for attempt in range(self.repair_attempts + 1):
            report.record("etl_attempt_started", attempt=attempt + 1)
            try:
                if repair_was_attempted:
                    payload = self._run_fresh_etl_subprocess(
                        browser_mode=browser_mode,
                        output_path=output_path,
                        export_dir=export_dir,
                        diagnostics_dir=diagnostics_dir,
                        simulate_failure=simulate_failure,
                        report=report,
                    )
                else:
                    etl = BooksToScrapeETL(config=CONFIG)
                    payload = await etl.run(
                        browser_mode=browser_mode,
                        output_path=output_path,
                        export_dir=export_dir,
                        diagnostics_dir=diagnostics_dir,
                        simulate_failure=simulate_failure,
                        quiet=quiet,
                    )
                if repair_was_attempted:
                    notification_path = self.notifier.send(
                        subject="[MCP-PW-SCRAPPER] Scraper recovered after repair",
                        body=(
                            "The scraper recovered after an auto-repair attempt.\n\n"
                            f"Items: {payload['summary']['items']}\n"
                            f"Output: {output_path.resolve()}\n"
                            f"Successful export dir: {export_dir.resolve() if export_dir else 'disabled'}\n"
                        ),
                        metadata={
                            "items": payload["summary"]["items"],
                            "output": str(output_path),
                            "attempt": attempt,
                        },
                    )
                    report.record(
                        "notification_sent",
                        kind="recovered_after_repair",
                        path=str(notification_path),
                    )
                report.finish(
                    "succeeded",
                    attempt=attempt + 1,
                    items=payload["summary"]["items"],
                    output=str(output_path),
                )
                return payload
            except Exception as exc:
                last_error = exc
                report.record(
                    "etl_attempt_failed",
                    attempt=attempt + 1,
                    error_type=type(exc).__name__,
                    error=repr(exc),
                    diagnostics_dir=str(diagnostics_dir),
                    repair_prompt=str(diagnostics_dir / "repair_prompt.md"),
                )
                notification_path = self.notifier.send(
                    subject="[MCP-PW-SCRAPPER] Scraper run failed",
                    body=(
                        "The scraper pipeline failed.\n\n"
                        f"Failure number: {attempt + 1}\n"
                        f"Repair attempts allowed: {self.repair_attempts}\n"
                        f"Error: {repr(exc)}\n"
                        f"Diagnostics: {diagnostics_dir.resolve()}\n"
                        f"Repair prompt: {(diagnostics_dir / 'repair_prompt.md').resolve()}\n"
                    ),
                    metadata={
                        "attempt": attempt,
                        "repair_attempts": self.repair_attempts,
                        "error": repr(exc),
                        "diagnostics_dir": str(diagnostics_dir),
                    },
                )
                report.record(
                    "notification_sent",
                    kind="scraper_run_failed",
                    path=str(notification_path),
                )
                if attempt >= self.repair_attempts:
                    break

                repair_was_attempted = True
                report.record("repair_attempt_started", attempt=attempt + 1)
                repair_agent = CodexRepairAgent(
                    diagnostics_dir=diagnostics_dir,
                    repair_timeout=self.repair_timeout,
                    notifier=self.notifier,
                    repair_command=self.repair_command,
                )
                try:
                    repair_result = repair_agent.run()
                    report.record(
                        "repair_attempt_finished",
                        attempt=attempt + 1,
                        **repair_result,
                    )
                except Exception as repair_exc:
                    report.record(
                        "repair_attempt_failed",
                        attempt=attempt + 1,
                        error_type=type(repair_exc).__name__,
                        error=repr(repair_exc),
                    )
                    notification_path = self.notifier.send(
                        subject="[MCP-PW-SCRAPPER] Repair attempt failed",
                        body=(
                            "The repair agent failed before the scraper could be retried.\n\n"
                            f"Repair attempt: {attempt + 1}\n"
                            f"Error: {repr(repair_exc)}\n"
                            f"Diagnostics: {diagnostics_dir.resolve()}\n"
                        ),
                        metadata={
                            "repair_attempt": attempt + 1,
                            "error": repr(repair_exc),
                            "diagnostics_dir": str(diagnostics_dir),
                        },
                    )
                    report.record(
                        "notification_sent",
                        kind="repair_attempt_failed",
                        path=str(notification_path),
                    )
                    notification_path = self.notifier.send(
                        subject="[MCP-PW-SCRAPPER] Auto-repair stopped - manual intervention required",
                        body=(
                            "The repair agent failed, so the scraper cannot continue auto-repair safely.\n\n"
                            f"Repair attempt: {attempt + 1}\n"
                            f"Repair error: {repr(repair_exc)}\n"
                            f"Original scraper error: {repr(exc)}\n"
                            f"Diagnostics: {diagnostics_dir.resolve()}\n"
                            "The process is stopping now. Manual intervention is required.\n"
                        ),
                        metadata={
                            "repair_attempt": attempt + 1,
                            "repair_error": repr(repair_exc),
                            "scraper_error": repr(exc),
                            "diagnostics_dir": str(diagnostics_dir),
                        },
                    )
                    report.record(
                        "notification_sent",
                        kind="auto_repair_stopped",
                        path=str(notification_path),
                    )
                    report.finish(
                        "failed",
                        error_type=type(repair_exc).__name__,
                        error=repr(repair_exc),
                    )
                    raise

        assert last_error is not None
        notification_path = self.notifier.send(
            subject="[MCP-PW-SCRAPPER] Auto-repair exhausted - manual intervention required",
            body=(
                "The scraper failed after all allowed auto-repair attempts.\n\n"
                f"Total repair attempts: {self.repair_attempts}\n"
                f"Last error: {repr(last_error)}\n"
                f"Diagnostics: {diagnostics_dir.resolve()}\n"
                "The process is stopping now. Manual intervention is required.\n"
            ),
            metadata={
                "repair_attempts": self.repair_attempts,
                "last_error": repr(last_error),
                "diagnostics_dir": str(diagnostics_dir),
            },
        )
        report.record(
            "notification_sent",
            kind="auto_repair_exhausted",
            path=str(notification_path),
        )
        report.finish(
            "failed",
            error_type=type(last_error).__name__,
            error=repr(last_error),
        )
        raise last_error

    def _run_fresh_etl_subprocess(
        self,
        browser_mode: str,
        output_path: Path,
        export_dir: Path | None,
        diagnostics_dir: Path,
        simulate_failure: str,
        report: RepairReport,
    ) -> dict[str, Any]:
        command = [
            sys.executable,
            "main.py",
            "run",
            "--quiet",
            "--browser",
            browser_mode,
            "--output",
            str(output_path),
            "--diagnostics-dir",
            str(diagnostics_dir),
            "--simulate-failure",
            simulate_failure,
        ]
        if export_dir is not None:
            command.extend(["--export-dir", str(export_dir)])

        report.record("fresh_retry_subprocess_started", command=command)
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            cwd=Path.cwd(),
            check=False,
        )
        report.record(
            "fresh_retry_subprocess_finished",
            returncode=completed.returncode,
            stdout_chars=len(completed.stdout),
            stderr_chars=len(completed.stderr),
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Fresh retry subprocess failed after repair.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        return json.loads(output_path.read_text())
