# MCP-PW-SCRAPPER

`poc-simplest` is a direct-discovery POC: provide a URL, a prompt, and an output format, and an LLM agent uses Playwright MCP/browser MCP to scrape the page immediately.

There is no generated scraper code in this flow. The agent must not create extractor, transformer, loader, or reusable scraper scripts. It inspects the live page, performs the requested browser actions, and writes the final data file.

The alternative `generated-code` mode asks the agent to inspect the page first, write a disposable scraper script for that specific page and prompt, execute that script, then remove the generated code. This keeps the final output and metrics while separating artifacts from the direct-discovery runs.

## Quick Start

Discovery commands below default to `--openai`. Use `--claude` in the same position when you want to run the same scrape through Claude.

```bash
uv sync
uv run playwright install chromium
uv run python main.py discover --openai \
  --url "https://books.toscrape.com/" \
  --prompt "Scrape the first page of books with title, price, availability, rating, and absolute URL." \
  --output output/agent_discovery/books.json \
  --output-format json
```

## How To Run Scenarios

Install dependencies once:

```bash
uv sync
uv run playwright install chromium
```

Run the default Codex/OpenAI path:

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks.md
```

Run the same scenario through Claude:

```bash
uv run python main.py discover --claude \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks.md
```

Run the generated-code path with separate default output, run, and diagnostics locations:

```bash
uv run python main.py discover-code --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks.md \
  --output-format json
```

Or use the same `discover` command with a mode switch:

```bash
uv run python main.py discover --openai \
  --mode generated-code \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks.md \
  --output-format json
```

More ready-to-run scenarios are in `DISCOVERY_TEST_SCENARIOS.md` and `instructions/amazon/README.md`.

The same command can be run through the direct root options:

```bash
uv run python main.py \
  --url "https://books.toscrape.com/" \
  --prompt "Scrape book titles and prices from the first page."
```

## Output

For JSON output, the agent is instructed to write a JSON object like:

```json
{
  "source_url": "https://example.com",
  "user_prompt": "Scrape ...",
  "items": [],
  "meta": {
    "mode": "direct_agent_discovery"
  }
}
```

Validate JSON outputs with:

```bash
uv run python main.py validate output/books.json
```

## Run Artifacts And Diagnostics

Each discovery run creates an artifact folder under:

```text
output/agent_discovery/runs/<timestamp>/
```

Typical files:

```text
request.json
user_prompt.md
scrape_prompt.md
openai_direct_discovery.log
scrape_summary.md
output.json
```

Each scrape also creates a diagnostics folder under:

```text
output/agent_discovery/metrics/<timestamp>-<provider>-<prompt-slug>-<source-slug>/
```

Typical diagnostics files:

```text
request.json
user_prompt.md
scrape_prompt.md
openai_direct_discovery.log
scrape_summary.md
metrics.json
summary.md
output.json
```

`metrics.json` is host-generated and includes total time, prepare time, whole agent process time, output validation time, longest host phase, and item count. It does not split agent-internal scraping from processing.

The run folder and diagnostics folder are not scraper projects.

Generated-code discovery runs default to:

```text
output/generated_code_discovery/runs/<timestamp>/
output/generated_code_discovery/metrics/<timestamp>-<provider>-<prompt-slug>-<source-slug>/
```

The agent receives a temporary `generated-code-workspace` inside the run folder. The host removes that workspace after the agent process exits, so the retained artifacts are the prompt/logs/output copies and metrics, not the generated scraper source.

## Sessions

Browser session profiles remain available for authenticated or stateful pages:

```bash
uv run python main.py discover --openai \
  --url "https://example.com/account/orders" \
  --prompt "Scrape the visible order list." \
  --session-profile example-private
```

Session profiles live under `sessions/<profile>/` and record usage in `usage.jsonl`. Configure Playwright MCP/browser MCP with the paths shown in `sessions/<profile>/session.md` when the MCP server itself needs to reuse cookies or local storage.

## Credentials

For login-required flows, copy `.env.example` to `.env` and set:

```bash
LOGIN=
PASSWORD=
```

Then run with `--use-credentials`. Credentials are passed to the agent prompt through a redacted logging path and must not be written to outputs.

## Diagnostics

Use `diagnose` for a plain Playwright/Camoufox page snapshot:

```bash
uv run python main.py diagnose \
  --url "https://books.toscrape.com/" \
  --diagnostics-dir diagnostics/books
```

Amazon prompt variants live under `instructions/amazon/`, for example:

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks.md
```

To compare a deep link with agent-driven navigation from the Amazon.com homepage:

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-home-to-macbooks.md
```

Compare its `metrics.json` with the deep-link run. The homepage variant should usually have a longer `agent_elapsed_seconds` / `timings_seconds.agent_scrape` because the agent must open Amazon, handle consent if needed, use search, and wait for results.

## Configuration

Useful environment variables:

```bash
CODEX_CLI_PATH=
CLAUDE_CLI_PATH=
SCRAPER_AGENT_PROVIDER=openai
SCRAPER_DISCOVERY_OUTPUT=output/agent_discovery/discovery.json
SCRAPER_DISCOVERY_RUNS_DIR=output/agent_discovery/runs
SCRAPER_DISCOVERY_DIAGNOSTICS_DIR=output/agent_discovery/metrics
SCRAPER_GENERATED_CODE_OUTPUT=output/generated_code_discovery/discovery.json
SCRAPER_GENERATED_CODE_RUNS_DIR=output/generated_code_discovery/runs
SCRAPER_GENERATED_CODE_DIAGNOSTICS_DIR=output/generated_code_discovery/metrics
SCRAPER_SESSIONS_DIR=sessions
```

## Claude MCP setup

Claude Code uses its own MCP configuration. This project includes `config/claude.mcp.json` with the Playwright MCP server:

```bash
claude mcp list
```

If the `playwright` server is shown as pending, run Claude once in this project and approve the project MCP server:

```bash
claude
```

Then verify:

```bash
claude mcp get playwright
```

After that, Claude-backed discovery can use browser tools:

```bash
uv run python main.py discover --claude \
  --url "https://www.amazon.com/gp/bestsellers/" \
  --prompt-file instructions/amazon/amazon-com-bestsellers.md \
  --output output/amazon-com-bestsellers.json
```

The project runner starts Claude in print/streaming mode with `config/claude.mcp.json`, strict MCP config, no Chrome integration, and headless Playwright MCP. You should see progress in the terminal only, not a visible browser window.

## Verification

```bash
uv run python -m compileall main.py src
uv run python main.py --help
```
