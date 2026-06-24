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

from src.config.general import general_settings
from src.diagnostics.artifacts import save_page_artifacts
from src.discovery import AutomatedScrapeDiscovery
from src.discovery.runtime import run_generated_discovery_scraper
from src.notification.mock_email import MockEmailNotifier
from src.agents.credentials import Credentials, load_credentials_from_env
from src.agents.provider import normalize_agent_provider
from src.audit.source_auditor import SourceAuditor
from src.breaker.demo_breaker import DemoBreaker
from src.repair.target_repair import TargetAutoRepairRunner
from src.scraper_target import ScraperTarget, resolve_scraper_target
from src.semi_discovery import SemiDiscoveryExtender
from src.utils import write_text

logger.configure(handlers=[{"sink": sys.stdout, "level": "INFO"}])

SOURCE_COMMANDS = {
    "run": "run",
    "repair": "repair",
    "self-repair": "repair",
    "audit": "audit",
    "semi-discover": "semi-discover",
    "semi-discovery": "semi-discover",
    "break": "break",
}


def rewrite_source_first_argv(argv: list[str]) -> list[str]:
    if len(argv) < 3:
        return argv

    possible_source = Path(argv[1]).expanduser()
    source_command = argv[2]
    mapped_command = SOURCE_COMMANDS.get(source_command)
    if mapped_command is None or not possible_source.exists():
        return argv

    return [
        argv[0],
        mapped_command,
        "--path",
        argv[1],
        *argv[3:],
    ]


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


def read_scrape_prompt(prompt: str | None) -> str:
    if prompt:
        return prompt.strip()

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
    simulate_failure: str,
    quiet: bool,
) -> dict[str, Any]:
    if target.run_command is None:
        raise RuntimeError(f"Scraper target has no run_command: {target.root_dir}")

    command = list(target.run_command)
    append_option(command, "--output", str(output_path))
    append_option(command, "--diagnostics-dir", str(diagnostics_dir) if diagnostics_dir else None)
    append_option(command, "--export-dir", str(export_dir) if export_dir else None)
    append_option(command, "--browser", browser)
    if simulate_failure != "none":
        append_option(command, "--simulate-failure", simulate_failure)
    if quiet and "--quiet" not in command:
        command.append("--quiet")

    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        cwd=Path.cwd(),
        check=False,
    )
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
    simulate_failure: str,
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
        simulate_failure=simulate_failure,
        quiet=quiet,
    )


@click.group(invoke_without_command=True)
@click.option("--url", "direct_url", default=None, help="Run discovery directly for this page URL.")
@click.option("--output", "direct_output", default=str(general_settings.discovery_output_path))
@click.option("--runs-dir", "direct_runs_dir", default=str(general_settings.discovery_runs_dir))
@click.option("--prompt", "direct_prompt", default=None)
@click.option("--design-timeout", "direct_design_timeout", default=900, type=int)
@click.option("--design-command", "direct_design_command", default=None)
@click.option(
    "--use-credentials",
    "--use-credential",
    "--use_credentials",
    "--use_credential",
    "direct_use_credentials",
    is_flag=True,
    help="Read LOGIN and PASSWORD from env and use them before DOM analysis.",
)
@agent_provider_flags("discovery")
@click.pass_context
def main(
    ctx: click.Context,
    direct_url: str | None,
    direct_output: str,
    direct_runs_dir: str,
    direct_prompt: str | None,
    direct_design_timeout: int,
    direct_design_command: str | None,
    direct_use_credentials: bool,
    agent_provider: tuple[str, ...],
):
    if ctx.invoked_subcommand is not None:
        return

    if direct_url is None:
        click.echo(ctx.get_help())
        return

    ctx.invoke(
        discover,
        url=direct_url,
        output=direct_output,
        runs_dir=direct_runs_dir,
        prompt=direct_prompt,
        use_credentials=direct_use_credentials,
        agent_provider=agent_provider,
        design_timeout=direct_design_timeout,
        design_command=direct_design_command,
    )


@main.command("discover")
@click.option("--url", required=True, help="Page URL to inspect and scrape.")
@click.option("--output", default=str(general_settings.discovery_output_path), help="Path for transformed JSON output.")
@click.option("--runs-dir", default=str(general_settings.discovery_runs_dir), help="Directory for prompts, artifacts, and generated code.")
@click.option("--prompt", default=None, help="Optional one-line scrape goal. If omitted, CLI asks interactively.")
@click.option("--design-timeout", default=900, type=int, help="Timeout for the LLM design/codegen agent.")
@click.option("--design-command", default=None, help="Optional custom LLM command instead of the selected provider default.")
@click.option(
    "--use-credentials",
    "--use-credential",
    "--use_credentials",
    "--use_credential",
    is_flag=True,
    help="Read LOGIN and PASSWORD from env and use them before DOM analysis.",
)
@agent_provider_flags("discovery")
def discover(
    url: str,
    output: str,
    runs_dir: str,
    prompt: str | None,
    design_timeout: int,
    design_command: str | None,
    use_credentials: bool,
    agent_provider: tuple[str, ...],
):
    try:
        user_prompt = read_scrape_prompt(prompt)
        result = asyncio.run(
            AutomatedScrapeDiscovery(
                source_url=url,
                user_prompt=user_prompt,
                output_path=Path(output),
                runs_dir=Path(runs_dir),
                credentials=select_credentials(use_credentials=use_credentials),
                agent_provider=select_agent_provider(agent_provider),
                design_timeout=design_timeout,
                design_command=design_command,
            ).run()
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "items": result.items_count,
                    "raw_items": result.raw_items_count,
                    "agent_provider": result.agent_provider,
                    "output": str(result.output_path),
                    "run_dir": str(result.run_dir),
                    "generated_extractor": str(result.generated_extractor_path),
                    "generated_transformer": str(result.generated_transformer_path),
                    "generated_loader": str(result.generated_loader_path),
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
@click.option(
    "--simulate-failure",
    type=click.Choice(["none", "selector", "transform", "validation", "export"]),
    default="none",
)
@click.option("--quiet", is_flag=True)
@click.option("--auto-repair", is_flag=True)
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
    simulate_failure: str,
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
                simulate_failure=simulate_failure,
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


@main.command("validate")
@click.argument("path", type=click.Path(path_type=Path))
def validate(path: Path):
    try:
        payload = json.loads(path.read_text())
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("payload.items must be a list")
        print(json.dumps({"status": "ok", "items": len(items)}, indent=2))
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
@click.option(
    "--simulate-failure",
    type=click.Choice(["none", "selector", "transform", "validation", "export"]),
    default="none",
)
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
    simulate_failure: str,
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
        simulate_failure=simulate_failure,
        quiet=quiet,
        auto_repair=True,
        repair_attempts=repair_attempts,
        repair_command=repair_command,
        repair_timeout=repair_timeout,
        use_credentials=use_credentials,
        agent_provider=agent_provider,
    )


@main.command("semi-discover")
@click.option("--path", "source_path", type=click.Path(path_type=Path), required=True, help="Path to scraper folder or discovery run to extend.")
@click.option("--prompt", default=None, help="Optional one-line extension goal. If omitted, CLI asks interactively.")
@click.option("--diagnostics-dir", default=str(general_settings.semi_discovery_diagnostics_dir))
@click.option("--extend-timeout", default=900, type=int)
@click.option("--extend-command", default=None)
@click.option("--verify/--no-verify", default=True, help="Run target verification after the agent finishes.")
@click.option("--use-credentials", is_flag=True, help="Read LOGIN and PASSWORD from env/.env and pass them to the extension agent.")
@agent_provider_flags("semi-discovery")
def semi_discover(
    source_path: Path,
    prompt: str | None,
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
            requested_data=read_scrape_prompt(prompt),
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


@main.command("diagnose")
@click.option("--url", required=True, help="Page URL to diagnose.")
@click.option("--diagnostics-dir", default=str(general_settings.diagnostics_dir))
@click.option("--browser", type=click.Choice(["auto", "camoufox", "playwright"]), default=None)
def diagnose(url: str, diagnostics_dir: str, browser: str | None):
    try:
        asyncio.run(_diagnose(url=url, diagnostics_dir=Path(diagnostics_dir), browser=browser))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


async def _diagnose(url: str, diagnostics_dir: Path, browser: str | None) -> None:
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
            page = await browser_instance.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await save_page_artifacts(page, diagnostics_dir)
            finally:
                await browser_instance.close()

    write_text(
        diagnostics_dir / "repair_prompt.md",
        f"Manual diagnose run for {url}.",
    )
    print(f"Diagnostics saved to {diagnostics_dir}")


if __name__ == "__main__":
    sys.argv = rewrite_source_first_argv(sys.argv)
    main()
