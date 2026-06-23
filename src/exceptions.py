from __future__ import annotations


class ScraperValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Validation failed: " + "; ".join(errors))


class MockedScraperBreakage(Exception):
    pass
