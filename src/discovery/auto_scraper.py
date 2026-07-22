from __future__ import annotations

import json
import shlex
import time
import csv
import shutil
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
    build_playwright_mcp_args,
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
    run_mode = "direct_agent_discovery"
    log_suffix = "direct_discovery"
    status_prefix_suffix = "discovery"
    task_title = "Direct discovery scrape agent"
    summary_title = "# Direct Discovery Summary"
    summary_channel = "discovery"

    def __init__(
        self,
        source_url: str,
        user_prompt: str,
        output_path: Path,
        runs_dir: Path,
        diagnostics_root_dir: Path,
        output_format: str = "json",
        credentials: Credentials | None = None,
        agent_provider: str = "claude",
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
        cleanup_completed = False
        try:
            self._time_phase("prepare", self._prepare_run_dir)
            self._time_phase("agent_scrape", self._run_scrape_agent)
            cleanup_action = self._post_agent_cleanup_action()
            if cleanup_action is not None:
                self._time_phase("generated_code_cleanup", cleanup_action)
                cleanup_completed = True
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
                self.summary_channel,
                status.capitalize(),
                {
                    "mode": self.run_mode,
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
            cleanup_error = None
            cleanup_action = self._post_agent_cleanup_action()
            if cleanup_action is not None and not cleanup_completed:
                try:
                    self._time_phase("generated_code_cleanup", cleanup_action)
                except Exception as cleanup_exc:
                    cleanup_error = repr(cleanup_exc)
            self._write_analytics(
                status="failed",
                total_seconds=time.perf_counter() - total_started,
                payload=payload,
                error=f"{repr(exc)}; cleanup_error={cleanup_error}" if cleanup_error else repr(exc),
            )
            raise

    def _prepare_run_dir(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        write_text(self.run_dir / "user_prompt.md", self.user_prompt.strip() + "\n")
        write_text(self.diagnostics_dir / "user_prompt.md", self.user_prompt.strip() + "\n")
        request = {
            "mode": self.run_mode,
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
            **self._request_metadata_extras(),
        }
        write_json(self.run_dir / "request.json", request)
        write_json(self.diagnostics_dir / "request.json", request)
        write_text(self.run_dir / "scrape_prompt.md", self._build_scrape_prompt(redacted=True))
        write_text(self.diagnostics_dir / "scrape_prompt.md", self._build_scrape_prompt(redacted=True))

    def _resolve_agent_command(self) -> list[str]:
        if self.scrape_command:
            return shlex.split(self.scrape_command)

        # Give every run an isolated, in-memory browser profile and a unique MCP
        # output dir so concurrent runs do not fight over the shared on-disk
        # profile ("Browser is already in use ... use --isolated").
        playwright_output_dir = self.run_dir / ".playwright-mcp"
        playwright_output_dir.mkdir(parents=True, exist_ok=True)

        mcp_config_path: Path | None = None
        if self.agent_provider == "claude":
            mcp_config_path = self.run_dir / "claude.mcp.json"
            write_json(
                mcp_config_path,
                {
                    "mcpServers": {
                        "playwright": {
                            "command": "npx",
                            "args": build_playwright_mcp_args(output_dir=playwright_output_dir),
                        }
                    }
                },
            )

        return build_agent_command(
            self.agent_provider,
            mcp_config_path=mcp_config_path,
            playwright_output_dir=playwright_output_dir,
        )

    def _run_scrape_agent(self) -> None:
        command = self._resolve_agent_command()
        log_path = self.diagnostics_dir / agent_log_name(self.agent_provider, self.log_suffix)
        completed = run_logged_process(
            command=command,
            input_text=self._build_scrape_prompt(redacted=False),
            log_path=log_path,
            timeout=self.scrape_timeout,
            status_prefix=f"{self.agent_provider}_{self.status_prefix_suffix}",
            task_title=self.task_title,
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
            raise RuntimeError(f"{self.task_title} failed with exit code {completed.returncode}. See {log_path}.")
        self._agent_elapsed_seconds = completed.elapsed_seconds
        write_text(
            self.diagnostics_dir / "scrape_summary.md",
            "\n".join(
                [
                    self.summary_title,
                    "",
                    f"- Mode: {self.run_mode}",
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
            "mode": self.run_mode,
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
            **self._analytics_extras(),
        }
        write_json(self.diagnostics_dir / "metrics.json", analytics)
        write_text(
            self.diagnostics_dir / "summary.md",
            "\n".join(
                [
                    "# Scrape Diagnostics",
                    "",
                    f"- Status: {status}",
                    f"- Mode: {self.run_mode}",
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

    def _request_metadata_extras(self) -> dict[str, Any]:
        return {}

    def _analytics_extras(self) -> dict[str, Any]:
        return {}

    def _post_agent_cleanup_action(self):
        return None

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
- Save supporting artifacts only under the diagnostics directory, for example page notes, screenshots, or raw notes.
- If the run is blocked, partial because of an error/limitation, hits login/OTP/CAPTCHA/anti-bot, or sees repeated navigation/pagination failure, capture a screenshot if the browser MCP exposes screenshot support and save it under the diagnostics directory with a descriptive filename.
- When a page action triggers lazy loading, pagination, or an infinite-scroll spinner, wait for the loading indicator to disappear, the target data count to change, or a clearly stated timeout before deciding that no new data appeared. Do not mark repeated data or capture the final failure screenshot while a loading spinner is still active unless the failure is specifically a loading timeout.

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
- If a CAPTCHA, OTP, anti-bot challenge, login failure, repeated pagination failure, or unavailable page appears, do not bypass it. Save any useful diagnostics under the diagnostics directory, including a screenshot when possible, and report the blocker or limitation in the output.

Credential instructions:
{credentials_prompt_block(self.credentials, redacted=redacted)}

Session instructions:
{session_prompt_block(self.session_profile)}

Constraints:
- Do not print credentials or persist credential values.
- Finish only after the output file exists and contains the requested data or a clear structured blocker report.
"""


class GeneratedCodeScrapeDiscovery(AutomatedScrapeDiscovery):
    run_mode = "generated_code_discovery"
    log_suffix = "generated_code_discovery"
    status_prefix_suffix = "generated_code_discovery"
    task_title = "Generated-code discovery scrape agent"
    summary_title = "# Generated-Code Discovery Summary"

    @property
    def generated_code_dir(self) -> Path:
        return self.run_dir / "generated-code-workspace"

    def _prepare_run_dir(self) -> None:
        self.generated_code_dir.mkdir(parents=True, exist_ok=True)
        super()._prepare_run_dir()

    def _request_metadata_extras(self) -> dict[str, Any]:
        return {
            "generated_code_dir": str(self.generated_code_dir),
            "generated_code_cleanup": "host_removes_generated_code_dir_after_agent_process",
        }

    def _analytics_extras(self) -> dict[str, Any]:
        return {
            "generated_code_dir": str(self.generated_code_dir),
            "generated_code_dir_exists_after_cleanup": self.generated_code_dir.exists(),
        }

    def _post_agent_cleanup_action(self):
        return self._cleanup_generated_code_dir

    def _cleanup_generated_code_dir(self) -> None:
        if self.generated_code_dir.exists():
            shutil.rmtree(self.generated_code_dir)

    def _build_scrape_prompt(self, redacted: bool) -> str:
        return f"""You are running a generated-code scraping task for MCP-PW-SCRAPPER.

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

Temporary generated-code workspace:
{self.generated_code_dir.resolve()}

Core workflow:
- Use Playwright MCP/browser MCP first to inspect and understand the live page structure, pagination/lazy-loading behavior, blockers, and the data shape needed by the user.
- After inspecting the page, write a disposable scraper script under the temporary generated-code workspace above.
- The generated script must perform the scraping and transformation work itself. It should open the source URL, collect the requested data, normalize it into the requested output format, and write the final result to the exact output file above.
- Execute the generated script from this run. Do not manually assemble or rewrite the final output outside the script except to create a clear structured blocker report if code execution cannot proceed.
- Delete generated source code and other temporary code files after the script has run. The host process will also remove the temporary generated-code workspace after your process exits.
- Do not create scraper source code outside the temporary generated-code workspace.
- Do not modify repository source files.
- Save the final scraped result to the exact output file above.
- Save supporting diagnostics only under the diagnostics directory, for example page notes, screenshots, or raw observations.
- If the run is blocked, partial because of an error/limitation, hits login/OTP/CAPTCHA/anti-bot, or sees repeated navigation/pagination failure, capture a screenshot if the browser MCP exposes screenshot support and save it under the diagnostics directory with a descriptive filename.
- When a page action triggers lazy loading, pagination, or an infinite-scroll spinner, the generated script should wait for the loading indicator to disappear, the target data count to change, or a clearly stated timeout before deciding that no new data appeared.

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
      "mode": "generated_code_discovery",
      "generated_script_executed": true
    }}
  }}
- Include stable field names based on the user's request.
- Keep useful original text fields, and normalize obvious numbers/dates/URLs when it is safe.

Script/tooling guidance:
- Prefer Python with the installed Playwright package when practical.
- Keep the generated script self-contained and deterministic for this specific scrape goal.
- The script may read environment variables only when needed for credentials described below.
- The script must not print credentials or persist credential values.
- The script should close browser/context/page objects when complete.
- If Playwright MCP is not available for the initial inspection, stop and report that browser MCP is required for generated-code discovery.
- If local browser automation cannot launch from the generated script, write a structured blocker report to the output file and include the script/runtime error in diagnostics without exposing secrets.

Browser behavior constraints:
- You are running unattended from the host process; do not ask the user to approve MCP/tool calls.
- Prefer low-noise browser operations: navigate once, use DOM inspection/evaluate for extraction, and avoid opening product pages unless the user prompt explicitly requires product-detail data.
- Do not browse freely, compare unrelated pages, add items to cart, sign in, change account settings, or perform actions unrelated to collecting the requested fields.
- If a CAPTCHA, OTP, anti-bot challenge, login failure, repeated pagination failure, or unavailable page appears, do not bypass it. Save useful diagnostics under the diagnostics directory and report the blocker or limitation in the output.

Credential instructions:
{credentials_prompt_block(self.credentials, redacted=redacted)}

Session instructions:
{session_prompt_block(self.session_profile)}

Constraints:
- Do not print credentials or persist credential values.
- Finish only after the output file exists and contains the requested data or a clear structured blocker report.
"""
