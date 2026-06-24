from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from scrapers.books.extractor.books import BooksToScrapeExtractor
from scrapers.books.settings import SOURCE_NAME, SOURCE_URL
from scrapers.books.transformer.books import BooksToScrapeTransformer
from scrapers.books.validator.books import BooksPayloadValidator
from src.diagnostics.artifacts import write_failure_artifacts
from src.contracts.base import BaseETL
from src.contracts.local_json import LocalJsonLoader
from src.exceptions import MockedScraperBreakage

CONFIG = {
    "extractor": {
        "_class": BooksToScrapeExtractor,
        "params": {
            "source_url": SOURCE_URL,
        },
    },
    "transformer": {
        "_class": BooksToScrapeTransformer,
        "params": {
            "source_name": SOURCE_NAME,
            "source_url": SOURCE_URL,
        },
    },
    "validator": {
        "_class": BooksPayloadValidator,
    },
    "loader": {
        "_class": LocalJsonLoader,
        "params": {
            "export_prefix": "books",
        },
    },
}


class BooksToScrapeETL(BaseETL):
    async def extract(
        self,
        browser_mode: str,
        diagnostics_dir: Path,
        simulate_failure: str,
    ) -> list[dict[str, Any]]:
        if simulate_failure == "selector":
            raise MockedScraperBreakage(
                "Mocked selector failure: product card selector no longer matches the page."
            )
        return await self.extractor.extract(
            browser_mode=browser_mode,
            diagnostics_dir=diagnostics_dir,
        )

    def transform(
        self,
        raw_books: list[dict[str, Any]],
        simulate_failure: str,
    ) -> dict[str, Any]:
        if simulate_failure == "transform":
            raw_books = [
                {
                    **item,
                    "price": "MOCK_BROKEN_PRICE",
                }
                for item in raw_books
            ]

        payload = self.transformer.transform(raw_books=raw_books)

        if simulate_failure == "validation":
            payload["items"] = []
            payload["summary"]["items"] = 0

        return payload

    def validate(self, payload: dict[str, Any]) -> None:
        self.validator.validate(payload=payload)

    def load(
        self,
        payload: dict[str, Any],
        output_path: Path,
        export_dir: Path | None,
        simulate_failure: str,
    ) -> Path | None:
        if simulate_failure == "export":
            raise MockedScraperBreakage("Mocked export failure before writing output.")
        return self.loader.load(
            payload=payload,
            output_path=output_path,
            export_dir=export_dir,
        )

    async def run(
        self,
        browser_mode: str,
        output_path: Path,
        export_dir: Path | None,
        diagnostics_dir: Path,
        simulate_failure: str = "none",
        quiet: bool = False,
    ) -> dict[str, Any]:
        partial_payload: Any | None = None
        try:
            raw_books = await self.extract(
                browser_mode=browser_mode,
                diagnostics_dir=diagnostics_dir,
                simulate_failure=simulate_failure,
            )
            partial_payload = {"raw_items": raw_books}

            payload = self.transform(raw_books=raw_books, simulate_failure=simulate_failure)
            partial_payload = payload

            self.validate(payload=payload)
            exported_path = self.load(
                payload=payload,
                output_path=output_path,
                export_dir=export_dir,
                simulate_failure=simulate_failure,
            )

            if not quiet:
                print(json.dumps(payload, ensure_ascii=False, indent=2))

            print(
                json.dumps(
                    {
                        "status": "ok",
                        "items": payload["summary"]["items"],
                        "output": str(output_path),
                        "exported": str(exported_path) if exported_path else None,
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return payload
        except Exception as exc:
            write_failure_artifacts(diagnostics_dir, exc, partial_payload)
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": repr(exc),
                        "diagnostics_dir": str(diagnostics_dir),
                        "repair_prompt": str(diagnostics_dir / "repair_prompt.md"),
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            raise
