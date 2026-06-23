from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any
from urllib.parse import urljoin

from src.etl.transformer.abstract import AbstractTransformer
from src.models.books import Book

RATING_MAP = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5,
}


class BooksToScrapeTransformer(AbstractTransformer):
    def __init__(self, source_name: str, source_url: str):
        self.source_name = source_name
        self.source_url = source_url

    def transform(self, raw_books: list[dict[str, Any]]) -> dict[str, Any]:
        books = [
            Book(
                title=item["title"].strip(),
                price_gbp=self.parse_price(item["price"]),
                rating=self.parse_rating(item.get("ratingClass")),
                availability=self.normalize_availability(item["availability"]),
                relative_url=item["relativeUrl"],
                absolute_url=urljoin(self.source_url, item["relativeUrl"]),
            )
            for item in raw_books
        ]

        prices = [book.price_gbp for book in books]
        available_items = [
            book for book in books if book.availability.lower().startswith("in stock")
        ]
        top_rated = [book for book in books if book.rating == 5]

        return {
            "source": {
                "name": self.source_name,
                "url": self.source_url,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            },
            "summary": {
                "items": len(books),
                "available_items": len(available_items),
                "average_price_gbp": round(mean(prices), 2) if prices else None,
                "min_price_gbp": min(prices) if prices else None,
                "max_price_gbp": max(prices) if prices else None,
                "top_rated_count": len(top_rated),
            },
            "items": [asdict(book) for book in books],
        }

    @staticmethod
    def parse_price(raw_price: str) -> float:
        cleaned = re.sub(r"[^0-9.]", "", raw_price)
        if not cleaned:
            raise ValueError(f"Could not parse price from {raw_price!r}")
        return round(float(cleaned), 2)

    @staticmethod
    def parse_rating(class_name: str | None) -> int | None:
        if not class_name:
            return None

        for token in class_name.split():
            if token in RATING_MAP:
                return RATING_MAP[token]
        return None

    @staticmethod
    def normalize_availability(raw_availability: str) -> str:
        return " ".join(raw_availability.split())
