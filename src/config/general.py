from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneralSettings:
    diagnostics_dir: Path = Path(os.getenv("SCRAPER_DIAGNOSTICS_DIR", "diagnostics/latest"))
    discovery_diagnostics_dir: Path = Path(os.getenv("SCRAPER_DISCOVERY_DIAGNOSTICS_DIR", "diagnostics"))
    discovery_output_path: Path = Path(os.getenv("SCRAPER_DISCOVERY_OUTPUT", "output/discovery.json"))
    discovery_runs_dir: Path = Path(os.getenv("SCRAPER_DISCOVERY_RUNS_DIR", "output/discovery-runs"))
    sessions_dir: Path = Path(os.getenv("SCRAPER_SESSIONS_DIR", "sessions"))
    browser: str = os.getenv("SCRAPER_BROWSER", "auto")
    agent_provider: str = os.getenv("SCRAPER_AGENT_PROVIDER", "openai")


general_settings = GeneralSettings()
