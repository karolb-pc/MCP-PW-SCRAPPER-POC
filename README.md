# MCP-PW-SCRAPPER

`MCP-PW-SCRAPPER` is a small Python scraping proof of concept for `https://books.toscrape.com/`.

It is structured as a layered ETL pipeline:

```text
main.py -> BooksToScrapeETL -> extractor -> transformer -> validator -> loader
```

Normal pipeline:

```text
scrape -> transform -> validate -> export/load
```

Self-repair pipeline:

```text
failure -> diagnostics -> mock email -> codex exec -> patch -> retry
```

`scraper.py` remains as a compatibility wrapper. Prefer `main.py` for all new usage.

## Quick Start

```bash
cd /Users/karol/Desktop/PC/projects/MCP-PW-SCRAPPER
uv sync
uv run playwright install chromium
uv run python main.py run --quiet --browser playwright
```

This will:

1. scrape `https://books.toscrape.com/`,
2. transform raw DOM records into JSON,
3. validate the output contract,
4. write `output/books.json`,
5. export `data/successful/latest.json`,
6. export a timestamped snapshot under `data/successful/`.

Validate the output:

```bash
uv run python main.py validate output/books.json
```

## Project Structure

```text
main.py
  Click CLI and preferred entrypoint.

scraper.py
  Compatibility wrapper that delegates to main.py.

src/config/general.py
  Default settings and SCRAPER_* environment fallbacks.

src/etl/base.py
  BaseETL helper that builds extractor, transformer, validator, and loader from CONFIG.

src/etl/books.py
  BooksToScrapeETL and CONFIG.

src/etl/extractor/books.py
  Camoufox/Playwright scraping logic.

src/etl/transformer/books.py
  Raw scraped records -> stable JSON payload.

src/etl/validator/books.py
  Payload contract validation.

src/etl/loader/local_json.py
  Local JSON output and export writer.

src/etl/runner.py
  Auto-repair loop, retry orchestration, mock notifications, and repair_report.json events.

src/diagnostics/artifacts.py
  page.html, screenshot.png, error.json, error.log, partial.json, repair_prompt.md.

src/diagnostics/repair_report.py
  Structured JSON event report for self-repair runs.

src/notification/mock_email.py
  Mock email outbox implemented as .txt files.

src/repair/codex.py
  Codex repair agent. Runs codex exec and writes codex_repair.log.

src/repair/demo_breaker.py
  LLM-powered controlled breaker for self-repair demos.
```

## Commands

Normal run:

```bash
uv run python main.py run --quiet --browser playwright
```

Run with browser auto mode:

```bash
uv run python main.py run --quiet
```

Run with self-repair:

```bash
uv run python main.py run --quiet --auto-repair --browser playwright
```

Validate an existing output file:

```bash
uv run python main.py validate output/books.json
```

Collect current page HTML, screenshot, and repair prompt:

```bash
uv run python main.py diagnose \
  --browser playwright \
  --diagnostics-dir diagnostics/manual-check
```

Proactively audit the live source and compare it with scraper code:

```bash
uv run python main.py source-audit \
  --diagnostics-dir diagnostics/source-audit \
  --browser playwright
```

Proactively audit and allow Codex to patch scraper code if source drift is found:

```bash
uv run python main.py source-audit \
  --fix \
  --diagnostics-dir diagnostics/source-audit-fix \
  --browser playwright
```

Compatibility wrapper:

```bash
uv run python scraper.py run --quiet --browser playwright
```

## Runtime Options

Important `run` options:

```text
--output
  Path for the primary output JSON. Default: output/books.json

--diagnostics-dir
  Directory for error artifacts and repair logs. Default: diagnostics/latest

--export-dir
  Directory for successful timestamped exports and latest.json. Default: data/successful

--notifications-dir
  Directory for mock email .txt files. Default: notifications/mock-email-outbox

--notify-email
  Recipient written into mock email files. Default: scraper-ops@example.local

--browser auto|camoufox|playwright
  Browser backend. For deterministic local demos, prefer playwright.

--quiet
  Suppresses full payload printing. Status JSON is still printed.

--auto-repair
  Enables diagnostics, mock notifications, codex exec repair, and retry.

--repair-attempts
  Number of repair attempts after the initial failure. Default: 5

--repair-timeout
  Timeout for each codex repair process in seconds. Default: 900

--repair-command
  Optional custom repair command instead of the default codex exec command.

--simulate-failure none|selector|transform|validation|export
  Injects a controlled failure for diagnostics testing.
```

Environment fallbacks are defined in `src/config/general.py`:

```text
SCRAPER_OUTPUT
SCRAPER_DIAGNOSTICS_DIR
SCRAPER_EXPORT_DIR
SCRAPER_NOTIFICATIONS_DIR
SCRAPER_NOTIFY_EMAIL
SCRAPER_BROWSER
SCRAPER_REPAIR_ATTEMPTS
SCRAPER_REPAIR_TIMEOUT
SCRAPER_REPAIR_COMMAND
```

## Data Contract

The output payload contains:

```text
source:
  name
  url
  scraped_at

summary:
  items
  available_items
  average_price_gbp
  min_price_gbp
  max_price_gbp
  top_rated_count

items:
  - title
    price_gbp
    rating
    availability
    relative_url
    absolute_url
```

`BooksPayloadValidator` requires:

- `items` is a non-empty list;
- `summary.items` matches `len(items)`;
- each item has `title`;
- `price_gbp` is numeric;
- `rating` is `null` or an integer from `1` to `5`;
- `availability` is present;
- `absolute_url` starts with `https://`.

## Diagnostics

Manual diagnostics:

```bash
uv run python main.py diagnose \
  --browser playwright \
  --diagnostics-dir diagnostics/live-page-check
```

Expected artifacts:

```text
diagnostics/live-page-check/page.html
diagnostics/live-page-check/screenshot.png
diagnostics/live-page-check/repair_prompt.md
```

On ETL failure, the pipeline writes:

```text
diagnostics/<run-name>/error.json
diagnostics/<run-name>/error.log
diagnostics/<run-name>/partial.json
diagnostics/<run-name>/repair_prompt.md
```

If page capture is available, it also writes:

```text
diagnostics/<run-name>/page.html
diagnostics/<run-name>/screenshot.png
```

## Self-Repair

Run with real self-repair:

```bash
uv run python main.py run --quiet --auto-repair \
  --repair-attempts 5 \
  --repair-timeout 900 \
  --browser playwright \
  --diagnostics-dir diagnostics/latest \
  --notifications-dir notifications/mock-email-outbox
```

On failure:

1. ETL writes diagnostics.
2. `BooksToScrapeAutoRepairRunner` writes a structured event to `repair_report.json`.
3. `MockEmailNotifier` writes a mock `Scraper run failed` email.
4. `CodexRepairAgent` runs `codex exec`.
5. Codex receives `repair_prompt.md` through stdin.
6. Codex can inspect the page and patch scraper code.
7. The runner retries the ETL in a fresh Python subprocess, so patched source files are re-imported from disk.
8. On recovery, it writes a mock `Scraper recovered after repair` email.
9. On exhaustion, it writes a mock `manual intervention required` email.

Default repair command:

```text
codex exec --cd <project-root> --sandbox workspace-write --skip-git-repo-check -
```

Repair artifacts:

```text
diagnostics/<run-name>/repair_report.json
diagnostics/<run-name>/codex_repair.log
notifications/<run-name>/*.txt
```

Long-running Codex subprocesses stream progress to the CLI. You should see lines such as:

```text
[codex_repair] started pid=12345
[codex_repair] writing detailed log to diagnostics/.../codex_repair.log
[codex_repair] | running 2.0s / 900s
[codex_repair] / running 4.0s / 900s
[codex_repair] finished returncode=0 elapsed=42.5s
[codex_repair] detailed log: diagnostics/.../codex_repair.log
```

The spinner frames rotate between `|`, `/`, `-`, and `\`. Full stdout/stderr from Codex is written to the detailed log instead of being streamed line-by-line to the terminal.

`repair_report.json` records events such as:

```text
auto_repair_run_started
etl_attempt_started
etl_attempt_failed
notification_sent
repair_attempt_started
repair_attempt_finished
fresh_retry_subprocess_started
fresh_retry_subprocess_finished
repair_report_succeeded
repair_report_failed
```

It also records file-change information:

```text
changed_files_before_repair
changed_files_after_repair
changed_project_files
```

`changed_project_files` is calculated from Python file hashes, so it works even when `git diff` is unavailable.

## Proactive Source Audit

`source-audit` is an explicit command for checking the live source before a normal scraper failure happens.

Inspect-only mode:

```bash
uv run python main.py source-audit \
  --diagnostics-dir diagnostics/source-audit \
  --audit-timeout 900 \
  --source-url https://books.toscrape.com/ \
  --browser playwright
```

Inspect-and-fix mode:

```bash
uv run python main.py source-audit \
  --fix \
  --diagnostics-dir diagnostics/source-audit-fix \
  --audit-timeout 900 \
  --source-url https://books.toscrape.com/ \
  --browser playwright
```

The command runs `codex exec` with a prompt that asks Codex to:

1. open and inspect the live source page,
2. analyze current HTML/DOM and product-card selectors,
3. compare the source page with `src/etl/extractor/books.py` and `src/etl/transformer/books.py`,
4. either report findings only or patch minimal scraper code when `--fix` is used,
5. verify with `uv run python main.py run --quiet --browser <browser>` when code was changed,
6. write a structured report.

Audit artifacts:

```text
diagnostics/source-audit*/source_audit_report.json
diagnostics/source-audit*/source_audit_prompt.md
diagnostics/source-audit*/source_audit.log
diagnostics/source-audit*/source_audit_fresh_verification.log
```

When `--fix` is used, the command also runs a fresh Python subprocess after Codex exits:

```text
source_audit_fresh_verification_started
source_audit_fresh_verification_finished
```

This ensures that patched scraper files are re-imported from disk, instead of relying on code that may already be loaded in memory.

Optional credentials:

```bash
uv run python main.py source-audit \
  --fix \
  --source-url https://example.com/private/catalog \
  --credentials "login@example.com" "password-value" \
  --diagnostics-dir diagnostics/private-source-audit
```

Credentials are passed to Codex through stdin only when this command runs. Saved prompts, logs, and reports redact credential values. Shell history can still contain command-line credentials, so use this option carefully.

## Playwright MCP For Repair

The repair prompt asks Codex to use Playwright MCP when needed. Add it to Codex with:

```bash
codex mcp add playwright -- npx -y @playwright/mcp@latest --headless
```

The scraper itself does not require Playwright MCP. It requires the Python `playwright` package and a browser install.

## Failure Simulation

Quick diagnostics test without starting Codex:

```bash
uv run python main.py run --quiet --auto-repair \
  --repair-attempts 0 \
  --browser playwright \
  --simulate-failure transform \
  --diagnostics-dir diagnostics/mock-transform \
  --notifications-dir notifications/mock-transform-outbox
```

Available simulated failures:

```text
--simulate-failure selector
--simulate-failure transform
--simulate-failure validation
--simulate-failure export
```

Use these to test diagnostics and mock notifications.

Do not use `--simulate-failure` to test successful self-repair. The failure is injected on every retry, so recovery is intentionally blocked.

## Demo: Deterministic Selector Break

This demo intentionally breaks the real product-card selector in `src/etl/extractor/books.py`:

```bash
uv run python main.py break-selector-demo
```

Then run auto-repair without `--simulate-failure`:

```bash
uv run python main.py run --quiet --auto-repair \
  --repair-attempts 1 \
  --repair-timeout 900 \
  --browser playwright \
  --diagnostics-dir diagnostics/real-self-fix-selector \
  --notifications-dir notifications/real-self-fix-selector
```

Check the structured repair report:

```bash
cat diagnostics/real-self-fix-selector/repair_report.json
```

Check the Codex repair log:

```bash
tail -n 160 diagnostics/real-self-fix-selector/codex_repair.log
```

Manual restore if needed:

```bash
uv run python main.py break-selector-demo --restore
```

## Demo: LLM-Introduced Scraper Break

This demo is closer to a real repair scenario. One Codex process intentionally introduces exactly one realistic scraper bug under `src/etl/extractor/` or `src/etl/transformer/`. A later self-repair run must identify and fix it from diagnostics, current HTML, and the output contract.

Introduce the controlled LLM break:

```bash
uv run python main.py llm-break-demo \
  --diagnostics-dir diagnostics/llm-break-demo \
  --break-timeout 900
```

Breaker artifacts:

```text
diagnostics/llm-break-demo/llm_break_report.json
diagnostics/llm-break-demo/llm_break_prompt.md
diagnostics/llm-break-demo/llm_break.log
diagnostics/llm-break-demo/llm_break_summary.md
```

During the break step, the CLI streams concise `[llm_break]` progress lines and writes full Codex output to `llm_break.log`.
`llm_break_summary.md` contains the changed scraper files and the scraper diff, so it is the quickest way to see what was intentionally broken.

Run self-repair:

```bash
uv run python main.py run --quiet --auto-repair \
  --repair-attempts 1 \
  --repair-timeout 900 \
  --browser playwright \
  --diagnostics-dir diagnostics/llm-self-fix \
  --notifications-dir notifications/llm-self-fix
```

Repair artifacts:

```text
diagnostics/llm-self-fix/repair_report.json
diagnostics/llm-self-fix/codex_repair.log
notifications/llm-self-fix/*.txt
```

## Docker

Build:

```bash
docker build -t mcp-pw-scrapper .
```

Run:

```bash
docker run --rm mcp-pw-scrapper
```

The Dockerfile installs Chromium with:

```bash
uv run playwright install --with-deps chromium
```

Default container command:

```text
uv run python main.py run --quiet
```

## Current Limitations

- No real GCS loader.
- No real BigQuery loader.
- No real SMTP, SendGrid, or Mailgun notifier.
- No Cloud Scheduler configuration.
- No Cloud Monitoring alert policy.
- No unit/integration test suite yet.
- No CI/CD or PR-based deployment flow yet.
