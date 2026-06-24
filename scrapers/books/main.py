from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import click

from scrapers.books.etl import BooksToScrapeETL, CONFIG
from scrapers.books.settings import DEFAULT_DIAGNOSTICS_DIR, DEFAULT_EXPORT_DIR, DEFAULT_OUTPUT_PATH
from scrapers.books.validator.books import BooksPayloadValidator


@click.group()
def cli() -> None:
    """Books to Scrape local scraper commands."""


@cli.command()
@click.option("--output", type=click.Path(path_type=Path), default=DEFAULT_OUTPUT_PATH)
@click.option("--diagnostics-dir", type=click.Path(path_type=Path), default=DEFAULT_DIAGNOSTICS_DIR)
@click.option("--export-dir", type=click.Path(path_type=Path), default=DEFAULT_EXPORT_DIR)
@click.option("--browser", type=click.Choice(["auto", "camoufox", "playwright"]), default=None)
@click.option(
    "--simulate-failure",
    type=click.Choice(["none", "selector", "transform", "validation", "export"]),
    default="none",
)
@click.option("--quiet", is_flag=True)
def run(
    output: Path,
    diagnostics_dir: Path,
    export_dir: Path | None,
    browser: str | None,
    simulate_failure: str,
    quiet: bool,
) -> None:
    browser_mode = browser or os.getenv("SCRAPER_BROWSER", "auto").lower()
    etl = BooksToScrapeETL(config=CONFIG)
    try:
        asyncio.run(
            etl.run(
                browser_mode=browser_mode,
                output_path=output,
                export_dir=export_dir,
                diagnostics_dir=diagnostics_dir,
                simulate_failure=simulate_failure,
                quiet=quiet,
            )
        )
    except Exception:
        sys.exit(1)


@cli.command()
@click.argument("path", type=click.Path(path_type=Path))
def validate(path: Path) -> None:
    try:
        payload = json.loads(path.read_text())
        BooksPayloadValidator().validate(payload)
        print(json.dumps({"status": "ok", "items": len(payload["items"])}, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli()
