from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneralSettings:
    source_name: str = "Books to Scrape"
    source_url: str = "https://books.toscrape.com/"
    output_path: Path = Path(os.getenv("SCRAPER_OUTPUT", "output/books.json"))
    diagnostics_dir: Path = Path(os.getenv("SCRAPER_DIAGNOSTICS_DIR", "diagnostics/latest"))
    export_dir: Path = Path(os.getenv("SCRAPER_EXPORT_DIR", "data/successful"))
    notifications_dir: Path = Path(
        os.getenv("SCRAPER_NOTIFICATIONS_DIR", "notifications/mock-email-outbox")
    )
    notify_email: str = os.getenv("SCRAPER_NOTIFY_EMAIL", "scraper-ops@example.local")
    browser: str = os.getenv("SCRAPER_BROWSER", "auto")
    repair_attempts: int = int(os.getenv("SCRAPER_REPAIR_ATTEMPTS", "5"))
    repair_timeout: int = int(os.getenv("SCRAPER_REPAIR_TIMEOUT", "900"))


general_settings = GeneralSettings()
