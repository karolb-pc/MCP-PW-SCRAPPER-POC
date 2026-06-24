from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any


def emit_status(prefix: str, message: str) -> None:
    print(f"[{prefix}] {message}", file=sys.stderr, flush=True)


def format_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining = divmod(seconds, 60)
    return f"{int(minutes)}m {remaining:.1f}s"


def compact_command(command: Sequence[str], max_chars: int = 180) -> str:
    value = " ".join(command)
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


def normalize_agent_line(line: str, max_chars: int = 500) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None

    noisy_prefixes = (
        "DEBUG:",
        "INFO:",
        "WARNING:",
        "WARN:",
    )
    if stripped.startswith(noisy_prefixes):
        return None

    if len(stripped) > max_chars:
        stripped = stripped[: max_chars - 3] + "..."
    return stripped


def emit_task_start(
    prefix: str,
    title: str,
    command: Sequence[str],
    log_path: str,
    timeout: int,
    details: Mapping[str, Any] | None = None,
) -> None:
    emit_status(prefix, f"{title} started")
    for key, value in (details or {}).items():
        emit_status(prefix, f"{key}: {value}")
    emit_status(prefix, f"command: {compact_command(command)}")
    emit_status(prefix, f"log: {log_path}")
    emit_status(prefix, f"timeout: {timeout}s")


def emit_task_finish(prefix: str, returncode: int, elapsed_seconds: float, log_path: str) -> None:
    emit_status(
        prefix,
        f"finished returncode={returncode} elapsed={format_seconds(elapsed_seconds)} log={log_path}",
    )


def emit_summary(prefix: str, title: str, details: Mapping[str, Any]) -> None:
    emit_status(prefix, f"{title} summary")
    for key, value in details.items():
        if isinstance(value, list):
            if not value:
                emit_status(prefix, f"{key}: none")
            else:
                emit_status(prefix, f"{key}:")
                for item in value:
                    emit_status(prefix, f"  - {item}")
            continue
        emit_status(prefix, f"{key}: {value}")


def emit_json_event(prefix: str, event: str, **details: Any) -> None:
    payload = {"event": event, **details}
    emit_status(prefix, json.dumps(payload, ensure_ascii=False, default=str))
