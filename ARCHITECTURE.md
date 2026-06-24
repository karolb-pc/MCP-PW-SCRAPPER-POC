# MCP-PW-SCRAPPER Architecture

## Core Idea

The host is neutral. It does not own a default scraper and it does not know about a special `books` target.

Every scraper is addressed by path:

```bash
uv run python main.py run --path <source-path>
uv run python main.py audit --path <source-path> --fix
uv run python main.py repair --path <source-path>
uv run python main.py semi-discover --path <source-path>
uv run python main.py break --path <source-path>
```

`<source-path>` can be:

- a folder scraper with `scraper_target.json`, for example `scrapers/books`
- a discovery run folder, for example `scrapers/discovery/<timestamp>`
- the `generated/` folder inside a discovery run

## Layers

```text
main.py
  command-first CLI
  target resolution
  host orchestration

src/scraper_target.py
  resolves source paths into ScraperTarget objects

src/discovery/
  full discovery:
  URL + prompt -> generated/extractor.py + transformer.py + loader.py

src/semi_discovery/
  extends an existing scraper target in place

src/agents/
  shared LLM provider selection, credentials handling, process execution,
  terminal events, and provider-specific agent wrappers

src/audit/
  source/code audit domain

src/breaker/
  LLM-assisted scraper break test domain

src/repair/
  self-repair loop orchestration for a selected scraper target

src/diagnostics/
  shared page/error/prompt artifacts

src/contracts/
  shared ETL base abstractions and generic local JSON loader

scrapers/
  concrete scraper implementations
```

## Scraper Target Resolution

For a discovery run, `src/scraper_target.py` reads:

```text
request.json
user_prompt.md
generated/extractor.py
generated/transformer.py
generated/loader.py
```

For a folder scraper, it reads:

```text
scraper_target.json
```

The resolved target exposes:

```text
name
kind
root_dir
source_url
files
allowed_paths
run_command
verification_command
output_path
```

The LLM can inspect `files`, but may patch only `allowed_paths`.

## Folder Scraper Contract

Folder scrapers provide their own local code and a manifest:

```text
scrapers/books/
  scraper_target.json
  main.py
  etl.py
  settings.py
  extractor/books.py
  transformer/books.py
  validator/books.py
  models/book.py
```

The host runs the scraper through `run_command` from the manifest. The host audits, repairs, and extends the scraper using metadata from the same manifest.

## Command-First CLI

The user-facing form is:

```bash
uv run python main.py run --path scrapers/books --quiet --browser playwright
uv run python main.py audit --path scrapers/books --openai --fix
uv run python main.py repair --path scrapers/books --openai
uv run python main.py semi-discover --path scrapers/books --openai --prompt "Add stock status."
uv run python main.py break --path scrapers/books --openai
```

Source-first shorthand calls are only a convenience rewrite. The canonical form is command-first with `--path`.

## Discovery Run Flow

```text
discover
  |
  +--> ask/read user scrape prompt
  +--> run selected LLM agent
  +--> agent must use Playwright MCP/browser MCP
  +--> generated/extractor.py
  +--> generated/transformer.py
  +--> generated/loader.py
  +--> host executes Extract -> Transform -> Load JSON
```

Generated classes must keep the standard shape:

```text
DiscoveryExtractor(AbstractExtractor)
DiscoveryTransformer(AbstractTransformer)
DiscoveryLoader(AbstractLoader)
```

## Audit And Repair Flow

Audit:

```text
source path -> target metadata -> LLM agent -> Playwright MCP DOM audit -> optional patch -> verification command
```

Self-repair:

```text
run scraper
  |
  +--> failure
  +--> write repair_prompt.md
  +--> selected LLM agent uses Playwright MCP
  +--> patch only allowed_paths
  +--> retry verification/run command
```

Break demo:

```text
source path -> selected LLM agent -> introduce one realistic scraper bug in allowed_paths
```

There is no fake agent flow in the documented scenarios.

## Credentials

Credentials are never passed in CLI args. They come from environment or `.env`:

```env
LOGIN=user@example.com
PASSWORD=secret
```

Then:

```bash
uv run python main.py audit --path scrapers/books --use-credentials --openai --fix
```

Prompts saved to diagnostics are redacted.

## Local Environment

Repository code should not contain developer-specific absolute paths. Local paths and tool
locations are configured through environment variables or `.env`:

```env
CODEX_CLI_PATH=<absolute-path-to-codex>
CLAUDE_CLI_PATH=<absolute-path-to-claude>
SCRAPER_DISCOVERY_RUNS_DIR=scrapers/discovery
SCRAPER_DISCOVERY_OUTPUT=output/discovery.json
SCRAPER_DIAGNOSTICS_DIR=diagnostics/latest
```

When these values are not set, the host uses repository-relative defaults and resolves
`codex`/`claude` from `PATH`.

## Books Example

Books is just one folder target:

```bash
uv run python main.py run --path scrapers/books --quiet --browser playwright
uv run python main.py validate scrapers/books/output/books.json
```

Its scraper code is not in `src/`. It lives under `scrapers/books/` and is discovered through `scraper_target.json`.
