from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from src.diagnostics.artifacts import save_page_artifacts
from src.etl.extractor.abstract import AbstractExtractor


class BooksToScrapeExtractor(AbstractExtractor):
    def __init__(self, source_url: str):
        self.source_url = source_url

    async def extract(
        self,
        browser_mode: str,
        diagnostics_dir: Path | None = None,
    ) -> list[dict[str, Any]]:
        if browser_mode == "playwright":
            return await self._scrape_with_playwright(diagnostics_dir)

        if browser_mode == "camoufox":
            return await self._scrape_with_camoufox(diagnostics_dir)

        try:
            return await self._scrape_with_camoufox(diagnostics_dir)
        except Exception as exc:
            print(
                f"Camoufox failed ({exc!r}); falling back to Playwright Chromium.",
                file=sys.stderr,
                flush=True,
            )
            return await self._scrape_with_playwright(diagnostics_dir)

    async def _scrape_with_camoufox(self, diagnostics_dir: Path | None) -> list[dict[str, Any]]:
        from camoufox.async_api import AsyncCamoufox

        async with AsyncCamoufox(headless=True) as browser:
            page = await browser.new_page()
            return await self._scrape_books(page, diagnostics_dir)

    async def _scrape_with_playwright(self, diagnostics_dir: Path | None) -> list[dict[str, Any]]:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                return await self._scrape_books(page, diagnostics_dir)
            finally:
                await browser.close()

    async def _scrape_books(
        self,
        page: Any,
        diagnostics_dir: Path | None = None,
    ) -> list[dict[str, Any]]:
        try:
            await page.goto(self.source_url, wait_until="domcontentloaded", timeout=30_000)
            await page.locator("article.product_pod").first.wait_for(timeout=15_000)

            return await page.locator("article.product_pod").evaluate_all(
                """cards => cards.map(card => {
                    const titleLink = card.querySelector("h3 a");
                    return {
                        title: titleLink?.getAttribute("title") ?? titleLink?.textContent?.trim() ?? "",
                        price: card.querySelector(".price_color")?.textContent?.trim() ?? "",
                        ratingClass: card.querySelector(".star-rating")?.className ?? "",
                        availability: card.querySelector(".availability")?.textContent?.trim() ?? "",
                        relativeUrl: titleLink?.getAttribute("href") ?? ""
                    };
                })"""
            )
        except Exception:
            if diagnostics_dir is not None:
                await save_page_artifacts(page, diagnostics_dir)
            raise
