# MCP-PW-SCRAPPER

`MCP-PW-SCRAPPER` is a POC for folder-based scrapers that can be run, audited, extended, broken for repair tests, and self-repaired by an LLM agent.

The important rule is simple:

```bash
uv run python main.py <command> --path <scraper-folder-or-discovery-run>
```

There is no privileged scraper in `main.py`. The old Books scraper now lives under `scrapers/books/` like any other scraper target.

## Quick Start

```bash
uv sync
uv run playwright install chromium
uv run python main.py run --path scrapers/books --quiet --browser playwright
uv run python main.py validate scrapers/books/output/books.json
```

Expected output:

- `scrapers/books/output/books.json`
- `scrapers/books/data/successful/latest.json`
- a timestamped export under `scrapers/books/data/successful/`

## Command-First CLI

Use the scraper path first:

```bash
uv run python main.py run --path scrapers/books --quiet --browser playwright
uv run python main.py audit --path scrapers/books --openai --fix
uv run python main.py repair --path scrapers/books --openai --browser playwright
uv run python main.py semi-discover --path scrapers/books --openai --prompt "Add stock status."
uv run python main.py break --path scrapers/books --openai
```

The same pattern works for generated discovery runs:

```bash
uv run python main.py run --path scrapers/discovery/<timestamp>
uv run python main.py audit --path scrapers/discovery/<timestamp> --fix --openai
uv run python main.py repair --path scrapers/discovery/<timestamp> --openai
uv run python main.py semi-discover --path scrapers/discovery/<timestamp> --openai --prompt "Add rating."
uv run python main.py break --path scrapers/discovery/<timestamp> --openai
```



## Scraper Folder Contract

Every non-discovery scraper folder must contain `scraper_target.json`.

Example:

```json
{
  "name": "books",
  "kind": "folder_etl",
  "source_url": "https://books.toscrape.com/",
  "files": [
    "main.py",
    "etl.py",
    "extractor/books.py",
    "transformer/books.py",
    "validator/books.py",
    "models/book.py",
    "settings.py"
  ],
  "allowed_paths": [
    "etl.py",
    "extractor/books.py",
    "transformer/books.py",
    "validator/books.py",
    "models/book.py",
    "settings.py"
  ],
  "run_command": [
    "uv",
    "run",
    "python",
    "-m",
    "scrapers.books.main",
    "run",
    "--quiet",
    "--browser",
    "playwright"
  ],
  "verification_command": [
    "uv",
    "run",
    "python",
    "-m",
    "scrapers.books.main",
    "run",
    "--quiet",
    "--browser",
    "playwright"
  ],
  "output_path": "output/books.json"
}
```

The host uses this manifest to infer:

- source URL
- files to inspect
- files the LLM may patch
- run command
- verification command
- output path

## Discovery

Full discovery starts from a URL and a user prompt:

```bash
uv run python main.py discover \
  --url https://books.toscrape.com/ \
  --openai \
  --prompt "Scrape book title, price, category and URL, but keep the first scraper intentionally small." \
  --output output/discovery-books.json
```

Discovery creates:

```text
scrapers/discovery/<timestamp>/
  request.json
  user_prompt.md
  design_prompt.md
  design_summary.md
  generated/extractor.py
  generated/transformer.py
  generated/loader.py
  raw_items.json
  output.json
```

`scrapers/discovery/*` is ignored by git, except `scrapers/discovery/.gitkeep`.
The folder exists in the repo, but generated discovery scrapers do not get committed by accident.

Generated discovery scrapers use the same command-first CLI:

```bash
uv run python main.py run --path scrapers/discovery/<timestamp>
uv run python main.py audit --path scrapers/discovery/<timestamp> --fix --openai
uv run python main.py repair --path scrapers/discovery/<timestamp> --openai
uv run python main.py semi-discover --path scrapers/discovery/<timestamp> --openai --prompt "Add availability."
```

## Credentials

Never pass login/password directly in CLI args. Use `.env`:

```env
LOGIN=user@example.com
PASSWORD=secret
```

Then pass:

```bash
uv run python main.py audit --path scrapers/books --use-credentials --openai --fix
```

The agent prompt receives credentials only through the controlled credentials block, and logs/prompts written to diagnostics are redacted.

## Local Environment Overrides

Use `.env.example` as the template for local configuration:

```bash
cp .env.example .env
```

Useful local overrides:

```env
CODEX_CLI_PATH=<absolute-path-to-codex>
CLAUDE_CLI_PATH=<absolute-path-to-claude>
SCRAPER_DISCOVERY_RUNS_DIR=scrapers/discovery
SCRAPER_DISCOVERY_OUTPUT=output/discovery.json
SCRAPER_DIAGNOSTICS_DIR=diagnostics/latest
SCRAPER_AUDIT_DIAGNOSTICS_DIR=diagnostics/source-audit
SCRAPER_BREAK_DIAGNOSTICS_DIR=diagnostics/llm-break-demo
SCRAPER_SEMI_DISCOVERY_DIAGNOSTICS_DIR=diagnostics/semi-discovery
```

Leave these unset when the defaults work. Real `.env` files are local-only and ignored by git.

## LLM Providers

Use one provider flag:

```bash
uv run python main.py audit --path scrapers/books --openai --fix
uv run python main.py audit --path scrapers/books --claude --fix
```

OpenAI/Codex and Claude commands are built centrally in `src/agents/provider.py`. Shared credentials, process execution, terminal events, and provider wrappers live under `src/agents/` because discovery, semi-discovery, audit, break, and repair all use the same agent runtime. `src/repair/` only owns the self-repair orchestration loop.

## Playwright MCP

LLM-driven discovery, audit, semi-discovery, break, and repair prompts require Playwright MCP/browser MCP. The agent is instructed to inspect the live source with browser MCP before changing scraper code.

Local scraper execution itself can use normal Playwright Python:

```bash
uv run python main.py run --path scrapers/books --quiet --browser playwright
```

## Project Layout

```text
main.py
  command-first host CLI and orchestration

src/
  shared host infrastructure:
  discovery, repair, diagnostics, notification, target resolution,
  ETL base classes and shared loader abstractions

scrapers/books/
  example folder-based scraper target:
  scraper_target.json, local main.py, ETL, extractor, transformer,
  validator, model, settings, output and exports

scrapers/discovery/
  generated scraper runs created by full discovery
```

## Useful Commands

```bash
uv run python -m compileall main.py scraper.py src scrapers
uv run python main.py run --path scrapers/books --quiet --browser playwright
uv run python main.py validate scrapers/books/output/books.json
uv run python main.py audit --path scrapers/books --openai --fix
uv run python main.py break --path scrapers/books --openai
uv run python main.py repair --path scrapers/books --openai --browser playwright
```
