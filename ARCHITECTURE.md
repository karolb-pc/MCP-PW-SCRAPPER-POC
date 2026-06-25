# MCP-PW-SCRAPPER Architecture

This branch is intentionally small. The host process does not generate scraper code and does not run stored scraper projects.

## Flow

```text
python CLI
  -> URL + user prompt + output format
  -> direct LLM agent command
  -> Playwright MCP/browser MCP live-page inspection
  -> final output file
  -> run artifacts + per-scrape diagnostics
```

## Active Modules

```text
main.py
  Click CLI for direct discovery, output validation, and diagnostics.

src/discovery/auto_scraper.py
  Direct agent orchestration. Builds the scrape prompt, runs the selected agent,
  validates the final output file, and records run metadata plus diagnostics.

src/agents/
  Shared provider command building, credentials prompt blocks, process logging,
  terminal status events, and redaction.

src/browser/
  Browser session profile resolution and session instructions for MCP reuse.

src/diagnostics/
  Plain browser diagnostics for page snapshots.

src/config/general.py
  Environment-backed defaults for output paths, run paths, sessions, and agent provider.
```

## Discovery Contract

The agent receives:

- source URL,
- user scrape goal,
- requested output format,
- exact output file path,
- run artifact directory,
- diagnostics directory,
- optional credentials,
- optional browser session paths.

The agent must:

- use Playwright MCP/browser MCP to inspect and interact with the page,
- scrape the requested data during that same agent run,
- write the final output file,
- avoid creating scraper source files or reusable scripts,
- save optional diagnostics only inside the diagnostics directory.

## Artifacts

Discovery runs are stored under `output/discovery-runs/<timestamp>/` by default.

The output file is controlled separately with `--output`, defaulting to `output/discovery.json`.

Per-scrape diagnostics are stored under:

```text
diagnostics/<timestamp>-<prompt-slug>-<source-slug>/
```

The host writes:

- `metrics.json` with prepare, agent, validation, and total timings;
- `summary.md`;
- redacted prompt and request files;
- the selected agent log;
- a copy of JSON output when validation succeeds.

## Sessions

The Python host creates session folders and records usage, but it does not launch the global Playwright MCP server. When a browser MCP server needs an authenticated profile, configure it with the paths written to `sessions/<profile>/session.md`.
