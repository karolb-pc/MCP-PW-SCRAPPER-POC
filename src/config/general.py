from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneralSettings:
    diagnostics_dir: Path = Path(os.getenv("SCRAPER_DIAGNOSTICS_DIR", "diagnostics/latest"))
    discovery_diagnostics_dir: Path = Path(
        os.getenv("SCRAPER_DISCOVERY_DIAGNOSTICS_DIR", "output/agent_discovery/metrics")
    )
    discovery_output_path: Path = Path(os.getenv("SCRAPER_DISCOVERY_OUTPUT", "output/agent_discovery/discovery.json"))
    discovery_runs_dir: Path = Path(os.getenv("SCRAPER_DISCOVERY_RUNS_DIR", "output/agent_discovery/runs"))
    generated_code_diagnostics_dir: Path = Path(
        os.getenv("SCRAPER_GENERATED_CODE_DIAGNOSTICS_DIR", "output/generated_code_discovery/metrics")
    )
    generated_code_output_path: Path = Path(
        os.getenv("SCRAPER_GENERATED_CODE_OUTPUT", "output/generated_code_discovery/discovery.json")
    )
    generated_code_runs_dir: Path = Path(
        os.getenv("SCRAPER_GENERATED_CODE_RUNS_DIR", "output/generated_code_discovery/runs")
    )
    sessions_dir: Path = Path(os.getenv("SCRAPER_SESSIONS_DIR", "sessions"))
    browser: str = os.getenv("SCRAPER_BROWSER", "auto")
    agent_provider: str = os.getenv("SCRAPER_AGENT_PROVIDER", "claude")

    # --- Self-healing / persistent scraper generation (generate-self-healing) ---
    scrapers_dir: Path = Path(os.getenv("SCRAPER_SCRAPERS_DIR", "scrapers"))
    self_healing_output_dir: Path = Path(
        os.getenv("SCRAPER_SELF_HEALING_OUTPUT_DIR", "output/scrapers")
    )
    self_healing_runs_dir: Path = Path(
        os.getenv("SCRAPER_SELF_HEALING_RUNS_DIR", "output/self_healing/runs")
    )
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
    notify_email: str = os.getenv("SCRAPER_NOTIFY_EMAIL", "scraper-ops@example.local")
    repair_attempts: int = int(os.getenv("SCRAPER_REPAIR_ATTEMPTS", "5"))
    repair_timeout: int = int(os.getenv("SCRAPER_REPAIR_TIMEOUT", "900"))


general_settings = GeneralSettings()
