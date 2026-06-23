# MCP-PW-SCRAPPER Architecture

## 1. Purpose

`MCP-PW-SCRAPPER` is a small Python scraping proof of concept built as a layered ETL pipeline for `https://books.toscrape.com/`.

The project started as a scraper script and was refactored into a structure similar to larger ETL projects:

```text
main.py -> BooksToScrapeETL -> extractor -> transformer -> validator -> loader
```

The runtime can also run a self-repair loop:

```text
failure -> diagnostics -> mock notification -> codex exec -> retry
```

## 2. High-Level Architecture

```text
main.py
  |
  +--> run
  |     |
  |     +--> BooksToScrapeETL(config=CONFIG)
  |     |     |
  |     |     +--> extractor: src/etl/extractor/books.py
  |     |     +--> transformer: src/etl/transformer/books.py
  |     |     +--> validator: src/etl/validator/books.py
  |     |     +--> loader: src/etl/loader/local_json.py
  |     |
  |     +--> optional BooksToScrapeAutoRepairRunner
  |
  +--> validate
  |
  +--> diagnose
  |
  +--> break-selector-demo
  |
  +--> llm-break-demo
```

The normal ETL output is:

```text
output/books.json
data/successful/books-<timestamp>.json
data/successful/latest.json
```

Failure and repair artifacts are written under:

```text
diagnostics/<run-name>/
notifications/<run-name>/
```

## 3. Main Modules

```text
main.py
  Click CLI. This is the preferred entrypoint.

scraper.py
  Compatibility wrapper for old commands. It delegates to main.py.

src/config/general.py
  Default runtime settings and SCRAPER_* environment fallbacks.

src/etl/base.py
  BaseETL helper that builds extractor, transformer, validator, and loader from CONFIG.

src/etl/books.py
  BooksToScrapeETL and CONFIG for the current Books to Scrape pipeline.

src/etl/runner.py
  Auto-repair orchestration, retry loop, repair_report.json events, and mock notifications.

src/etl/extractor/books.py
  Browser scraping layer. Uses Camoufox or Playwright and returns raw book records.

src/etl/transformer/books.py
  Maps raw records into the stable JSON payload.

src/etl/validator/books.py
  Validates the final payload contract.

src/etl/loader/local_json.py
  Writes local JSON output and successful exports.

src/diagnostics/artifacts.py
  Writes page HTML, screenshots, error payloads, partial payloads, and repair prompts.

src/diagnostics/repair_report.py
  Writes repair_report.json with structured self-repair events.

src/notification/mock_email.py
  Mock email notifier. It writes .txt files to a local outbox.

src/repair/codex.py
  Runs codex exec for self-repair and writes codex_repair.log.

src/repair/demo_breaker.py
  Runs codex exec to intentionally introduce one realistic scraper bug for self-repair demos.
```

## 4. Normal Scraping Flow

```text
uv run python main.py run --quiet --browser playwright
      |
      v
Click command: run
      |
      v
BooksToScrapeETL(config=CONFIG)
      |
      +--> extract(browser_mode, diagnostics_dir)
      |       |
      |       +--> Playwright or Camoufox
      |       +--> https://books.toscrape.com/
      |       +--> raw records:
      |             title, price, ratingClass, availability, relativeUrl
      |
      +--> transform(raw_books)
      |       |
      |       +--> Book dataclass records
      |       +--> source + summary + items payload
      |
      +--> validate(payload)
      |       |
      |       +--> BooksPayloadValidator
      |
      +--> load(payload)
              |
              +--> output/books.json
              +--> data/successful/books-<timestamp>.json
              +--> data/successful/latest.json
```

## 5. Data Contract

The final payload contains:

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

- `items` must be a list.
- `items` must contain at least one record.
- `summary.items` must match the number of records.
- each item must have `title`;
- `price_gbp` must be numeric;
- `rating` must be `null` or an integer from `1` to `5`;
- `availability` must be present;
- `absolute_url` must start with `https://`.

## 6. Diagnostics Flow

When the ETL fails, `BooksToScrapeETL.run()` writes diagnostics before re-raising the error:

```text
diagnostics/<run-name>/error.log
diagnostics/<run-name>/error.json
diagnostics/<run-name>/partial.json
diagnostics/<run-name>/repair_prompt.md
```

If the failure happens while a browser page is available, the scraper can also write:

```text
diagnostics/<run-name>/page.html
diagnostics/<run-name>/screenshot.png
```

Manual page diagnostics can be collected with:

```bash
uv run python main.py diagnose \
  --browser playwright \
  --diagnostics-dir diagnostics/manual-check
```

## 7. Auto-Repair Flow

Auto-repair is enabled by `--auto-repair`.

```text
uv run python main.py run --quiet --auto-repair --browser playwright
      |
      v
BooksToScrapeAutoRepairRunner
      |
      +--> ETL attempt
      |
      +--> on success:
      |       finish
      |
      +--> on failure:
              diagnostics/*
              repair_report.json event
              mock email: scraper run failed
              CodexRepairAgent
              codex exec
              codex_repair.log
              retry ETL
```

Default repair settings:

```text
repair_attempts = 5
repair_timeout = 900 seconds
notify_email = scraper-ops@example.local
notifications_dir = notifications/mock-email-outbox
```

`CodexRepairAgent` runs:

```text
codex exec --cd <project-root> --sandbox workspace-write --skip-git-repo-check -
```

It sends `repair_prompt.md` through stdin and writes:

```text
diagnostics/<run-name>/codex_repair.log
```

## 8. Structured Repair Report

Every auto-repair run writes:

```text
diagnostics/<run-name>/repair_report.json
```

The report records events such as:

```text
auto_repair_run_started
etl_attempt_started
etl_attempt_failed
notification_sent
repair_attempt_started
repair_attempt_finished
repair_report_succeeded
repair_report_failed
```

The repair result also includes file-change information:

```text
changed_files_before_repair
changed_files_after_repair
changed_project_files
```

`changed_project_files` is calculated from hashes of Python project files, so it still works even when `git diff` is not available or the project is not visible as a Git repository to the subprocess.

## 9. Demo: Hardcoded Selector Break

This command intentionally breaks the main product card selector in `src/etl/extractor/books.py`:

```bash
uv run python main.py break-selector-demo
```

It changes:

```text
article.product_pod
```

to:

```text
article.product_pod_broken_for_repair_demo
```

Then run real auto-repair without `--simulate-failure`:

```bash
uv run python main.py run --quiet --auto-repair \
  --repair-attempts 1 \
  --repair-timeout 900 \
  --browser playwright \
  --diagnostics-dir diagnostics/real-self-fix-selector \
  --notifications-dir notifications/real-self-fix-selector
```

Manual restore:

```bash
uv run python main.py break-selector-demo --restore
```

This scenario is deterministic and useful for checking that the repair loop, notifications, retry, logs, and `repair_report.json` work.

## 10. Demo: LLM-Introduced Scraper Break

`llm-break-demo` is closer to a real repair scenario. It runs a separate `codex exec` task that introduces exactly one realistic scraper bug in:

```text
src/etl/extractor/
src/etl/transformer/
```

It is instructed not to edit diagnostics, repair code, notifier code, docs, output files, or test the scraper.

Run:

```bash
uv run python main.py llm-break-demo \
  --diagnostics-dir diagnostics/llm-break-demo \
  --break-timeout 900
```

It writes:

```text
diagnostics/llm-break-demo/llm_break_report.json
diagnostics/llm-break-demo/llm_break_prompt.md
diagnostics/llm-break-demo/llm_break.log
```

Then run the real self-repair:

```bash
uv run python main.py run --quiet --auto-repair \
  --repair-attempts 1 \
  --repair-timeout 900 \
  --browser playwright \
  --diagnostics-dir diagnostics/llm-self-fix \
  --notifications-dir notifications/llm-self-fix
```

Repair output:

```text
diagnostics/llm-self-fix/repair_report.json
diagnostics/llm-self-fix/codex_repair.log
notifications/llm-self-fix/*.txt
```

This scenario is not tied to a single hardcoded break. The first LLM introduces a realistic scraper drift, and the repair LLM must identify the cause from diagnostics, current HTML, and the data contract.

## 11. Failure Simulation

The `run` command supports simulated failures:

```text
--simulate-failure selector
--simulate-failure transform
--simulate-failure validation
--simulate-failure export
```

Example:

```bash
uv run python main.py run --quiet --auto-repair \
  --repair-attempts 0 \
  --browser playwright \
  --simulate-failure transform \
  --diagnostics-dir diagnostics/mock-transform \
  --notifications-dir notifications/mock-transform-outbox
```

These modes are good for testing diagnostics and notifications. They are not good for testing successful self-repair because the simulated failure is injected on every retry.

## 12. Commands

Normal run:

```bash
uv run python main.py run --quiet --browser playwright
```

Run with auto-repair:

```bash
uv run python main.py run --quiet --auto-repair --browser playwright
```

Validate existing output:

```bash
uv run python main.py validate output/books.json
```

Collect page diagnostics:

```bash
uv run python main.py diagnose --browser playwright --diagnostics-dir diagnostics/manual-check
```

Break fixed selector demo:

```bash
uv run python main.py break-selector-demo
```

Run LLM break demo:

```bash
uv run python main.py llm-break-demo --diagnostics-dir diagnostics/llm-break-demo
```

## 13. Docker

The Dockerfile uses:

```text
python:3.12-slim
uv sync --frozen
uv run playwright install --with-deps chromium
```

Default container command:

```text
uv run python main.py run --quiet
```

Build and run:

```bash
docker build -t mcp-pw-scrapper .
docker run --rm mcp-pw-scrapper
```

## 14. Implemented

- layered ETL architecture;
- Click CLI;
- `CONFIG` + `BooksToScrapeETL`;
- Camoufox and Playwright extraction;
- raw records to JSON transformation;
- payload validator;
- local JSON loader;
- diagnostics artifacts;
- mock email outbox;
- Codex repair agent;
- structured `repair_report.json`;
- deterministic selector-break demo;
- LLM-generated scraper-break demo;
- retry-based self-repair;
- Dockerfile.

## 15. Not Implemented Yet

- real GCS loader;
- real BigQuery loader;
- real SMTP, SendGrid, or Mailgun notifier;
- Cloud Scheduler configuration;
- Cloud Monitoring alert policy;
- unit and integration tests;
- CI/CD or PR-based deployment flow.
