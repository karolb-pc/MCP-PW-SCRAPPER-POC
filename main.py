from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import click
from loguru import logger

from src.config.general import general_settings
from src.diagnostics.artifacts import build_repair_prompt, save_page_artifacts
from src.etl.books import BooksToScrapeETL, CONFIG
from src.etl.runner import BooksToScrapeAutoRepairRunner
from src.etl.validator.books import BooksPayloadValidator
from src.notification.mock_email import MockEmailNotifier
from src.repair.demo_breaker import CodexDemoBreaker
from src.repair.source_auditor import CodexSourceAuditor
from src.utils import write_text

logger.configure(handlers=[{"sink": sys.stdout, "level": "INFO"}])

EXTRACTOR_PATH = Path("src/etl/extractor/books.py")
GOOD_PRODUCT_SELECTOR = "article.product_pod"
BROKEN_PRODUCT_SELECTOR = "article.product_pod_broken_for_repair_demo"


@click.group()
def main():
    pass


@main.command()
@click.option("--output", default=str(general_settings.output_path))
@click.option("--diagnostics-dir", default=str(general_settings.diagnostics_dir))
@click.option("--export-dir", default=str(general_settings.export_dir))
@click.option("--notifications-dir", default=str(general_settings.notifications_dir))
@click.option("--notify-email", default=general_settings.notify_email)
@click.option("--browser", type=click.Choice(["auto", "camoufox", "playwright"]), default=None)
@click.option(
    "--simulate-failure",
    type=click.Choice(["none", "selector", "transform", "validation", "export"]),
    default="none",
)
@click.option("--quiet", is_flag=True)
@click.option("--auto-repair", is_flag=True)
@click.option("--repair-attempts", default=general_settings.repair_attempts, type=int)
@click.option("--repair-command", default=None)
@click.option("--repair-timeout", default=general_settings.repair_timeout, type=int)
def run(
    output: str,
    diagnostics_dir: str,
    export_dir: str,
    notifications_dir: str,
    notify_email: str,
    browser: str | None,
    simulate_failure: str,
    quiet: bool,
    auto_repair: bool,
    repair_attempts: int,
    repair_command: str | None,
    repair_timeout: int,
):
    browser_mode = browser or os.getenv("SCRAPER_BROWSER", general_settings.browser).lower()
    output_path = Path(output)
    diagnostics_path = Path(diagnostics_dir)
    export_path = Path(export_dir) if export_dir else None
    notifier = MockEmailNotifier(
        notifications_dir=Path(notifications_dir),
        recipient=notify_email,
    )

    if auto_repair:
        runner = BooksToScrapeAutoRepairRunner(
            notifier=notifier,
            repair_attempts=repair_attempts,
            repair_timeout=repair_timeout,
            repair_command=repair_command or os.getenv("SCRAPER_REPAIR_COMMAND"),
        )
        try:
            asyncio.run(
                runner.run(
                    browser_mode=browser_mode,
                    output_path=output_path,
                    export_dir=export_path,
                    diagnostics_dir=diagnostics_path,
                    simulate_failure=simulate_failure,
                    quiet=quiet,
                )
            )
        except Exception:
            sys.exit(1)
        return

    etl = BooksToScrapeETL(config=CONFIG)
    try:
        asyncio.run(
            etl.run(
                browser_mode=browser_mode,
                output_path=output_path,
                export_dir=export_path,
                diagnostics_dir=diagnostics_path,
                simulate_failure=simulate_failure,
                quiet=quiet,
            )
        )
    except Exception:
        sys.exit(1)


@main.command()
@click.argument("path")
def validate(path: str):
    try:
        payload = json.loads(Path(path).read_text())
        BooksPayloadValidator().validate(payload)
        print(json.dumps({"status": "ok", "items": len(payload["items"])}, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


@main.command("break-selector-demo")
@click.option("--restore", is_flag=True, help="Restore the normal Books to Scrape product selector.")
def break_selector_demo(restore: bool):
    try:
        source = EXTRACTOR_PATH.read_text()
        if restore:
            updated = source.replace(BROKEN_PRODUCT_SELECTOR, GOOD_PRODUCT_SELECTOR)
            action = "restored"
        else:
            updated = source.replace(GOOD_PRODUCT_SELECTOR, BROKEN_PRODUCT_SELECTOR)
            action = "broken"

        if updated == source:
            print(
                json.dumps(
                    {
                        "status": "unchanged",
                        "action": action,
                        "path": str(EXTRACTOR_PATH),
                    },
                    indent=2,
                )
            )
            return

        write_text(EXTRACTOR_PATH, updated)
        print(
            json.dumps(
                {
                    "status": action,
                    "path": str(EXTRACTOR_PATH),
                    "good_selector": GOOD_PRODUCT_SELECTOR,
                    "broken_selector": BROKEN_PRODUCT_SELECTOR,
                },
                indent=2,
            )
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


@main.command("llm-break-demo")
@click.option("--diagnostics-dir", default="diagnostics/llm-break-demo")
@click.option("--break-timeout", default=900, type=int)
@click.option("--break-command", default=None)
def llm_break_demo(diagnostics_dir: str, break_timeout: int, break_command: str | None):
    try:
        breaker = CodexDemoBreaker(
            diagnostics_dir=Path(diagnostics_dir),
            timeout=break_timeout,
            break_command=break_command,
        )
        breaker.run()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


@main.command("source-audit")
@click.option("--diagnostics-dir", default="diagnostics/source-audit")
@click.option("--audit-timeout", default=900, type=int)
@click.option("--audit-command", default=None)
@click.option("--source-url", default=general_settings.source_url)
@click.option("--browser", type=click.Choice(["auto", "camoufox", "playwright"]), default="playwright")
@click.option("--fix", is_flag=True, help="Allow Codex to patch scraper code if source drift is found.")
@click.option("--credentials", nargs=2, metavar="LOGIN PASSWORD", default=None)
def source_audit(
    diagnostics_dir: str,
    audit_timeout: int,
    audit_command: str | None,
    source_url: str,
    browser: str,
    fix: bool,
    credentials: tuple[str, str] | None,
):
    try:
        auditor = CodexSourceAuditor(
            diagnostics_dir=Path(diagnostics_dir),
            timeout=audit_timeout,
            source_url=source_url,
            browser=browser,
            fix=fix,
            credentials=credentials,
            audit_command=audit_command,
        )
        auditor.run()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


@main.command()
@click.option("--diagnostics-dir", default=str(general_settings.diagnostics_dir))
@click.option("--browser", type=click.Choice(["auto", "camoufox", "playwright"]), default=None)
def diagnose(diagnostics_dir: str, browser: str | None):
    try:
        asyncio.run(_diagnose(diagnostics_dir=Path(diagnostics_dir), browser=browser))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


async def _diagnose(diagnostics_dir: Path, browser: str | None) -> None:
    browser_mode = browser or os.getenv("SCRAPER_BROWSER", general_settings.browser).lower()

    if browser_mode == "camoufox":
        from camoufox.async_api import AsyncCamoufox

        async with AsyncCamoufox(headless=True) as browser_instance:
            page = await browser_instance.new_page()
            await page.goto(general_settings.source_url, wait_until="domcontentloaded", timeout=30_000)
            await save_page_artifacts(page, diagnostics_dir)
    else:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser_instance = await p.chromium.launch(headless=True)
            page = await browser_instance.new_page()
            try:
                await page.goto(general_settings.source_url, wait_until="domcontentloaded", timeout=30_000)
                await save_page_artifacts(page, diagnostics_dir)
            finally:
                await browser_instance.close()

    write_text(
        diagnostics_dir / "repair_prompt.md",
        build_repair_prompt(Exception("Manual diagnose run"), diagnostics_dir),
    )
    print(f"Diagnostics saved to {diagnostics_dir}")


if __name__ == "__main__":
    main()
