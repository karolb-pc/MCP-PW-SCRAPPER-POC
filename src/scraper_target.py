from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScraperTarget:
    name: str
    kind: str
    root_dir: Path
    source_url: str
    files: tuple[Path, ...]
    allowed_paths: tuple[Path, ...]
    run_command: tuple[str, ...] | None
    verification_command: tuple[str, ...]
    output_path: Path

    @property
    def generated_dir(self) -> Path | None:
        candidate = self.root_dir / "generated"
        return candidate if candidate.exists() else None


def discovery_run_target(discovery_run: Path, output_path: Path | None = None) -> ScraperTarget:
    run_dir = discovery_run.expanduser()
    if run_dir.name == "generated" and (run_dir / "extractor.py").exists():
        run_dir = run_dir.parent
    request_path = run_dir / "request.json"
    generated_dir = run_dir / "generated"
    if not request_path.exists():
        raise ValueError(f"Discovery run is missing request.json: {request_path}")
    if not generated_dir.exists():
        raise ValueError(f"Discovery run is missing generated/ directory: {generated_dir}")

    request = json.loads(request_path.read_text())
    source_url = request.get("source_url")
    if not isinstance(source_url, str) or not source_url:
        raise ValueError(f"Discovery run request.json has no source_url: {request_path}")

    output = output_path or Path(request.get("output_path") or run_dir / "output.json")
    files = (
        generated_dir / "extractor.py",
        generated_dir / "transformer.py",
        generated_dir / "loader.py",
        request_path,
        run_dir / "user_prompt.md",
    )
    allowed_paths = (
        generated_dir / "extractor.py",
        generated_dir / "transformer.py",
        generated_dir / "loader.py",
    )
    return ScraperTarget(
        name=run_dir.name,
        kind="discovery_run",
        root_dir=run_dir,
        source_url=source_url,
        files=files,
        allowed_paths=allowed_paths,
        run_command=(
            sys.executable,
            "main.py",
            "run",
            "--path",
            str(run_dir),
            "--output",
            str(output),
        ),
        verification_command=(
            sys.executable,
            "main.py",
            "run",
            "--path",
            str(run_dir),
            "--output",
            str(output),
        ),
        output_path=output,
    )


def manifest_target(source_path: Path, output_path: Path | None = None) -> ScraperTarget:
    root_dir = source_path.expanduser()
    manifest_path = root_dir / "scraper_target.json"
    if not manifest_path.exists():
        raise ValueError(f"Source path is missing scraper_target.json: {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    source_url = manifest.get("source_url")
    if not isinstance(source_url, str) or not source_url:
        raise ValueError(f"scraper_target.json has no source_url: {manifest_path}")

    def path_list(field: str) -> tuple[Path, ...]:
        raw_paths = manifest.get(field)
        if not isinstance(raw_paths, list) or not raw_paths:
            raise ValueError(f"scraper_target.json field {field!r} must be a non-empty list: {manifest_path}")
        paths: list[Path] = []
        for raw_path in raw_paths:
            if not isinstance(raw_path, str) or not raw_path:
                raise ValueError(f"scraper_target.json field {field!r} contains an invalid path: {manifest_path}")
            candidate = Path(raw_path).expanduser()
            paths.append(candidate if candidate.is_absolute() else root_dir / candidate)
        return tuple(paths)

    run_command = manifest.get("run_command")
    if run_command is not None and (
        not isinstance(run_command, list)
        or not all(isinstance(part, str) and part for part in run_command)
    ):
        raise ValueError(
            f"scraper_target.json field 'run_command' must be a non-empty string list when set: {manifest_path}"
        )

    verification_command = manifest.get("verification_command") or run_command
    if not isinstance(verification_command, list) or not all(
        isinstance(part, str) and part for part in verification_command
    ):
        raise ValueError(
            f"scraper_target.json field 'verification_command' must be a non-empty string list: {manifest_path}"
        )

    configured_output = output_path or manifest.get("output_path") or root_dir / "output.json"
    configured_output_path = Path(configured_output).expanduser()
    if not configured_output_path.is_absolute():
        configured_output_path = root_dir / configured_output_path

    return ScraperTarget(
        name=str(manifest.get("name") or root_dir.name),
        kind=str(manifest.get("kind") or "manifest"),
        root_dir=root_dir,
        source_url=source_url,
        files=path_list("files"),
        allowed_paths=path_list("allowed_paths"),
        run_command=tuple(run_command) if run_command is not None else None,
        verification_command=tuple(verification_command),
        output_path=configured_output_path,
    )


def resolve_scraper_target(
    *,
    source_path: Path | None = None,
    output_path: Path | None = None,
) -> ScraperTarget:
    if source_path is None:
        raise ValueError("Select a source path with --path.")

    selected_path = source_path.expanduser()
    normalized_path = selected_path.parent if selected_path.name == "generated" else selected_path
    if (normalized_path / "request.json").exists() and (normalized_path / "generated").exists():
        return discovery_run_target(selected_path, output_path=output_path)
    return manifest_target(normalized_path, output_path=output_path)
