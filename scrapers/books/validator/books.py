from __future__ import annotations

from typing import Any

from scrapers.books.schema.books import BooksPayload
from src.exceptions import ScraperValidationError


class BooksPayloadValidator:
    def validate(self, payload: dict[str, Any]) -> None:
        errors: list[str] = []
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            errors.append("payload.items must be a non-empty list")
        try:
            BooksPayload.model_validate(payload)
        except Exception as exc:  # pydantic ValidationError
            errors.append(f"payload does not match BooksPayload schema: {exc}")
        if errors:
            raise ScraperValidationError(errors)
