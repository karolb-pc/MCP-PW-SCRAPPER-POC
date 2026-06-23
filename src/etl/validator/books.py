from __future__ import annotations

from typing import Any

from src.exceptions import ScraperValidationError


class BooksPayloadValidator:
    def __repr__(self) -> str:
        return self.__class__.__name__

    def validate(self, payload: dict[str, Any]) -> None:
        errors = self.collect_errors(payload)
        if errors:
            raise ScraperValidationError(errors)

    @staticmethod
    def collect_errors(payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        items = payload.get("items")
        summary = payload.get("summary", {})

        if not isinstance(items, list):
            return ["payload.items must be a list"]

        if len(items) == 0:
            errors.append("payload.items must contain at least one record")

        if summary.get("items") != len(items):
            errors.append("summary.items must match the number of items")

        for index, item in enumerate(items):
            prefix = f"items[{index}]"
            if not item.get("title"):
                errors.append(f"{prefix}.title is required")
            if not isinstance(item.get("price_gbp"), int | float):
                errors.append(f"{prefix}.price_gbp must be numeric")
            rating = item.get("rating")
            if rating is not None and rating not in {1, 2, 3, 4, 5}:
                errors.append(f"{prefix}.rating must be null or an integer from 1 to 5")
            if not item.get("availability"):
                errors.append(f"{prefix}.availability is required")
            absolute_url = item.get("absolute_url", "")
            if not isinstance(absolute_url, str) or not absolute_url.startswith("https://"):
                errors.append(f"{prefix}.absolute_url must be an https URL")

        return errors
