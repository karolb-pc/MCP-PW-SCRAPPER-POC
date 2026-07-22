from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from src.utils import write_json, write_text


def write_failure_artifacts(
    diagnostics_dir: Path,
    error: BaseException,
    partial_payload: Any | None = None,
) -> None:
    """Persist a failing scraper run's context so the repair agent has a starting point.

    Writes a machine-readable ``failure.json``, any partial payload collected before
    the failure, and a ``repair_prompt.md`` seed that the auto-repair loop can enrich.
    """
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        diagnostics_dir / "failure.json",
        {
            "error": repr(error),
            "error_type": error.__class__.__name__,
            "traceback": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ),
        },
    )
    if partial_payload is not None:
        write_json(diagnostics_dir / "partial_payload.json", partial_payload)
    write_text(
        diagnostics_dir / "repair_prompt.md",
        "\n".join(
            [
                "# Scraper failure",
                "",
                f"The scraper run failed with: {error!r}",
                "",
                "Inspect the live source page, find the root cause, and patch the",
                "scraper so it produces a valid payload again.",
                "",
            ]
        ),
    )


async def save_page_artifacts(page: Any, diagnostics_dir: Path) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    try:
        html = await page.content()
        write_text(diagnostics_dir / "page.html", html)
    except Exception as exc:
        write_text(diagnostics_dir / "page-html-error.txt", repr(exc))

    try:
        await page.screenshot(path=str(diagnostics_dir / "screenshot.png"), full_page=True)
    except Exception as exc:
        write_text(diagnostics_dir / "screenshot-error.txt", repr(exc))
