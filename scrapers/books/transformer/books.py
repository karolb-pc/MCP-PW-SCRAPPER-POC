from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from src.contracts.transformer import AbstractTransformer


class BooksToScrapeTransformer(AbstractTransformer):
    def __init__(self, source_name: str, source_url: str):
        self.source_name = source_name
        self.source_url = source_url

    def transform(self, raw_items: list[dict[str, Any]]) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for raw in raw_items:
            price_text = str(raw.get("price", ""))
            price_match = re.search(r"[\d.]+", price_text)
            items.append(
                {
                    "title": str(raw.get("title", "")).strip(),
                    "price": float(price_match.group()) if price_match else 0.0,
                    "availability": str(raw.get("availability", "")).strip(),
                    "rating": int(raw.get("rating", 0) or 0),
                    "detail_url": urljoin(self.source_url, str(raw.get("detail_url", ""))),
                }
            )
        return {
            "source_url": self.source_url,
            "user_prompt": f"Scrape book listings from {self.source_name}",
            "items": items,
            "summary": {"items": len(items)},
            "meta": {"mode": "generate_self_healing", "scraper": "books"},
        }
