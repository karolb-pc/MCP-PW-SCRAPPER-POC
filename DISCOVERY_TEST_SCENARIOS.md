# Direct Discovery Test Scenarios

This file focuses on discovery behavior after removing generated scraper code.

Default commands use `--openai` so the baseline matches Codex runs. To run the same scenario with Claude, replace `--openai` with `--claude`.

## Rule

Every test must preserve this invariant:

```text
The agent scrapes data directly and writes the final output. It must not create scraper source code.
```

## Required Files Per Run

Given:

```bash
uv run python main.py discover --openai \
  --url "<url>" \
  --prompt-file "<prompt-file>" \
  --output "output/<name>.json" \
  --diagnostics-dir diagnostics
```

Expected diagnostics:

```text
diagnostics/<timestamp>-<provider>-<prompt-slug>-<source-slug>/
  request.json
  user_prompt.md
  scrape_prompt.md
  <provider>_direct_discovery.log
  scrape_summary.md
  metrics.json
  summary.md
  output.json
```

`metrics.json` is host-generated. It measures the whole agent process, not the agent's internal scrape/processing split.

## Amazon Prompt Matrix

Use these prompt files:

```text
instructions/amazon/amazon-com-search-macbooks.md
instructions/amazon/amazon-com-search-macbooks-csv.md
instructions/amazon/amazon-com-bestsellers.md
instructions/amazon/amazon-com-bestsellers-csv.md
instructions/amazon/amazon-com-product-detail.md
instructions/amazon/amazon-com-offers.md
instructions/amazon/amazon-com-reviews.md
instructions/amazon/amazon-com-prime-availability.md
instructions/amazon/amazon-com-home-to-macbooks.md
instructions/amazon/amazon-com-home-to-bestsellers.md
instructions/amazon/amazon-com-complex-product-research.md
instructions/amazon/amazon-com-complex-budget-filtered-research.md
```

For each prompt:

1. Run with `--diagnostics-dir diagnostics`.
2. For JSON outputs, validate with `uv run python main.py validate <output>`.
3. For CSV outputs, inspect the CSV header and `metrics.json -> items_count`.
4. Inspect `metrics.json`.
5. Confirm no files were created under `src/`, `scrapers/`, or any generated code folder.

## Ready-To-Run Amazon Commands

### Search MacBooks

Prompt: `instructions/amazon/amazon-com-search-macbooks.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks.md \
  --output output/amazon-com-macbooks.json \
  --diagnostics-dir diagnostics
```

### Search MacBooks CSV

Prompt: `instructions/amazon/amazon-com-search-macbooks-csv.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks-csv.md \
  --output output/amazon-com-macbooks.csv \
  --output-format csv \
  --diagnostics-dir diagnostics
```

### Bestsellers

Prompt: `instructions/amazon/amazon-com-bestsellers.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/gp/bestsellers/" \
  --prompt-file instructions/amazon/amazon-com-bestsellers.md \
  --output output/amazon-com-bestsellers.json \
  --diagnostics-dir diagnostics
```

### Bestsellers CSV

Prompt: `instructions/amazon/amazon-com-bestsellers-csv.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/gp/bestsellers/" \
  --prompt-file instructions/amazon/amazon-com-bestsellers-csv.md \
  --output output/amazon-com-bestsellers.csv \
  --output-format csv \
  --diagnostics-dir diagnostics
```

### Product Detail

Prompt: `instructions/amazon/amazon-com-product-detail.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/Apple-2025-MacBook-13-inch-Laptop/dp/B0DZDC3WW5" \
  --prompt-file instructions/amazon/amazon-com-product-detail.md \
  --output output/amazon-com-product-detail.json \
  --diagnostics-dir diagnostics
```

### Product Offers

Prompt: `instructions/amazon/amazon-com-offers.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/Apple-2025-MacBook-13-inch-Laptop/dp/B0DZDC3WW5" \
  --prompt-file instructions/amazon/amazon-com-offers.md \
  --output output/amazon-com-offers.json \
  --diagnostics-dir diagnostics
```

### Product Reviews

Prompt: `instructions/amazon/amazon-com-reviews.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/product-reviews/B0DZDC3WW5/" \
  --prompt-file instructions/amazon/amazon-com-reviews.md \
  --output output/amazon-com-reviews.json \
  --diagnostics-dir diagnostics
```

### Prime And Availability

Prompt: `instructions/amazon/amazon-com-prime-availability.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-prime-availability.md \
  --output output/amazon-com-prime-availability.json \
  --diagnostics-dir diagnostics
```

### Homepage To MacBooks

Prompt: `instructions/amazon/amazon-com-home-to-macbooks.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-home-to-macbooks.md \
  --output output/amazon-com-macbooks-home-navigation.json \
  --diagnostics-dir diagnostics
```

### Homepage To Bestsellers

Prompt: `instructions/amazon/amazon-com-home-to-bestsellers.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-home-to-bestsellers.md \
  --output output/amazon-com-bestsellers-home-navigation.json \
  --diagnostics-dir diagnostics
```

### Complex Product Research

Prompt: `instructions/amazon/amazon-com-complex-product-research.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-complex-product-research.md \
  --output output/amazon-com-complex-product-research.json \
  --diagnostics-dir diagnostics
```

### Complex Budget Filtered Research

Prompt: `instructions/amazon/amazon-com-complex-budget-filtered-research.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-complex-budget-filtered-research.md \
  --output output/amazon-com-complex-budget-filtered-research.json \
  --diagnostics-dir diagnostics
```

## Amazon Deep Link vs Homepage Navigation

Run comparable A/B pairs to measure the cost of asking the agent to navigate from the Amazon.com homepage.

MacBook pair:

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks.md \
  --output output/amazon-com-macbooks-deeplink.json \
  --diagnostics-dir diagnostics

uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-home-to-macbooks.md \
  --output output/amazon-com-macbooks-home-navigation.json \
  --diagnostics-dir diagnostics
```

Bestsellers pair:

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/gp/bestsellers/" \
  --prompt-file instructions/amazon/amazon-com-bestsellers.md \
  --output output/amazon-com-bestsellers-deeplink.json \
  --diagnostics-dir diagnostics

uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-home-to-bestsellers.md \
  --output output/amazon-com-bestsellers-home-navigation.json \
  --diagnostics-dir diagnostics
```

Compare:

- `metrics.json -> agent_elapsed_seconds`;
- `metrics.json -> timings_seconds.agent_scrape`;
- `metrics.json -> timings_seconds.total`;
- number of items and blocker status.

## Product Offers From Product Page

Use this for `instructions/amazon/amazon-com-offers.md`. This prompt expects a concrete Amazon.com product detail URL, not the homepage.

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/Apple-2025-MacBook-13-inch-Laptop/dp/B0DZDC3WW5" \
  --prompt-file instructions/amazon/amazon-com-offers.md \
  --output output/amazon-com-offers.json \
  --diagnostics-dir diagnostics
```

Expected:

- agent opens the product detail page;
- agent looks for visible offer/seller information or normal other-sellers entry points;
- output contains seller/offer rows when available;
- if no offer list is exposed, output uses `meta.status: "partial"` and explains what was visible.

## Complex Amazon Navigation

Use this when you want to test whether the agent can handle multi-step navigation, scrolling, product-page drilling, and detail extraction.

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-complex-product-research.md \
  --output output/amazon-com-complex-product-research.json \
  --diagnostics-dir diagnostics
```

Expected:

- agent searches from homepage;
- agent scrolls the results page;
- agent opens up to 5 product detail pages;
- output includes `items`, `comparison_summary`, and `meta.results_inspected_count`;
- if blocked or partially successful, output explains the blocker/partial status.

## Complex Amazon Budget Filter

Use this when you want to test whether the agent can apply selection criteria before opening product pages.

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-complex-budget-filtered-research.md \
  --output output/amazon-com-complex-budget-filtered-research.json \
  --diagnostics-dir diagnostics
```

Expected:

- agent starts from homepage;
- agent searches for `wireless noise cancelling headphones`;
- agent inspects up to 40 visible result tiles;
- agent filters products by USD 50-150, rating, review count, Prime/fast delivery, sponsorship, and relevance;
- agent opens up to 5 qualifying product pages;
- output includes `items`, `rejected_examples`, `decision_summary`, and bounded counts in `meta`.

## Blocker Handling

Amazon may show CAPTCHA, bot checks, consent screens, or locale prompts.

Expected behavior:

- do not bypass CAPTCHA or anti-bot controls;
- write final JSON with `items: []` and `meta.status: "blocked"` or equivalent;
- include a clear blocker explanation in the output payload;
- preserve optional screenshots or notes in diagnostics if useful and available through MCP.

## CSV Output Scenarios

Use these when you want to verify non-JSON output handling. The host copies CSV outputs into diagnostics as `output.csv` and counts data rows for `metrics.json`.

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks-csv.md \
  --output output/amazon-com-macbooks.csv \
  --output-format csv \
  --diagnostics-dir diagnostics

uv run python main.py discover --openai \
  --url "https://www.amazon.com/gp/bestsellers/" \
  --prompt-file instructions/amazon/amazon-com-bestsellers-csv.md \
  --output output/amazon-com-bestsellers.csv \
  --output-format csv \
  --diagnostics-dir diagnostics
```

## Analytics Acceptance Criteria

Host-level analytics are acceptable when `metrics.json` contains:

- total elapsed time;
- prepare time;
- agent process time;
- output validation time;
- longest host phase;
- item count if JSON has `items`;
- output path;
- diagnostics path.
