from __future__ import annotations

from pathlib import Path
from typing import Any

from src.utils import write_text


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
