from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from scrapers.books.extractor.books import BooksToScrapeExtractor
from scrapers.books.settings import SOURCE_NAME, SOURCE_URL
from scrapers.books.transformer.books import BooksToScrapeTransformer
from scrapers.books.validator.books import BooksPayloadValidator
from src.contracts.base import BaseETL
from src.contracts.local_json import LocalJsonLoader
from src.diagnostics.artifacts import write_failure_artifacts

CONFIG = {
    "extractor": {
        "_class": BooksToScrapeExtractor,
        "params": {"source_url": SOURCE_URL},
    },
    "transformer": {
        "_class": BooksToScrapeTransformer,
        "params": {"source_name": SOURCE_NAME, "source_url": SOURCE_URL},
    },
    "validator": {
        "_class": BooksPayloadValidator,
    },
    "loader": {
        "_class": LocalJsonLoader,
        "params": {"export_prefix": "books"},
    },
}


class BooksToScrapeETL(BaseETL):
    async def extract(self, browser_mode: str, diagnostics_dir: Path) -> list[dict[str, Any]]:
        return await self.extractor.extract(browser_mode=browser_mode, diagnostics_dir=diagnostics_dir)

    def transform(self, raw_items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.transformer.transform(raw_items=raw_items)

    def validate(self, payload: dict[str, Any]) -> None:
        self.validator.validate(payload=payload)

    def load(self, payload: dict[str, Any], output_path: Path, export_dir: Path | None) -> Path | None:
        return self.loader.load(payload=payload, output_path=output_path, export_dir=export_dir)

    async def run(
        self,
        browser_mode: str,
        output_path: Path,
        export_dir: Path | None,
        diagnostics_dir: Path,
        quiet: bool = False,
    ) -> dict[str, Any]:
        partial_payload: Any | None = None
        try:
            raw_items = await self.extract(browser_mode=browser_mode, diagnostics_dir=diagnostics_dir)
            partial_payload = {"raw_items": raw_items}
            payload = self.transform(raw_items=raw_items)
            partial_payload = payload
            self.validate(payload=payload)
            exported_path = self.load(payload=payload, output_path=output_path, export_dir=export_dir)

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
