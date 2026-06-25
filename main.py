from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import click
from loguru import logger

from src.agents.credentials import Credentials, load_credentials_from_env
from src.agents.provider import normalize_agent_provider
from src.browser import BrowserSessionProfile, resolve_browser_session_profile
from src.config.general import general_settings
from src.diagnostics.artifacts import save_page_artifacts
from src.discovery import AutomatedScrapeDiscovery
from src.utils import write_text

logger.configure(handlers=[{"sink": sys.stdout, "level": "INFO"}])


def select_agent_provider(agent_provider: str | tuple[str, ...] | None) -> str:
    if isinstance(agent_provider, tuple):
        selected_flags = list(dict.fromkeys(agent_provider))
        if len(selected_flags) > 1:
            raise click.UsageError("Use only one agent provider flag: --openai or --claude.")
        agent_provider = selected_flags[0] if selected_flags else None

    if agent_provider is not None:
        try:
            return normalize_agent_provider(agent_provider)
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc

    try:
        return normalize_agent_provider(os.getenv("SCRAPER_AGENT_PROVIDER", general_settings.agent_provider))
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc


def agent_provider_flags(command_kind: str):
    def decorator(function):
        function = click.option(
            "--claude",
            "agent_provider",
            flag_value="claude",
            multiple=True,
            help=f"Use Claude CLI as the {command_kind} agent.",
        )(function)
        function = click.option(
            "--openai",
            "agent_provider",
            flag_value="openai",
            multiple=True,
            help=f"Use OpenAI Codex CLI as the {command_kind} agent.",
        )(function)
        return function

    return decorator


def select_credentials(use_credentials: bool) -> Credentials | None:
    if use_credentials:
        try:
            return load_credentials_from_env()
        except RuntimeError as exc:
            raise click.UsageError(str(exc)) from exc
    return None


def select_session_profile(
    *,
    session_profile: str | None,
    sessions_dir: Path,
    source_url: str | None = None,
    command: str,
    details: dict[str, Any] | None = None,
) -> BrowserSessionProfile | None:
    if session_profile is None:
        return None
    try:
        resolved_profile = resolve_browser_session_profile(
            session_profile,
            sessions_dir=sessions_dir,
            source_url=source_url,
        )
        resolved_profile.record_usage(
            command=command,
            source_url=source_url,
            details=details,
        )
        return resolved_profile
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc


def read_scrape_prompt(prompt: str | None, prompt_file: Path | None = None) -> str:
    if prompt and prompt_file is not None:
        raise click.UsageError("Use either --prompt or --prompt-file, not both.")

    if prompt:
        return prompt.strip()

    if prompt_file is not None:
        loaded_prompt = prompt_file.expanduser().read_text().strip()
        if not loaded_prompt:
            raise click.UsageError(f"Prompt file is empty: {prompt_file}")
        return loaded_prompt

    if not sys.stdin.isatty():
        piped_prompt = sys.stdin.read().strip()
        if piped_prompt:
            return piped_prompt

    click.echo("Describe what you want to scrape. Finish with an empty line.")
    lines: list[str] = []
    while True:
        line = click.prompt("scrape>", default="", show_default=False)
        if not line.strip():
            if lines:
                break
            click.echo("Please enter at least one sentence.")
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def run_direct_discovery(
    *,
    url: str,
    output: str,
    runs_dir: str,
    diagnostics_dir: str,
    output_format: str,
    prompt: str | None,
    prompt_file: Path | None,
    scrape_timeout: int,
    scrape_command: str | None,
    session_profile: str | None,
    sessions_dir: Path,
    use_credentials: bool,
    agent_provider: tuple[str, ...],
) -> None:
    user_prompt = read_scrape_prompt(prompt, prompt_file)
    selected_session = select_session_profile(
        session_profile=session_profile,
        sessions_dir=sessions_dir,
        source_url=url,
        command="discover",
        details={
            "output": output,
            "runs_dir": str(runs_dir),
            "diagnostics_dir": str(diagnostics_dir),
            "output_format": output_format,
            "prompt_source": "file" if prompt_file else "inline/stdin/interactive",
        },
    )
    result = asyncio.run(
        AutomatedScrapeDiscovery(
            source_url=url,
            user_prompt=user_prompt,
            output_path=Path(output),
            runs_dir=Path(runs_dir),
            diagnostics_root_dir=Path(diagnostics_dir),
            output_format=output_format,
            credentials=select_credentials(use_credentials=use_credentials),
            agent_provider=select_agent_provider(agent_provider),
            scrape_timeout=scrape_timeout,
            scrape_command=scrape_command,
            session_profile=selected_session,
        ).run()
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "items": result.items_count,
                "agent_provider": result.agent_provider,
                "output_format": result.output_format,
                "output": str(result.output_path),
                "run_dir": str(result.run_dir),
                "diagnostics_dir": str(result.diagnostics_dir),
            },
            indent=2,
        )
    )


@click.group(invoke_without_command=True)
@click.option("--url", "direct_url", default=None, help="Run direct discovery for this page URL.")
@click.option("--output", "direct_output", default=str(general_settings.discovery_output_path))
@click.option("--runs-dir", "direct_runs_dir", default=str(general_settings.discovery_runs_dir))
@click.option("--diagnostics-dir", "direct_diagnostics_dir", default=str(general_settings.discovery_diagnostics_dir))
@click.option("--output-format", "direct_output_format", default="json", help="Requested output format, for example json.")
@click.option("--prompt", "direct_prompt", default=None)
@click.option(
    "--prompt-file",
    "direct_prompt_file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Read the scrape goal from a text/markdown file.",
)
@click.option("--scrape-timeout", "direct_scrape_timeout", default=900, type=int)
@click.option("--scrape-command", "direct_scrape_command", default=None)
@click.option("--session-profile", "direct_session_profile", default=None, help="Reuse/create a named browser session profile.")
@click.option(
    "--sessions-dir",
    "direct_sessions_dir",
    type=click.Path(path_type=Path),
    default=general_settings.sessions_dir,
    help="Directory for local browser session profiles.",
)
@click.option(
    "--use-credentials",
    "--use-credential",
    "--use_credentials",
    "--use_credential",
    "direct_use_credentials",
    is_flag=True,
    help="Read LOGIN and PASSWORD from env and use them during DOM analysis.",
)
@agent_provider_flags("discovery")
@click.pass_context
def main(
    ctx: click.Context,
    direct_url: str | None,
    direct_output: str,
    direct_runs_dir: str,
    direct_diagnostics_dir: str,
    direct_output_format: str,
    direct_prompt: str | None,
    direct_prompt_file: Path | None,
    direct_scrape_timeout: int,
    direct_scrape_command: str | None,
    direct_session_profile: str | None,
    direct_sessions_dir: Path,
    direct_use_credentials: bool,
    agent_provider: tuple[str, ...],
):
    if ctx.invoked_subcommand is not None:
        return

    if direct_url is None:
        click.echo(ctx.get_help())
        return

    try:
        run_direct_discovery(
            url=direct_url,
            output=direct_output,
            runs_dir=direct_runs_dir,
            diagnostics_dir=direct_diagnostics_dir,
            output_format=direct_output_format,
            prompt=direct_prompt,
            prompt_file=direct_prompt_file,
            scrape_timeout=direct_scrape_timeout,
            scrape_command=direct_scrape_command,
            session_profile=direct_session_profile,
            sessions_dir=direct_sessions_dir,
            use_credentials=direct_use_credentials,
            agent_provider=agent_provider,
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


@main.command("discover")
@click.option("--url", required=True, help="Page URL to inspect and scrape.")
@click.option("--output", default=str(general_settings.discovery_output_path), help="Path for the final output.")
@click.option("--runs-dir", default=str(general_settings.discovery_runs_dir), help="Directory for prompts and artifacts.")
@click.option("--diagnostics-dir", default=str(general_settings.discovery_diagnostics_dir), help="Root directory for per-scrape diagnostics.")
@click.option("--output-format", default="json", help="Requested output format, for example json.")
@click.option("--prompt", default=None, help="Optional one-line scrape goal. If omitted, CLI asks interactively.")
@click.option(
    "--prompt-file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Read the scrape goal from a text/markdown file.",
)
@click.option("--scrape-timeout", default=900, type=int, help="Timeout for the direct scraping agent.")
@click.option("--scrape-command", default=None, help="Optional custom LLM command instead of the selected provider default.")
@click.option("--session-profile", default=None, help="Reuse/create a named browser session profile.")
@click.option(
    "--sessions-dir",
    type=click.Path(path_type=Path),
    default=general_settings.sessions_dir,
    help="Directory for local browser session profiles.",
)
@click.option(
    "--use-credentials",
    "--use-credential",
    "--use_credentials",
    "--use_credential",
    is_flag=True,
    help="Read LOGIN and PASSWORD from env and use them during DOM analysis.",
)
@agent_provider_flags("discovery")
def discover(
    url: str,
    output: str,
    runs_dir: str,
    diagnostics_dir: str,
    output_format: str,
    prompt: str | None,
    prompt_file: Path | None,
    scrape_timeout: int,
    scrape_command: str | None,
    session_profile: str | None,
    sessions_dir: Path,
    use_credentials: bool,
    agent_provider: tuple[str, ...],
):
    try:
        run_direct_discovery(
            url=url,
            output=output,
            runs_dir=runs_dir,
            diagnostics_dir=diagnostics_dir,
            output_format=output_format,
            prompt=prompt,
            prompt_file=prompt_file,
            scrape_timeout=scrape_timeout,
            scrape_command=scrape_command,
            session_profile=session_profile,
            sessions_dir=sessions_dir,
            use_credentials=use_credentials,
            agent_provider=agent_provider,
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


@main.command("validate")
@click.argument("path", type=click.Path(path_type=Path))
def validate(path: Path):
    try:
        payload = json.loads(path.read_text())
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError("JSON output must be a list or an object with an items list")
        print(json.dumps({"status": "ok", "items": len(items)}, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


@main.command("diagnose")
@click.option("--url", required=True, help="Page URL to diagnose.")
@click.option("--diagnostics-dir", default=str(general_settings.diagnostics_dir))
@click.option("--browser", type=click.Choice(["auto", "camoufox", "playwright"]), default=None)
@click.option("--session-profile", default=None, help="Create/update a named browser session note for this URL.")
@click.option(
    "--sessions-dir",
    type=click.Path(path_type=Path),
    default=general_settings.sessions_dir,
    help="Directory for local browser session profiles.",
)
def diagnose(
    url: str,
    diagnostics_dir: str,
    browser: str | None,
    session_profile: str | None,
    sessions_dir: Path,
):
    try:
        selected_session = select_session_profile(
            session_profile=session_profile,
            sessions_dir=sessions_dir,
            source_url=url,
            command="diagnose",
            details={
                "diagnostics_dir": diagnostics_dir,
                "browser": browser,
            },
        )
        asyncio.run(
            _diagnose(
                url=url,
                diagnostics_dir=Path(diagnostics_dir),
                browser=browser,
                session_profile=selected_session,
            )
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


async def _diagnose(
    url: str,
    diagnostics_dir: Path,
    browser: str | None,
    session_profile: BrowserSessionProfile | None,
) -> None:
    browser_mode = browser or os.getenv("SCRAPER_BROWSER", general_settings.browser).lower()

    if browser_mode == "camoufox":
        from camoufox.async_api import AsyncCamoufox

        async with AsyncCamoufox(headless=True) as browser_instance:
            page = await browser_instance.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await save_page_artifacts(page, diagnostics_dir)
    else:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser_instance = await p.chromium.launch(headless=True)
            context_kwargs: dict[str, Any] = {}
            if session_profile is not None and session_profile.storage_state_path.exists():
                context_kwargs["storage_state"] = str(session_profile.storage_state_path)
            context = await browser_instance.new_context(**context_kwargs)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await save_page_artifacts(page, diagnostics_dir)
                if session_profile is not None:
                    await context.storage_state(path=str(session_profile.storage_state_path))
            finally:
                await context.close()
                await browser_instance.close()

    write_text(diagnostics_dir / "diagnose.md", f"Manual diagnose run for {url}.\n")
    print(f"Diagnostics saved to {diagnostics_dir}")


if __name__ == "__main__":
    main()
