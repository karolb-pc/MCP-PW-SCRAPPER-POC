from __future__ import annotations

import os
from pathlib import Path

SCRAPER_ROOT = Path(__file__).resolve().parent

SOURCE_NAME = os.getenv("BOOKS_SOURCE_NAME", "Books to Scrape")
SOURCE_URL = os.getenv("BOOKS_SOURCE_URL", "https://books.toscrape.com/")
DEFAULT_OUTPUT_PATH = Path(os.getenv("BOOKS_OUTPUT_PATH", SCRAPER_ROOT / "output/books.json"))
DEFAULT_DIAGNOSTICS_DIR = Path(
    os.getenv("BOOKS_DIAGNOSTICS_DIR", SCRAPER_ROOT / "diagnostics/latest")
)
DEFAULT_EXPORT_DIR = Path(os.getenv("BOOKS_EXPORT_DIR", SCRAPER_ROOT / "data/successful"))
