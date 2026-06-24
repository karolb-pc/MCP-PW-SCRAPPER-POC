from __future__ import annotations

import importlib.util
import inspect
import shlex
from dataclasses import dataclass
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
from src.agents.terminal import emit_summary
from src.utils import utc_timestamp_with_microseconds, write_json, write_text


@dataclass(frozen=True)
class DiscoveryResult:
    run_dir: Path
    output_path: Path
    generated_extractor_path: Path
    generated_transformer_path: Path
    generated_loader_path: Path
    raw_items_count: int
    items_count: int
    agent_provider: str


class AutomatedScrapeDiscovery:
    def __init__(
        self,
        source_url: str,
        user_prompt: str,
        output_path: Path,
        runs_dir: Path,
        credentials: Credentials | None = None,
        agent_provider: str = "openai",
        design_timeout: int = 900,
        design_command: str | None = None,
    ):
        self.source_url = source_url
        self.user_prompt = user_prompt
        self.output_path = output_path
        self.runs_dir = runs_dir
        self.credentials = credentials
        self.agent_provider = normalize_agent_provider(agent_provider)
        self.design_timeout = design_timeout
        self.design_command = design_command
        self.run_dir = runs_dir / utc_timestamp_with_microseconds()
        self.generated_dir = self.run_dir / "generated"

    async def run(self) -> DiscoveryResult:
        self._prepare_run_dir()
        self._run_design_agent()
        raw_items = await self._extract()
        payload = self._transform(raw_items)
        self._load(raw_items, payload)

        result = DiscoveryResult(
            run_dir=self.run_dir,
            output_path=self.output_path,
            generated_extractor_path=self.generated_dir / "extractor.py",
            generated_transformer_path=self.generated_dir / "transformer.py",
            generated_loader_path=self.generated_dir / "loader.py",
            raw_items_count=len(raw_items),
            items_count=len(payload.get("items", [])) if isinstance(payload.get("items"), list) else 0,
            agent_provider=self.agent_provider,
        )
        emit_summary(
            "discovery",
            "Completed",
            {
                "provider": agent_display_name(self.agent_provider),
                "raw_items": result.raw_items_count,
                "items": result.items_count,
                "output": str(result.output_path),
                "run_dir": str(result.run_dir),
            },
        )
        return result

    def _prepare_run_dir(self) -> None:
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        write_text(self.run_dir / "user_prompt.md", self.user_prompt.strip() + "\n")
        write_json(
            self.run_dir / "request.json",
            {
                "source_url": self.source_url,
                "agent_provider": self.agent_provider,
                "use_credentials": self.credentials is not None,
                "prompt_path": str(self.run_dir / "user_prompt.md"),
                "generated_dir": str(self.generated_dir),
                "output_path": str(self.output_path),
            },
        )
        write_text(self.run_dir / "design_prompt.md", self._build_design_prompt(redacted=True))

    def _run_design_agent(self) -> None:
        command = shlex.split(self.design_command) if self.design_command else build_agent_command(self.agent_provider)
        log_path = self.run_dir / agent_log_name(self.agent_provider, "discovery_design")
        completed = run_logged_process(
            command=command,
            input_text=self._build_design_prompt(redacted=False),
            log_path=log_path,
            timeout=self.design_timeout,
            status_prefix=f"{self.agent_provider}_discovery",
            task_title="Discovery scraper design agent",
            task_details={
                "provider": agent_display_name(self.agent_provider),
                "source_url": self.source_url,
                "generated_dir": str(self.generated_dir),
                "credentials": "provided" if self.credentials else "not provided",
            },
            redact_values=redact_values(self.credentials),
            show_output_lines=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Discovery design agent failed with exit code {completed.returncode}. See {log_path}."
            )
        self._assert_generated_files()
        write_text(
            self.run_dir / "design_summary.md",
            "\n".join(
                [
                    "# Discovery Design Summary",
                    "",
                    f"- Provider: {agent_display_name(self.agent_provider)}",
                    f"- Return code: {completed.returncode}",
                    f"- Elapsed: {completed.elapsed_seconds:.1f}s",
                    f"- Log: {log_path}",
                    f"- Extractor: {self.generated_dir / 'extractor.py'}",
                    f"- Transformer: {self.generated_dir / 'transformer.py'}",
                    f"- Loader: {self.generated_dir / 'loader.py'}",
                    "",
                ]
            ),
        )

    async def _extract(self) -> list[dict[str, Any]]:
        module = self._load_module("discovery_generated_extractor", self.generated_dir / "extractor.py")
        extractor_class = getattr(module, "DiscoveryExtractor", None)
        if extractor_class is None:
            raise RuntimeError(
                "generated/extractor.py must define class DiscoveryExtractor(AbstractExtractor)."
            )

        extractor = extractor_class(
            source_url=self.source_url,
            credentials=self.credentials,
            artifacts_dir=self.generated_dir,
        )
        result = extractor.extract()
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, list):
            raise RuntimeError("generated extractor returned a non-list value.")
        return result

    def _transform(self, raw_items: list[dict[str, Any]]) -> dict[str, Any]:
        module = self._load_module("discovery_generated_transformer", self.generated_dir / "transformer.py")
        transformer_class = getattr(module, "DiscoveryTransformer", None)
        if transformer_class is None:
            raise RuntimeError(
                "generated/transformer.py must define class DiscoveryTransformer(AbstractTransformer)."
            )

        transformer = transformer_class(
            source_url=self.source_url,
            user_prompt=self.user_prompt,
            run_dir=self.run_dir,
        )
        payload = transformer.transform(raw_items=raw_items)
        if not isinstance(payload, dict):
            raise RuntimeError("generated transformer returned a non-dict value.")
        if "items" not in payload or not isinstance(payload["items"], list):
            raise RuntimeError("generated transformer payload must contain an items list.")
        payload.setdefault("source_url", self.source_url)
        payload.setdefault("user_prompt", self.user_prompt)
        payload.setdefault("meta", {})
        if isinstance(payload["meta"], dict):
            payload["meta"].update(
                {
                    "mode": "llm_generated_discovery",
                    "agent_provider": self.agent_provider,
                    "artifacts_dir": str(self.run_dir),
                    "extractor": str(self.generated_dir / "extractor.py"),
                    "transformer": str(self.generated_dir / "transformer.py"),
                }
            )
        return payload

    def _load(self, raw_items: list[dict[str, Any]], payload: dict[str, Any]) -> None:
        module = self._load_module("discovery_generated_loader", self.generated_dir / "loader.py")
        loader_class = getattr(module, "DiscoveryLoader", None)
        if loader_class is None:
            raise RuntimeError("generated/loader.py must define class DiscoveryLoader(AbstractLoader).")

        loader = loader_class(run_dir=self.run_dir, output_path=self.output_path)
        result = loader.load(raw_items=raw_items, payload=payload)
        if result is not None and not isinstance(result, (str, Path)):
            raise RuntimeError("generated loader returned an unsupported value.")

    def _assert_generated_files(self) -> None:
        missing = [
            path
            for path in (
                self.generated_dir / "extractor.py",
                self.generated_dir / "transformer.py",
                self.generated_dir / "loader.py",
            )
            if not path.exists()
        ]
        if missing:
            joined = ", ".join(str(path) for path in missing)
            raise RuntimeError(f"Discovery agent did not generate required file(s): {joined}.")

    @staticmethod
    def _load_module(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load generated module: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _build_design_prompt(self, redacted: bool) -> str:
        return f"""You are implementing a one-off scraper for MCP-PW-SCRAPPER.

The user asked for this scrape goal:
{self.user_prompt}

Source URL:
{self.source_url}

Generated-code directory:
{self.generated_dir.resolve()}

Required architecture:
- Keep Extract / Transform / Load responsibilities separate.
- You must create {self.generated_dir.resolve() / "extractor.py"}.
- You must create {self.generated_dir.resolve() / "transformer.py"}.
- You must create {self.generated_dir.resolve() / "loader.py"}.
- Match the existing project architecture contracts under `src/contracts/`: generated extractor, transformer, and loader code must use classes, not loose top-level functions.
- The host process owns orchestration and will run generated Extract, Transform, and Load in order.

Extractor contract:
- In `extractor.py`, import `AbstractExtractor` from `src.contracts.extractor`.
- Define `class DiscoveryExtractor(AbstractExtractor)`.
- Constructor signature must be `def __init__(self, source_url: str, credentials: tuple[str, str] | None = None, artifacts_dir: Path | None = None)`.
- Define `async def extract(self) -> list[dict[str, Any]]`.
- Use Python Playwright inside `DiscoveryExtractor.extract`.
- Open `self.source_url`, perform login only if `self.credentials` is provided and the page needs it, inspect the live DOM, and scrape records matching the user's goal.
- Return raw records as dictionaries. Include raw text and useful raw fields; do not over-normalize in Extract.
- Save optional debugging artifacts next to the generated files only if they help, for example `page.html` or `screenshot.png`.

Transformer contract:
- In `transformer.py`, import `AbstractTransformer` from `src.contracts.transformer`.
- Define `class DiscoveryTransformer(AbstractTransformer)`.
- Constructor signature must be `def __init__(self, source_url: str, user_prompt: str, run_dir: Path)`.
- Define `def transform(self, raw_items: list[dict[str, Any]]) -> dict[str, Any]`.
- Convert raw records into a stable JSON payload using the shared Extract / Transform / Load style.
- The payload must contain `items: list[dict]`.
- Include `source_url`, `user_prompt`, and a `meta` dict when useful.
- Normalize obvious numbers such as prices into numeric fields while keeping original text fields.
- Prefer small helper methods on the transformer class for parsing and normalization, for example `parse_price`, `normalize_text`, or `absolute_url`.

Load contract:
- In `loader.py`, import `AbstractLoader` from `src.contracts.loader`.
- Define `class DiscoveryLoader(AbstractLoader)`.
- Constructor signature must be `def __init__(self, run_dir: Path, output_path: Path)`.
- Define `def load(self, raw_items: list[dict[str, Any]], payload: dict[str, Any]) -> Path`.
- For this POC, the loader should write JSON files only:
  - `self.run_dir / "raw_items.json"`
  - `self.run_dir / "output.json"`
  - `self.output_path`
- Use `src.utils.write_json` or standard `json.dumps(..., ensure_ascii=False, indent=2)`.
- Return `self.output_path`.

Browser/tooling guidance:
- You must use Playwright MCP/browser MCP to inspect and understand the live page before generating code.
- If Playwright MCP is not available in your agent environment, stop and report that browser MCP is required for discovery.
- You are running unattended from the host process; do not ask the user to approve MCP/tool calls.
- The generated extractor may use Python Playwright at runtime after MCP-based analysis is complete.
- The generated code must be self-contained and runnable by the host process.

Credential instructions:
{credentials_prompt_block(self.credentials, redacted=redacted)}

Constraints:
- Only write files under {self.generated_dir.resolve()}.
- Do not modify existing scraper targets outside this discovery run.
- Avoid broad abstractions. This is generated per-source code and can be replaced by later runs.
- Do not print credentials or persist credential values.
- Finish only after all three required files exist: `extractor.py`, `transformer.py`, and `loader.py`.
"""
