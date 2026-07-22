from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from src.agents.credentials import load_dotenv_values

SUPPORTED_AGENT_PROVIDERS = ("openai", "claude")
DEFAULT_AGENT_PROVIDER = "claude"
OPENAI_UNATTENDED_FLAGS = ("--dangerously-bypass-approvals-and-sandbox",)
CLAUDE_UNATTENDED_FLAGS = ("--dangerously-skip-permissions",)
CLAUDE_STREAMING_FLAGS = ("--output-format", "stream-json", "--verbose")

PLAYWRIGHT_MCP_PACKAGE = "@playwright/mcp@latest"


def build_playwright_mcp_args(*, output_dir: Path | None = None, isolated: bool = True) -> list[str]:
    """Build the `npx @playwright/mcp` argument list for a single agent run.

    `--isolated` keeps each browser profile in memory instead of the single
    shared on-disk profile (``~/Library/Caches/ms-playwright-mcp/mcp-chrome-*``).
    Without it, concurrent agent processes fight over that one profile and fail
    with "Browser is already in use ... use --isolated to run multiple
    instances of the same browser". A per-run ``--output-dir`` keeps each run's
    MCP artifacts (screenshots, traces) separate under concurrency.
    """
    args = ["-y", PLAYWRIGHT_MCP_PACKAGE, "--headless"]
    if isolated:
        args.append("--isolated")
    if output_dir is not None:
        args += ["--output-dir", str(output_dir)]
    return args


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
    dotenv = load_dotenv_values()
    configured = os.getenv(env_name) or dotenv.get(env_name)
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.exists():
            return str(configured_path)
        return shutil.which(configured)
    return shutil.which(default_name)


def build_agent_command(
    provider: str,
    *,
    mcp_config_path: Path | None = None,
    playwright_output_dir: Path | None = None,
) -> list[str]:
    provider = normalize_agent_provider(provider)
    if provider == "openai":
        codex_path = resolve_executable("CODEX_CLI_PATH", "codex")
        if codex_path is None:
            raise RuntimeError(
                "OpenAI agent requested, but the 'codex' command is not available in PATH. "
                "Install Codex CLI, set CODEX_CLI_PATH, select --claude, or pass a custom command."
            )

        # Codex reads MCP servers from the global ~/.codex/config.toml. Override
        # the playwright server for THIS run only (via `-c`, parsed as TOML) so
        # each concurrent run gets an isolated in-memory browser profile without
        # editing the user's global config.
        playwright_args = build_playwright_mcp_args(output_dir=playwright_output_dir)
        args_toml = "[" + ", ".join(json.dumps(arg) for arg in playwright_args) + "]"
        return [
            codex_path,
            "exec",
            "--cd",
            str(Path.cwd()),
            "-c",
            'mcp_servers.playwright.command="npx"',
            "-c",
            f"mcp_servers.playwright.args={args_toml}",
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

        config_path = mcp_config_path or (Path.cwd() / "config" / "claude.mcp.json")
        if not config_path.exists():
            raise RuntimeError(
                "Claude agent requested, but the Playwright MCP config was not found "
                f"({config_path}). Run the command from the project root or restore the "
                "project Claude MCP config."
            )

        return [
            claude_path,
            "-p",
            *CLAUDE_STREAMING_FLAGS,
            "--mcp-config",
            str(config_path),
            "--strict-mcp-config",
            "--no-chrome",
            *CLAUDE_UNATTENDED_FLAGS,
        ]

    raise AssertionError(f"Unhandled provider: {provider}")
