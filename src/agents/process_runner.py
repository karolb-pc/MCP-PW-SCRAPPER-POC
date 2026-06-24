from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.agents.terminal import (
    emit_status,
    emit_task_finish,
    emit_task_start,
    normalize_agent_line,
)
from src.utils import write_text


@dataclass(frozen=True)
class LoggedProcessResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float


def run_logged_process(
    command: list[str],
    input_text: str,
    log_path: Path,
    timeout: int,
    status_prefix: str,
    task_title: str | None = None,
    task_details: dict[str, object] | None = None,
    redact_values: Iterable[str] = (),
    heartbeat_seconds: int = 2,
    show_output_lines: bool = False,
) -> LoggedProcessResult:
    started_at = time.monotonic()
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    redact = [value for value in redact_values if value]
    spinner_frames = ["|", "/", "-", "\\"]
    spinner_index = 0
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def clean(value: str) -> str:
        output = value
        for secret in redact:
            output = output.replace(secret, "[REDACTED]")
        return output

    with log_path.open("w") as log_file:
        log_file.write("$ " + " ".join(command) + "\n\n")
        log_file.flush()

        emit_task_start(
            prefix=status_prefix,
            title=task_title or "Agent task",
            command=command,
            log_path=str(log_path),
            timeout=timeout,
            details=task_details,
        )

        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=Path.cwd(),
            bufsize=1,
        )

        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None

        try:
            process.stdin.write(input_text)
            process.stdin.close()
        except BrokenPipeError:
            pass

        def read_stream(stream, chunks: list[str], name: str) -> None:
            for line in stream:
                safe_line = clean(line)
                chunks.append(safe_line)
                log_file.write(f"## {name}\n{safe_line}")
                log_file.flush()
                normalized = normalize_agent_line(safe_line)
                if show_output_lines and normalized:
                    emit_status(status_prefix, f"agent {name}: {normalized}")

        stdout_thread = threading.Thread(
            target=read_stream,
            args=(process.stdout, stdout_chunks, "stdout"),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=read_stream,
            args=(process.stderr, stderr_chunks, "stderr"),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        emit_status(status_prefix, f"process pid={process.pid}")
        next_heartbeat = started_at + heartbeat_seconds

        while process.poll() is None:
            elapsed = time.monotonic() - started_at
            if elapsed > timeout:
                process.kill()
                stdout_thread.join(timeout=2)
                stderr_thread.join(timeout=2)
                stdout = "".join(stdout_chunks)
                stderr = "".join(stderr_chunks)
                log_file.write(f"\n## timeout\nTimed out after {timeout} seconds.\n")
                log_file.flush()
                emit_status(status_prefix, f"timeout after {elapsed:.1f}s / {timeout}s log={log_path}")
                raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)

            if time.monotonic() >= next_heartbeat:
                frame = spinner_frames[spinner_index % len(spinner_frames)]
                spinner_index += 1
                emit_status(status_prefix, f"{frame} working elapsed={elapsed:.1f}s timeout={timeout}s")
                next_heartbeat += heartbeat_seconds
            time.sleep(0.5)

        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        elapsed = time.monotonic() - started_at
        stdout = "".join(stdout_chunks)
        stderr = "".join(stderr_chunks)
        log_file.write(f"\n## returncode\n{process.returncode}\n")
        log_file.flush()
        emit_task_finish(status_prefix, process.returncode, elapsed, str(log_path))
        return LoggedProcessResult(
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            elapsed_seconds=elapsed,
        )


def write_timeout_log(log_path: Path, command: list[str], timeout: int, stdout: str | None, stderr: str | None) -> None:
    write_text(
        log_path,
        "\n".join(
            [
                "$ " + " ".join(command),
                "",
                f"Process timed out after {timeout} seconds.",
                "",
                "## stdout",
                stdout or "",
                "",
                "## stderr",
                stderr or "",
            ]
        ),
    )
