from __future__ import annotations

import os
import shutil
from pathlib import Path

SUPPORTED_AGENT_PROVIDERS = ("openai", "claude")
DEFAULT_AGENT_PROVIDER = "openai"
OPENAI_UNATTENDED_FLAGS = ("--dangerously-bypass-approvals-and-sandbox",)
CLAUDE_UNATTENDED_FLAGS = ("--dangerously-skip-permissions",)
CLAUDE_STREAMING_FLAGS = ("--output-format", "stream-json", "--verbose")


def normalize_agent_provider(provider: str | None) -> str:
    selected = (provider or DEFAULT_AGENT_PROVIDER).lower()
    if selected not in SUPPORTED_AGENT_PROVIDERS:
        supported = ", ".join(SUPPORTED_AGENT_PROVIDERS)
        raise ValueError(f"Unsupported agent provider {provider!r}. Use one of: {supported}.")
    return selected


def agent_display_name(provider: str) -> str:
    provider = normalize_agent_provider(provider)
    if provider == "openai":
        return "OpenAI Codex"
    if provider == "claude":
        return "Claude"
    raise AssertionError(f"Unhandled provider: {provider}")


def agent_log_name(provider: str, suffix: str) -> str:
    provider = normalize_agent_provider(provider)
    return f"{provider}_{suffix}.log"


def resolve_executable(env_name: str, default_name: str) -> str | None:
    configured = os.getenv(env_name)
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.exists():
            return str(configured_path)
        return shutil.which(configured)
    return shutil.which(default_name)


def build_agent_command(provider: str) -> list[str]:
    provider = normalize_agent_provider(provider)
    if provider == "openai":
        codex_path = resolve_executable("CODEX_CLI_PATH", "codex")
        if codex_path is None:
            raise RuntimeError(
                "OpenAI agent requested, but the 'codex' command is not available in PATH. "
                "Install Codex CLI, set CODEX_CLI_PATH, select --claude, or pass a custom command."
            )

        return [
            codex_path,
            "exec",
            "--cd",
            str(Path.cwd()),
            *OPENAI_UNATTENDED_FLAGS,
            "--skip-git-repo-check",
            "-",
        ]

    if provider == "claude":
        claude_path = resolve_executable("CLAUDE_CLI_PATH", "claude")
        if claude_path is None:
            raise RuntimeError(
                "Claude agent requested, but the 'claude' command is not available in PATH. "
                "Install Claude Code CLI, set CLAUDE_CLI_PATH, select --openai, or pass a custom command."
            )

        mcp_config_path = Path.cwd() / "config" / "claude.mcp.json"
        if not mcp_config_path.exists():
            raise RuntimeError(
                "Claude agent requested, but config/claude.mcp.json was not found. "
                "Run the command from the project root or restore the project Claude MCP config."
            )

        return [
            claude_path,
            "-p",
            *CLAUDE_STREAMING_FLAGS,
            "--mcp-config",
            str(mcp_config_path),
            "--strict-mcp-config",
            "--no-chrome",
            *CLAUDE_UNATTENDED_FLAGS,
        ]

    raise AssertionError(f"Unhandled provider: {provider}")
