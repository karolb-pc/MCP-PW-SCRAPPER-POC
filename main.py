from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import click
from loguru import logger

from src.agents.credentials import Credentials, load_credentials_from_env
from src.agents.provider import normalize_agent_provider
from src.audit.source_auditor import SourceAuditor
from src.breaker.demo_breaker import DemoBreaker
from src.browser import BrowserSessionProfile, resolve_browser_session_profile
from src.config.general import general_settings
from src.diagnostics.artifacts import save_page_artifacts
from src.discovery import (
    AutomatedScrapeDiscovery,
    GeneratedCodeScrapeDiscovery,
    SelfHealingScrapeGenerator,
    derive_scraper_slug,
)
from src.discovery.runtime import run_generated_discovery_scraper
from src.notification.mock_email import MockEmailNotifier
from src.repair.target_repair import TargetAutoRepairRunner
from src.scraper_target import ScraperTarget, resolve_scraper_target
from src.semi_discovery import SemiDiscoveryExtender
from src.utils import slugify, write_text

logger.configure(handlers=[{"sink": sys.stdout, "level": "INFO"}])


def normalize_slug(value: str) -> str:
    """Python-package-safe slug (underscores) for a scraper folder name."""
    return slugify(value, max_length=48, fallback="scraper").replace("-", "_")


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


def append_option(command: list[str], option: str, value: str | None) -> None:
    if value is None:
        return
    command.extend([option, value])


def load_payload_from_output(output_path: Path) -> dict[str, Any]:
    if not output_path.exists():
        raise RuntimeError(f"Scraper command finished but output file does not exist: {output_path}")
    payload = json.loads(output_path.read_text())
    if not isinstance(payload, dict):
        raise RuntimeError(f"Scraper output must be a JSON object: {output_path}")
    return payload


def run_manifest_scraper_command(
    *,
    target: ScraperTarget,
    output_path: Path,
    diagnostics_dir: Path | None,
    export_dir: Path | None,
    browser: str | None,
    quiet: bool,
) -> dict[str, Any]:
    if target.run_command is None:
        raise RuntimeError(f"Scraper target has no run_command: {target.root_dir}")

    command = list(target.run_command)
    append_option(command, "--output", str(output_path))
    append_option(command, "--diagnostics-dir", str(diagnostics_dir) if diagnostics_dir else None)
    append_option(command, "--export-dir", str(export_dir) if export_dir else None)
    append_option(command, "--browser", browser)
    if quiet and "--quiet" not in command:
        command.append("--quiet")

    completed = subprocess.run(command, text=True, capture_output=True, cwd=Path.cwd(), check=False)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode != 0:
        raise RuntimeError(
            "Scraper command failed.\n"
            f"Command: {' '.join(command)}\n"
            f"Exit code: {completed.returncode}"
        )
    return load_payload_from_output(output_path)


async def run_target_once(
    *,
    target: ScraperTarget,
    output_path: Path,
    diagnostics_dir: Path | None,
    export_dir: Path | None,
    browser: str | None,
    quiet: bool,
    credentials: Credentials | None,
) -> dict[str, Any]:
    if target.kind == "discovery_run":
        user_prompt_path = target.root_dir / "user_prompt.md"
        user_prompt = user_prompt_path.read_text().strip() if user_prompt_path.exists() else ""
        return await run_generated_discovery_scraper(
            run_dir=target.root_dir,
            source_url=target.source_url,
            user_prompt=user_prompt,
            output_path=output_path,
            credentials=credentials,
        )

    return run_manifest_scraper_command(
        target=target,
        output_path=output_path,
        diagnostics_dir=diagnostics_dir,
        export_dir=export_dir,
        browser=browser,
        quiet=quiet,
    )


def run_direct_discovery(
    *,
    mode: str = "direct",
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
    run_discovery(
        mode=mode,
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


def run_discovery(
    *,
    mode: str,
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
    normalized_mode = mode.strip().lower().replace("_", "-")
    discovery_class = {
        "direct": AutomatedScrapeDiscovery,
        "generated-code": GeneratedCodeScrapeDiscovery,
    }.get(normalized_mode)
    if discovery_class is None:
        raise click.UsageError("Unsupported discovery mode. Use direct or generated-code.")

    if normalized_mode == "generated-code":
        if output == str(general_settings.discovery_output_path):
            output = str(general_settings.generated_code_output_path)
        if runs_dir == str(general_settings.discovery_runs_dir):
            runs_dir = str(general_settings.generated_code_runs_dir)
        if diagnostics_dir == str(general_settings.discovery_diagnostics_dir):
            diagnostics_dir = str(general_settings.generated_code_diagnostics_dir)

    user_prompt = read_scrape_prompt(prompt, prompt_file)
    selected_session = select_session_profile(
        session_profile=session_profile,
        sessions_dir=sessions_dir,
        source_url=url,
        command="discover-code" if normalized_mode == "generated-code" else "discover",
        details={
            "mode": normalized_mode,
            "output": output,
            "runs_dir": str(runs_dir),
            "diagnostics_dir": str(diagnostics_dir),
            "output_format": output_format,
            "prompt_source": "file" if prompt_file else "inline/stdin/interactive",
        },
    )
    result = asyncio.run(
        discovery_class(
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
                "mode": "generated-code" if normalized_mode == "generated-code" else "direct",
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
@click.option(
    "--mode",
    "direct_mode",
    type=click.Choice(["direct", "generated-code"]),
    default="direct",
    help="Scrape directly with the agent or have the agent generate and run disposable scraper code.",
)
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
    direct_mode: str,
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
            mode=direct_mode,
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
@click.option(
    "--mode",
    type=click.Choice(["direct", "generated-code"]),
    default="direct",
    help="Scrape directly with the agent or have the agent generate and run disposable scraper code.",
)
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
    mode: str,
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
            mode=mode,
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


@main.command("discover-code")
@click.option("--url", required=True, help="Page URL to inspect and scrape.")
@click.option("--output", default=str(general_settings.generated_code_output_path), help="Path for the final output.")
@click.option(
    "--runs-dir",
    default=str(general_settings.generated_code_runs_dir),
    help="Directory for generated-code prompts and artifacts.",
)
@click.option(
    "--diagnostics-dir",
    default=str(general_settings.generated_code_diagnostics_dir),
    help="Root directory for generated-code per-scrape diagnostics.",
)
@click.option("--output-format", default="json", help="Requested output format, for example json.")
@click.option("--prompt", default=None, help="Optional one-line scrape goal. If omitted, CLI asks interactively.")
@click.option(
    "--prompt-file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Read the scrape goal from a text/markdown file.",
)
@click.option("--scrape-timeout", default=900, type=int, help="Timeout for the generated-code scraping agent.")
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
@agent_provider_flags("generated-code discovery")
def discover_code(
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
        run_discovery(
            mode="generated-code",
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


@main.command("generate-self-healing")
@click.option("--url", required=True, help="Page URL to inspect and scrape.")
@click.option("--prompt", default=None, help="Optional one-line scrape goal. If omitted, CLI asks interactively.")
@click.option(
    "--prompt-file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Read the scrape goal from a text/markdown file.",
)
@click.option("--output-format", default="json", help="Requested output format, for example json.")
@click.option("--output", default=None, help="Final output file path. Defaults under output/scrapers/<slug>.")
@click.option(
    "--target-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Where to persist the generated scraper project. Defaults to scrapers/<slug>.",
)
@click.option("--name", default=None, help="Override the scraper slug (python-safe).")
@click.option("--scrape-timeout", default=900, type=int, help="Timeout for the generating agent.")
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
@agent_provider_flags("self-healing generation")
def generate_self_healing(
    url: str,
    prompt: str | None,
    prompt_file: Path | None,
    output_format: str,
    output: str | None,
    target_dir: Path | None,
    name: str | None,
    scrape_timeout: int,
    scrape_command: str | None,
    session_profile: str | None,
    sessions_dir: Path,
    use_credentials: bool,
    agent_provider: tuple[str, ...],
):
    try:
        user_prompt = read_scrape_prompt(prompt, prompt_file)
        if name:
            slug = normalize_slug(name)
        else:
            slug = derive_scraper_slug(user_prompt, url)

        resolved_target_dir = target_dir or (general_settings.scrapers_dir / slug)
        resolved_output = output or str(general_settings.self_healing_output_dir / slug / "output.json")
        runs_dir = general_settings.self_healing_runs_dir
        diagnostics_dir = general_settings.self_healing_runs_dir.parent / "metrics"

        selected_session = select_session_profile(
            session_profile=session_profile,
            sessions_dir=sessions_dir,
            source_url=url,
            command="generate-self-healing",
            details={"target_dir": str(resolved_target_dir), "slug": slug, "output": resolved_output},
        )
        result = asyncio.run(
            SelfHealingScrapeGenerator(
                source_url=url,
                user_prompt=user_prompt,
                output_path=Path(resolved_output),
                runs_dir=runs_dir,
                diagnostics_root_dir=diagnostics_dir,
                output_format=output_format,
                credentials=select_credentials(use_credentials=use_credentials),
                agent_provider=select_agent_provider(agent_provider),
                scrape_timeout=scrape_timeout,
                scrape_command=scrape_command,
                session_profile=selected_session,
                target_dir=resolved_target_dir,
                scraper_slug=slug,
            ).run()
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "mode": "generate-self-healing",
                    "scraper_slug": slug,
                    "target_dir": str(resolved_target_dir),
                    "manifest": str(resolved_target_dir / "scraper_target.json"),
                    "items": result.items_count,
                    "agent_provider": result.agent_provider,
                    "output": str(result.output_path),
                    "run_dir": str(result.run_dir),
                    "diagnostics_dir": str(result.diagnostics_dir),
                    "next": f"uv run python main.py run --path {resolved_target_dir}",
                },
                indent=2,
            )
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


@main.command("run")
@click.option("--path", "source_path", type=click.Path(path_type=Path), required=True, help="Path to scraper folder or discovery run.")
@click.option("--output", type=click.Path(path_type=Path), default=None)
@click.option("--diagnostics-dir", type=click.Path(path_type=Path), default=None)
@click.option("--export-dir", type=click.Path(path_type=Path), default=None)
@click.option("--notifications-dir", type=click.Path(path_type=Path), default=general_settings.source_repair_notifications_dir)
@click.option("--notify-email", default=general_settings.notify_email)
@click.option("--browser", type=click.Choice(["auto", "camoufox", "playwright"]), default=None)
@click.option("--quiet", is_flag=True)
@click.option("--auto-repair", is_flag=True, help="On failure, invoke the repair agent and retry, emitting a diff per attempt.")
@click.option("--repair-attempts", default=general_settings.repair_attempts, type=int)
@click.option("--repair-command", default=None)
@click.option("--repair-timeout", default=general_settings.repair_timeout, type=int)
@click.option("--use-credentials", is_flag=True, help="Read LOGIN and PASSWORD from env and pass them to the scraper/repair agent.")
@agent_provider_flags("repair")
def run(
    source_path: Path,
    output: Path | None,
    diagnostics_dir: Path | None,
    export_dir: Path | None,
    notifications_dir: Path,
    notify_email: str,
    browser: str | None,
    quiet: bool,
    auto_repair: bool,
    repair_attempts: int,
    repair_command: str | None,
    repair_timeout: int,
    use_credentials: bool,
    agent_provider: tuple[str, ...],
):
    try:
        target = resolve_scraper_target(source_path=source_path, output_path=output)
        credentials = select_credentials(use_credentials=use_credentials)
        diagnostics_path = diagnostics_dir or target.root_dir / "diagnostics/latest"
        output_path = target.output_path

        async def run_once() -> dict[str, Any]:
            return await run_target_once(
                target=target,
                output_path=output_path,
                diagnostics_dir=diagnostics_path,
                export_dir=export_dir,
                browser=browser,
                quiet=quiet,
                credentials=credentials,
            )

        if auto_repair:
            runner = TargetAutoRepairRunner(
                target=target,
                diagnostics_dir=diagnostics_path,
                notifier=MockEmailNotifier(notifications_dir=notifications_dir, recipient=notify_email),
                repair_attempts=repair_attempts,
                repair_timeout=repair_timeout,
                agent_provider=select_agent_provider(agent_provider),
                credentials=credentials,
                repair_command=repair_command,
            )
            payload = asyncio.run(runner.run(run_once))
        else:
            payload = asyncio.run(run_once())

        items = payload.get("items")
        print(
            json.dumps(
                {
                    "status": "ok",
                    "target": target.name,
                    "target_root": str(target.root_dir),
                    "items": len(items) if isinstance(items, list) else None,
                    "output": str(output_path),
                },
                indent=2,
            )
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


@main.command("repair")
@click.option("--path", "source_path", type=click.Path(path_type=Path), required=True, help="Path to scraper folder or discovery run.")
@click.option("--output", type=click.Path(path_type=Path), default=None)
@click.option("--diagnostics-dir", type=click.Path(path_type=Path), default=None)
@click.option("--export-dir", type=click.Path(path_type=Path), default=None)
@click.option("--notifications-dir", type=click.Path(path_type=Path), default=general_settings.source_repair_notifications_dir)
@click.option("--notify-email", default=general_settings.notify_email)
@click.option("--browser", type=click.Choice(["auto", "camoufox", "playwright"]), default=None)
@click.option("--quiet", is_flag=True)
@click.option("--repair-attempts", default=general_settings.repair_attempts, type=int)
@click.option("--repair-command", default=None)
@click.option("--repair-timeout", default=general_settings.repair_timeout, type=int)
@click.option("--use-credentials", is_flag=True, help="Read LOGIN and PASSWORD from env and pass them to the scraper/repair agent.")
@agent_provider_flags("repair")
def repair(
    source_path: Path,
    output: Path | None,
    diagnostics_dir: Path | None,
    export_dir: Path | None,
    notifications_dir: Path,
    notify_email: str,
    browser: str | None,
    quiet: bool,
    repair_attempts: int,
    repair_command: str | None,
    repair_timeout: int,
    use_credentials: bool,
    agent_provider: tuple[str, ...],
):
    ctx = click.get_current_context()
    ctx.invoke(
        run,
        source_path=source_path,
        output=output,
        diagnostics_dir=diagnostics_dir,
        export_dir=export_dir,
        notifications_dir=notifications_dir,
        notify_email=notify_email,
        browser=browser,
        quiet=quiet,
        auto_repair=True,
        repair_attempts=repair_attempts,
        repair_command=repair_command,
        repair_timeout=repair_timeout,
        use_credentials=use_credentials,
        agent_provider=agent_provider,
    )


@main.command("audit")
@click.option("--path", "source_path", type=click.Path(path_type=Path), required=True, help="Path to scraper folder or discovery run to audit.")
@click.option("--diagnostics-dir", default=str(general_settings.audit_diagnostics_dir))
@click.option("--audit-timeout", default=900, type=int)
@click.option("--audit-command", default=None)
@click.option("--source-url", default=None, help="Optional source URL override. Defaults to the selected scraper target URL.")
@click.option("--browser", type=click.Choice(["auto", "camoufox", "playwright"]), default="playwright")
@click.option("--fix", is_flag=True, help="Allow the selected agent to patch scraper code if source drift is found.")
@click.option("--use-credentials", is_flag=True, help="Read LOGIN and PASSWORD from env and pass them to the audit agent.")
@agent_provider_flags("audit")
def audit(
    source_path: Path,
    diagnostics_dir: str,
    audit_timeout: int,
    audit_command: str | None,
    source_url: str | None,
    browser: str,
    fix: bool,
    use_credentials: bool,
    agent_provider: tuple[str, ...],
):
    try:
        target = resolve_scraper_target(source_path=source_path)
        auditor = SourceAuditor(
            diagnostics_dir=Path(diagnostics_dir),
            timeout=audit_timeout,
            target=target,
            source_url=source_url,
            browser=browser,
            fix=fix,
            credentials=select_credentials(use_credentials=use_credentials),
            agent_provider=select_agent_provider(agent_provider),
            audit_command=audit_command,
        )
        auditor.run()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


@main.command("semi-discover")
@click.option("--path", "source_path", type=click.Path(path_type=Path), required=True, help="Path to scraper folder or discovery run to extend.")
@click.option("--prompt", default=None, help="Optional one-line extension goal. If omitted, CLI asks interactively.")
@click.option(
    "--prompt-file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Read the extension goal from a text/markdown file.",
)
@click.option("--diagnostics-dir", default=str(general_settings.semi_discovery_diagnostics_dir))
@click.option("--extend-timeout", default=900, type=int)
@click.option("--extend-command", default=None)
@click.option("--verify/--no-verify", default=True, help="Run target verification after the agent finishes.")
@click.option("--use-credentials", is_flag=True, help="Read LOGIN and PASSWORD from env and pass them to the extension agent.")
@agent_provider_flags("semi-discovery")
def semi_discover(
    source_path: Path,
    prompt: str | None,
    prompt_file: Path | None,
    diagnostics_dir: str,
    extend_timeout: int,
    extend_command: str | None,
    verify: bool,
    use_credentials: bool,
    agent_provider: tuple[str, ...],
):
    try:
        target = resolve_scraper_target(source_path=source_path)
        extender = SemiDiscoveryExtender(
            target=target,
            requested_data=read_scrape_prompt(prompt, prompt_file),
            diagnostics_dir=Path(diagnostics_dir),
            timeout=extend_timeout,
            verify=verify,
            credentials=select_credentials(use_credentials=use_credentials),
            agent_provider=select_agent_provider(agent_provider),
            extend_command=extend_command,
        )
        extender.run()
        print(
            json.dumps(
                {
                    "status": "ok",
                    "target": target.name,
                    "target_kind": target.kind,
                    "target_root": str(target.root_dir),
                    "diagnostics_dir": diagnostics_dir,
                },
                indent=2,
            )
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


@main.command("break")
@click.option("--path", "source_path", type=click.Path(path_type=Path), required=True, help="Path to scraper folder or discovery run to break.")
@click.option("--diagnostics-dir", default=str(general_settings.break_diagnostics_dir))
@click.option("--break-timeout", default=900, type=int)
@click.option("--break-command", default=None)
@click.option("--use-credentials", is_flag=True, help="Read LOGIN and PASSWORD from env and pass them to the break agent.")
@agent_provider_flags("break")
def break_scraper(
    source_path: Path,
    diagnostics_dir: str,
    break_timeout: int,
    break_command: str | None,
    use_credentials: bool,
    agent_provider: tuple[str, ...],
):
    try:
        target = resolve_scraper_target(source_path=source_path)
        breaker = DemoBreaker(
            diagnostics_dir=Path(diagnostics_dir),
            timeout=break_timeout,
            agent_provider=select_agent_provider(agent_provider),
            target=target,
            credentials=select_credentials(use_credentials=use_credentials),
            break_command=break_command,
        )
        breaker.run()
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
