from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ARTIFACT_PATHS = [
    "output",
    "data",
    "diagnostics",
    "notifications",
    "scrapers/discovery",
    ".pytest_cache",
    ".ruff_cache",
]

RECREATE_DIRS = [
    "output",
    "data",
    "diagnostics",
    "notifications",
    "scrapers/discovery",
]


def remove_path(path: Path, *, dry_run: bool) -> None:
    if not path.exists():
        print(f"skip missing: {path.relative_to(PROJECT_ROOT)}")
        return

    if dry_run:
        print(f"would remove: {path.relative_to(PROJECT_ROOT)}")
        return

    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    print(f"removed: {path.relative_to(PROJECT_ROOT)}")


def remove_pycache_dirs(*, dry_run: bool) -> None:
    for path in sorted(PROJECT_ROOT.rglob("__pycache__")):
        if ".venv" in path.parts:
            continue
        remove_path(path, dry_run=dry_run)


def recreate_dirs(*, dry_run: bool) -> None:
    for relative in RECREATE_DIRS:
        path = PROJECT_ROOT / relative
        if dry_run:
            print(f"would recreate: {relative}/")
            continue
        path.mkdir(parents=True, exist_ok=True)
        if relative == "scrapers/discovery":
            (path / ".gitkeep").touch()
        print(f"ready: {relative}/")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset local test/run artifacts for MCP-PW-SCRAPPER scenarios."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete artifacts. Without this flag the script only prints a dry run.",
    )
    args = parser.parse_args()

    dry_run = not args.yes
    mode = "DRY RUN" if dry_run else "CLEAN"
    print(f"{mode}: resetting scenario artifacts under {PROJECT_ROOT}")
    print("Keeping code, docs, .env, .venv, and lock files untouched.")

    for relative in ARTIFACT_PATHS:
        remove_path(PROJECT_ROOT / relative, dry_run=dry_run)

    remove_pycache_dirs(dry_run=dry_run)
    recreate_dirs(dry_run=dry_run)

    if dry_run:
        print("Run again with --yes to delete these artifacts.")
    else:
        print("Done. Scenario workspace is clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
