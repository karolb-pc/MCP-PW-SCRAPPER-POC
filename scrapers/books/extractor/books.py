from __future__ import annotations

from pathlib import Path
from typing import Any

from src.contracts.extractor import AbstractExtractor

_RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


class BooksToScrapeExtractor(AbstractExtractor):
    def __init__(self, source_url: str):
        self.source_url = source_url

    async def extract(
        self,
        browser_mode: str = "playwright",
        diagnostics_dir: Path | None = None,
    ) -> list[dict[str, Any]]:
        from playwright.async_api import async_playwright

        raw: list[dict[str, Any]] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(self.source_url, wait_until="domcontentloaded", timeout=30_000)
                cards = await page.query_selector_all("article.product_pod")
                for card in cards:
                    title_el = await card.query_selector("h3 a")
                    price_el = await card.query_selector(".price_color")
                    avail_el = await card.query_selector(".availability")
                    rating_el = await card.query_selector("p.star-rating")
                    rating_class = (await rating_el.get_attribute("class")) if rating_el else ""
                    rating_word = rating_class.replace("star-rating", "").strip() if rating_class else ""
                    raw.append(
                        {
                            "title": (await title_el.get_attribute("title")) if title_el else "",
                            "price": (await price_el.inner_text()) if price_el else "",
                            "availability": ((await avail_el.inner_text()).strip()) if avail_el else "",
                            "rating": _RATING_WORDS.get(rating_word, 0),
                            "detail_url": (await title_el.get_attribute("href")) if title_el else "",
                        }
                    )
            finally:
                await browser.close()
        return raw
