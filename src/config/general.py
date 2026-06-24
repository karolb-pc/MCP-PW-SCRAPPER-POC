from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneralSettings:
    source_name: str = os.getenv("SCRAPER_SOURCE_NAME", "Scraper Source")
    source_url: str = os.getenv("SCRAPER_SOURCE_URL", "")
    output_path: Path = Path(os.getenv("SCRAPER_OUTPUT", "output/scraper.json"))
    diagnostics_dir: Path = Path(os.getenv("SCRAPER_DIAGNOSTICS_DIR", "diagnostics/latest"))
    export_dir: Path = Path(os.getenv("SCRAPER_EXPORT_DIR", "data/successful"))
    discovery_output_path: Path = Path(os.getenv("SCRAPER_DISCOVERY_OUTPUT", "output/discovery.json"))
    discovery_runs_dir: Path = Path(os.getenv("SCRAPER_DISCOVERY_RUNS_DIR", "scrapers/discovery"))
    semi_discovery_diagnostics_dir: Path = Path(
        os.getenv("SCRAPER_SEMI_DISCOVERY_DIAGNOSTICS_DIR", "diagnostics/semi-discovery")
    )
    break_diagnostics_dir: Path = Path(
        os.getenv("SCRAPER_BREAK_DIAGNOSTICS_DIR", "diagnostics/llm-break-demo")
    )
    audit_diagnostics_dir: Path = Path(
        os.getenv("SCRAPER_AUDIT_DIAGNOSTICS_DIR", "diagnostics/source-audit")
    )
    source_repair_notifications_dir: Path = Path(
        os.getenv("SCRAPER_REPAIR_NOTIFICATIONS_DIR", "notifications/source-repair")
    )
    notifications_dir: Path = Path(
        os.getenv("SCRAPER_NOTIFICATIONS_DIR", "notifications/mock-email-outbox")
    )
    notify_email: str = os.getenv("SCRAPER_NOTIFY_EMAIL", "scraper-ops@example.local")
    browser: str = os.getenv("SCRAPER_BROWSER", "auto")
    agent_provider: str = os.getenv("SCRAPER_AGENT_PROVIDER", "openai")
    repair_attempts: int = int(os.getenv("SCRAPER_REPAIR_ATTEMPTS", "5"))
    repair_timeout: int = int(os.getenv("SCRAPER_REPAIR_TIMEOUT", "900"))


general_settings = GeneralSettings()
