from __future__ import annotations

import json
import shlex
import time
import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.agents.credentials import Credentials, credentials_prompt_block, redact_values
from src.agents.process_runner import run_logged_process
from src.agents.provider import (
    agent_display_name,
    agent_log_name,
    build_agent_command,
    normalize_agent_provider,
)
from src.agents.terminal import emit_summary
from src.browser import BrowserSessionProfile, session_prompt_block
from src.utils import slugify, utc_timestamp_with_microseconds, write_json, write_text


@dataclass(frozen=True)
class DiscoveryResult:
    run_dir: Path
    diagnostics_dir: Path
    output_path: Path
    output_format: str
    items_count: int | None
    agent_provider: str


class AutomatedScrapeDiscovery:
    def __init__(
        self,
        source_url: str,
        user_prompt: str,
        output_path: Path,
        runs_dir: Path,
        diagnostics_root_dir: Path,
        output_format: str = "json",
        credentials: Credentials | None = None,
        agent_provider: str = "openai",
        scrape_timeout: int = 900,
        scrape_command: str | None = None,
        session_profile: BrowserSessionProfile | None = None,
    ):
        self.source_url = source_url
        self.user_prompt = user_prompt
        self.output_path = output_path
        self.runs_dir = runs_dir
        self.diagnostics_root_dir = diagnostics_root_dir
        self.output_format = output_format.strip() or "json"
        self.credentials = credentials
        self.agent_provider = normalize_agent_provider(agent_provider)
        self.scrape_timeout = scrape_timeout
        self.scrape_command = scrape_command
        self.session_profile = session_profile
        self.timestamp = utc_timestamp_with_microseconds()
        self.run_dir = runs_dir / self.timestamp
        self.diagnostics_dir = diagnostics_root_dir / self._diagnostics_folder_name()
        self._phase_timings: dict[str, float] = {}
        self._agent_elapsed_seconds: float | None = None

    async def run(self) -> DiscoveryResult:
        total_started = time.perf_counter()
        payload: Any = None
        try:
            self._time_phase("prepare", self._prepare_run_dir)
            self._time_phase("agent_scrape", self._run_scrape_agent)
            payload = self._time_phase("validate_output", self._read_and_validate_output)
            status = self._payload_status(payload)
            result = DiscoveryResult(
                run_dir=self.run_dir,
                diagnostics_dir=self.diagnostics_dir,
                output_path=self.output_path,
                output_format=self.output_format,
                items_count=self._count_items(payload),
                agent_provider=self.agent_provider,
            )
            self._write_analytics(
                status=status,
                total_seconds=time.perf_counter() - total_started,
                payload=payload,
            )
            emit_summary(
                "discovery",
                status.capitalize(),
                {
                    "provider": agent_display_name(self.agent_provider),
                    "items": result.items_count if result.items_count is not None else "unknown",
                    "format": result.output_format,
                    "output": str(result.output_path),
                    "run_dir": str(result.run_dir),
                    "diagnostics_dir": str(result.diagnostics_dir),
                },
            )
            return result
        except Exception as exc:
            self._write_analytics(
                status="failed",
                total_seconds=time.perf_counter() - total_started,
                payload=payload,
                error=repr(exc),
            )
            raise

    def _prepare_run_dir(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        write_text(self.run_dir / "user_prompt.md", self.user_prompt.strip() + "\n")
        write_text(self.diagnostics_dir / "user_prompt.md", self.user_prompt.strip() + "\n")
        request = {
            "mode": "direct_agent_discovery",
            "timestamp": self.timestamp,
            "source_url": self.source_url,
            "output_format": self.output_format,
            "agent_provider": self.agent_provider,
            "use_credentials": self.credentials is not None,
            "session_profile": self.session_profile.name if self.session_profile else None,
            "session_profile_dir": str(self.session_profile.profile_dir) if self.session_profile else None,
            "session_storage_state": str(self.session_profile.storage_state_path) if self.session_profile else None,
            "session_user_data_dir": str(self.session_profile.user_data_dir) if self.session_profile else None,
            "prompt_path": str(self.run_dir / "user_prompt.md"),
            "output_path": str(self.output_path),
            "run_dir": str(self.run_dir),
            "diagnostics_dir": str(self.diagnostics_dir),
        }
        write_json(self.run_dir / "request.json", request)
        write_json(self.diagnostics_dir / "request.json", request)
        write_text(self.run_dir / "scrape_prompt.md", self._build_scrape_prompt(redacted=True))
        write_text(self.diagnostics_dir / "scrape_prompt.md", self._build_scrape_prompt(redacted=True))

    def _run_scrape_agent(self) -> None:
        command = shlex.split(self.scrape_command) if self.scrape_command else build_agent_command(self.agent_provider)
        log_path = self.diagnostics_dir / agent_log_name(self.agent_provider, "direct_discovery")
        completed = run_logged_process(
            command=command,
            input_text=self._build_scrape_prompt(redacted=False),
            log_path=log_path,
            timeout=self.scrape_timeout,
            status_prefix=f"{self.agent_provider}_discovery",
            task_title="Direct discovery scrape agent",
            task_details={
                "provider": agent_display_name(self.agent_provider),
                "source_url": self.source_url,
                "output": str(self.output_path),
                "format": self.output_format,
                "credentials": "provided" if self.credentials else "not provided",
                "session_profile": self.session_profile.name if self.session_profile else "not selected",
            },
            redact_values=redact_values(self.credentials),
            show_output_lines=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Direct discovery agent failed with exit code {completed.returncode}. See {log_path}.")
        self._agent_elapsed_seconds = completed.elapsed_seconds
        write_text(
            self.diagnostics_dir / "scrape_summary.md",
            "\n".join(
                [
                    "# Direct Discovery Summary",
                    "",
                    f"- Provider: {agent_display_name(self.agent_provider)}",
                    f"- Return code: {completed.returncode}",
                    f"- Elapsed: {completed.elapsed_seconds:.1f}s",
                    f"- Log: {log_path}",
                    f"- Output: {self.output_path}",
                    f"- Format: {self.output_format}",
                    f"- Diagnostics: {self.diagnostics_dir}",
                    "",
                ]
            ),
        )

    def _read_and_validate_output(self) -> Any:
        if not self.output_path.exists():
            raise RuntimeError(f"Discovery agent finished but output file does not exist: {self.output_path}")
        content = self.output_path.read_text().strip()
        if not content:
            raise RuntimeError(f"Discovery output is empty: {self.output_path}")
        if self.output_format.lower() == "json" or self.output_path.suffix.lower() == ".json":
            try:
                payload = json.loads(content)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Discovery output is not valid JSON: {self.output_path}") from exc
            write_json(self.run_dir / "output.json", payload)
            write_json(self.diagnostics_dir / "output.json", payload)
            return payload
        output_name = f"output{self.output_path.suffix or '.txt'}"
        write_text(self.run_dir / output_name, content + "\n")
        write_text(self.diagnostics_dir / output_name, content + "\n")
        if self.output_format.lower() == "csv" or self.output_path.suffix.lower() == ".csv":
            return self._read_csv_payload(content)
        return content

    @staticmethod
    def _count_items(payload: Any) -> int | None:
        if isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list):
                return len(items)
            return None
        if isinstance(payload, list):
            if all(isinstance(row, dict) for row in payload):
                status_rows = [
                    row
                    for row in payload
                    if isinstance(row.get("status"), str)
                    and row.get("status", "").strip().lower() == "blocked"
                ]
                if status_rows and len(status_rows) == len(payload):
                    return 0
            return len(payload)
        return None

    @staticmethod
    def _read_csv_payload(content: str) -> list[dict[str, str]]:
        reader = csv.DictReader(StringIO(content))
        return [dict(row) for row in reader]

    @staticmethod
    def _payload_status(payload: Any) -> str:
        if isinstance(payload, list) and all(isinstance(row, dict) for row in payload):
            statuses = [
                row.get("status", "").strip().lower()
                for row in payload
                if isinstance(row.get("status"), str) and row.get("status", "").strip()
            ]
            if statuses and all(status == "blocked" for status in statuses):
                return "blocked"
            if statuses and any(status == "blocked" for status in statuses):
                return "partial"
            return "ok"

        if not isinstance(payload, dict):
            return "ok"

        candidates = [
            payload.get("status"),
            payload.get("meta", {}).get("status") if isinstance(payload.get("meta"), dict) else None,
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip().lower()
        return "ok"

    def _diagnostics_folder_name(self) -> str:
        prompt_slug = slugify(self.user_prompt, max_length=56, fallback="prompt")
        host = urlparse(self.source_url).netloc or "source"
        host = host.removeprefix("www.")
        source_slug = slugify(host.split(".")[0], max_length=24, fallback="source")
        return f"{self.timestamp}-{self.agent_provider}-{prompt_slug}-{source_slug}"

    def _time_phase(self, name: str, action):
        started = time.perf_counter()
        try:
            return action()
        finally:
            self._phase_timings[name] = time.perf_counter() - started

    def _write_analytics(
        self,
        *,
        status: str,
        total_seconds: float,
        payload: Any,
        error: str | None = None,
    ) -> None:
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        timings = {
            **self._phase_timings,
            "total": total_seconds,
        }
        measured_phases = {key: value for key, value in self._phase_timings.items()}
        longest_phase = max(measured_phases.items(), key=lambda item: item[1])[0] if measured_phases else None
        analytics = {
            "status": status,
            "error": error,
            "source_url": self.source_url,
            "output_path": str(self.output_path),
            "output_format": self.output_format,
            "agent_provider": self.agent_provider,
            "items_count": self._count_items(payload),
            "run_dir": str(self.run_dir),
            "diagnostics_dir": str(self.diagnostics_dir),
            "timings_seconds": timings,
            "longest_host_phase": longest_phase,
            "agent_elapsed_seconds": self._agent_elapsed_seconds,
        }
        write_json(self.diagnostics_dir / "metrics.json", analytics)
        write_text(
            self.diagnostics_dir / "summary.md",
            "\n".join(
                [
                    "# Scrape Diagnostics",
                    "",
                    f"- Status: {status}",
                    f"- Source URL: {self.source_url}",
                    f"- Output: {self.output_path}",
                    f"- Items: {analytics['items_count'] if analytics['items_count'] is not None else 'unknown'}",
                    f"- Total seconds: {total_seconds:.2f}",
                    f"- Longest host phase: {longest_phase or 'unknown'}",
                    f"- Agent process seconds: {self._agent_elapsed_seconds:.2f}" if self._agent_elapsed_seconds is not None else "- Agent process seconds: unknown",
                    f"- Error: {error or 'none'}",
                    "",
                ]
            ),
        )

    def _build_scrape_prompt(self, redacted: bool) -> str:
        return f"""You are running a direct scraping task for MCP-PW-SCRAPPER.

The user asked for this scrape goal:
{self.user_prompt}

Source URL:
{self.source_url}

Output file:
{self.output_path.resolve()}

Output format:
{self.output_format}

Run artifacts directory:
{self.run_dir.resolve()}

Diagnostics directory:
{self.diagnostics_dir.resolve()}

Core workflow:
- Use Playwright MCP/browser MCP to inspect and interact with the live page.
- Scrape the requested data directly during this agent run.
- Do not create scraper source code, generated extractor code, transformer code, loader code, or reusable scraping scripts.
- Do not modify repository source files.
- Save the final scraped result to the exact output file above.
- Save optional supporting artifacts only under the diagnostics directory, for example page notes, screenshots, or raw notes.

JSON output rules:
- When the requested output format is JSON, write a JSON object.
- Prefer this shape unless the user explicitly requested a different schema:
  {{
    "source_url": "...",
    "user_prompt": "...",
    "items": [
      {{ "...": "..." }}
    ],
    "meta": {{
      "mode": "direct_agent_discovery"
    }}
  }}
- Include stable field names based on the user's request.
- Keep useful original text fields, and normalize obvious numbers/dates/URLs when it is safe.

Browser/tooling guidance:
- If Playwright MCP is not available in your agent environment, stop and report that browser MCP is required for direct discovery.
- You are running unattended from the host process; do not ask the user to approve MCP/tool calls.
- Prefer low-noise browser operations: navigate once, use snapshots/DOM inspection/evaluate for extraction, and avoid opening product pages unless the user prompt explicitly requires product-detail data.
- Do not browse freely, compare unrelated pages, add items to cart, sign in, change account settings, or perform actions unrelated to collecting the requested fields.
- Close the browser/page when the scrape is complete if the MCP tool exposes a close action.
- If a CAPTCHA or anti-bot challenge appears, do not bypass it. Save any useful diagnostics under the diagnostics directory and report the blocker in the output.

Credential instructions:
{credentials_prompt_block(self.credentials, redacted=redacted)}

Session instructions:
{session_prompt_block(self.session_profile)}

Constraints:
- Do not print credentials or persist credential values.
- Finish only after the output file exists and contains the requested data or a clear structured blocker report.
"""
