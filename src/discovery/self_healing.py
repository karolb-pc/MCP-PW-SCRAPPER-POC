from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agents.credentials import credentials_prompt_block
from src.browser import session_prompt_block
from src.discovery.auto_scraper import AutomatedScrapeDiscovery, GeneratedCodeScrapeDiscovery
from src.utils import slugify

ETL_CONTRACT_PATH = Path(__file__).resolve().parents[2] / "resources" / "etl_architecture_contract.md"


def derive_scraper_slug(user_prompt: str, source_url: str) -> str:
    """Python-package-safe slug for the generated scraper folder."""
    from urllib.parse import urlparse

    host = urlparse(source_url).netloc.removeprefix("www.")
    base = host.split(".")[0] if host else ""
    combined = f"{base}-{user_prompt}" if base else user_prompt
    slug = slugify(combined, max_length=48, fallback="scraper")
    return slug.replace("-", "_")


class SelfHealingScrapeGenerator(GeneratedCodeScrapeDiscovery):
    """Generate a PERSISTENT, self-healing full-ETL scraper project.

    Unlike ``GeneratedCodeScrapeDiscovery`` (which writes a disposable script and
    deletes it), this generator keeps the code: the agent authors a complete ETL
    project under ``target_dir`` following SPEC_GENERATE_SELF_HEALING.md section 4,
    then runs it once to produce the output file.
    """

    run_mode = "generate_self_healing"
    log_suffix = "generate_self_healing"
    status_prefix_suffix = "generate_self_healing"
    task_title = "Self-healing scraper generator agent"
    summary_title = "# Self-Healing Generation Summary"
    summary_channel = "generate-self-healing"

    def __init__(self, *, target_dir: Path, scraper_slug: str, **kwargs: Any):
        super().__init__(**kwargs)
        self.target_dir = target_dir
        self.scraper_slug = scraper_slug

    # The generated code is persisted; never delete it.
    def _post_agent_cleanup_action(self):
        return None

    def _prepare_run_dir(self) -> None:
        # Skip GeneratedCodeScrapeDiscovery's disposable-workspace setup; scaffold
        # the persistent target directory instead.
        AutomatedScrapeDiscovery._prepare_run_dir(self)
        self.target_dir.mkdir(parents=True, exist_ok=True)

    def _request_metadata_extras(self) -> dict[str, Any]:
        return {
            "target_dir": str(self.target_dir),
            "scraper_slug": self.scraper_slug,
            "manifest_path": str(self.target_dir / "scraper_target.json"),
            "persisted": True,
        }

    def _analytics_extras(self) -> dict[str, Any]:
        manifest_path = self.target_dir / "scraper_target.json"
        return {
            "target_dir": str(self.target_dir),
            "scraper_slug": self.scraper_slug,
            "manifest_exists": manifest_path.exists(),
        }

    def _read_and_validate_output(self) -> Any:
        manifest_path = self.target_dir / "scraper_target.json"
        if not manifest_path.exists():
            raise RuntimeError(
                "Self-healing generation finished but the persistent scraper is missing its "
                f"manifest: {manifest_path}. The agent must write scraper_target.json."
            )
        return super()._read_and_validate_output()

    @property
    def _module_path(self) -> str:
        # target_dir like scrapers/<slug> -> scrapers.<slug>(.main)
        parts = self.target_dir.parts
        return ".".join(parts)

    def _load_etl_contract(self) -> str:
        contract = ETL_CONTRACT_PATH.read_text()
        replacements = {
            "<SLUG>": self.scraper_slug,
            "<MODULE_PATH>": self._module_path,
            "<SOURCE_URL>": self.source_url,
            "<OUTPUT_PATH>": self.output_path.as_posix(),
            "<TARGET_DIR>": self.target_dir.as_posix(),
        }
        for token, value in replacements.items():
            contract = contract.replace(token, value)
        return contract

    def _build_scrape_prompt(self, redacted: bool) -> str:
        etl_contract = self._load_etl_contract()
        return f"""You are generating a PERSISTENT, self-healing ETL scraper project for MCP-PW-SCRAPPER.

The user asked for this scrape goal:
{self.user_prompt}

Source URL:
{self.source_url}

Final output file the scraper must write:
{self.output_path.resolve()}

Output format:
{self.output_format}

Persistent scraper project directory (KEEP the code here, do NOT delete it):
{self.target_dir.resolve()}

Scraper slug (python-safe): {self.scraper_slug}
Run module path: {self._module_path}.main

Run artifacts directory:
{self.run_dir.resolve()}

Diagnostics directory:
{self.diagnostics_dir.resolve()}

## Step 1 — inspect the live page
- Use Playwright MCP/browser MCP FIRST to inspect the live page: DOM structure, the
  product/item selectors, pagination/lazy-loading behavior, and any blockers.
- If Playwright MCP is not available, stop and report that browser MCP is required.

## Step 2 — author a FULL ETL project following the architecture contract below
You MUST follow this contract exactly. It is the same one every ETL in this repo obeys and it is
maintained as a versioned resource at `resources/etl_architecture_contract.md`.

--- BEGIN ETL ARCHITECTURE CONTRACT ---
{etl_contract}
--- END ETL ARCHITECTURE CONTRACT ---

## Step 3 — run and verify
- Run the scraper once so it writes the final output file above with real scraped data.
- Ensure `uv run python -m compileall {self.target_dir.as_posix()}` succeeds (valid Python).
- Confirm the output file exists and matches the payload shape / requested format.

## Browser / safety rules
- You are running unattended from the host process; do not ask the user to approve MCP/tool calls.
- Prefer low-noise browser operations; navigate once, use DOM inspection/evaluate for extraction.
- Do not modify repository files outside the persistent project directory above
  (you MAY import from src/contracts). Save diagnostics only under the diagnostics directory.
- If blocked (login/OTP/CAPTCHA/anti-bot, repeated pagination failure), do not bypass it; save a
  screenshot to diagnostics and write a structured blocker report to the output file.

Credential instructions:
{credentials_prompt_block(self.credentials, redacted=redacted)}

Session instructions:
{session_prompt_block(self.session_profile)}

Constraints:
- Do not print credentials or persist credential values.
- Finish only after the persistent project exists (with scraper_target.json), compiles, and the
  output file contains the requested data or a clear structured blocker report.
"""
