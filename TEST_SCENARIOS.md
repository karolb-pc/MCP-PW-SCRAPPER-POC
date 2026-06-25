# Test Scenarios

These scenarios cover the `poc-simplest` flow:

```text
URL + prompt file -> direct agent -> Playwright MCP/browser MCP -> output file + diagnostics folder
```

Default discovery commands use `--openai`. To compare Claude, replace `--openai` with `--claude`.

No scenario should create scraper source code.

## 1. CLI Help

```bash
uv run python main.py --help
uv run python main.py discover --help
```

Expected:

- available commands are `discover`, `validate`, and `diagnose`;
- discovery options include `--url`, `--prompt`, `--prompt-file`, `--output`, `--output-format`, `--diagnostics-dir`, and `--session-profile`.

## 2. Host Orchestration Smoke Test

This does not call a real LLM agent. It checks that the host creates diagnostics, runs a command, validates JSON, and reports paths.

```bash
uv run python main.py discover --openai \
  --url "https://example.com" \
  --prompt "Return an empty items list for orchestration smoke test." \
  --output /private/tmp/poc-simplest-output.json \
  --runs-dir /private/tmp/poc-simplest-runs \
  --diagnostics-dir /private/tmp/poc-simplest-diagnostics \
  --scrape-command "python -c \"from pathlib import Path; Path('/private/tmp/poc-simplest-output.json').write_text('{\\\"source_url\\\": \\\"https://example.com\\\", \\\"items\\\": []}\\n')\""
```

Expected:

- command returns `status: ok`;
- output JSON exists;
- diagnostics folder exists with `request.json`, `scrape_prompt.md`, `metrics.json`, `summary.md`, and the agent log;
- `metrics.json` includes `timings_seconds.total`, `timings_seconds.agent_scrape`, `timings_seconds.validate_output`, `agent_elapsed_seconds`, and `longest_host_phase`.

## 3. JSON Validation

```bash
uv run python main.py validate /private/tmp/poc-simplest-output.json
```

Expected:

- `status: ok`;
- `items` equals the number of records.

## 4. Public Page Direct Discovery

```bash
uv run python main.py discover --openai \
  --url "https://books.toscrape.com/" \
  --prompt "Scrape the first page of books with title, price, availability, rating, and absolute URL." \
  --output output/books-direct.json \
  --diagnostics-dir diagnostics
```

Expected:

- agent uses Playwright MCP/browser MCP;
- output contains `items`;
- diagnostics include host timings, prompt, agent log, summary, and output copy.

## 5. Amazon Prompt File Discovery

Full ready-to-run commands for every prompt in `instructions/amazon/` are listed in:

- `DISCOVERY_TEST_SCENARIOS.md`
- `instructions/amazon/README.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks.md \
  --output output/amazon-com-macbooks.json \
  --diagnostics-dir diagnostics
```

Expected:

- output schema follows the prompt file;
- diagnostics folder name includes a timestamp, prompt slug, and `amazon`;
- if Amazon blocks with CAPTCHA or bot challenge, output contains a structured blocker report instead of bypass attempts.

## 6. Amazon Homepage Navigation Comparison

Run the same MacBook scrape two ways: first from the search-results deep link, then from the Amazon.com homepage where the agent must use the search UI.

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

Expected:

- both runs produce the same general schema;
- homepage-navigation should usually take longer because the agent must open the homepage, handle visible consent if needed, use search, and wait for results;
- compare `metrics.json -> agent_elapsed_seconds` and `metrics.json -> timings_seconds.agent_scrape`.

## 7. Amazon CSV Output

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks-csv.md \
  --output output/amazon-com-macbooks.csv \
  --output-format csv \
  --diagnostics-dir diagnostics
```

Expected:

- final output is CSV, not JSON;
- diagnostics copy is saved as `output.csv`;
- `metrics.json -> items_count` counts CSV data rows.

## 8. Amazon Product Offers From Product Page

Use this for `instructions/amazon/amazon-com-offers.md`. This prompt expects a concrete Amazon.com product detail URL.

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/Apple-2025-MacBook-13-inch-Laptop/dp/B0DZDC3WW5" \
  --prompt-file instructions/amazon/amazon-com-offers.md \
  --output output/amazon-com-offers.json \
  --diagnostics-dir diagnostics
```

Expected:

- agent opens the product detail page;
- agent looks for seller/offer information or normal other-sellers entry points;
- output contains seller/offer rows when available;
- if no offer list is exposed, output uses `meta.status: "partial"` and explains what was visible.

## 9. Amazon Complex Navigation

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-complex-product-research.md \
  --output output/amazon-com-complex-product-research.json \
  --diagnostics-dir diagnostics
```

Expected:

- agent starts from homepage;
- agent searches for `27 inch 4k monitor`;
- agent scrolls the result list;
- agent opens up to 5 product pages and extracts details/specifications;
- output contains `items`, `comparison_summary`, and bounded counts in `meta`.

## 10. Amazon Complex Budget Filter

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
- agent inspects up to 40 result tiles;
- agent filters by USD 50-150, rating, review count, delivery/Prime signal, sponsorship, and relevance;
- agent opens up to 5 qualifying product pages;
- output contains `items`, `rejected_examples`, `decision_summary`, and bounded counts in `meta`.

## 11. Amazon Session Profile

Use this only with your own account/session and only when the target page genuinely needs state.

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/gp/bestsellers/" \
  --prompt-file instructions/amazon/amazon-com-bestsellers.md \
  --output output/amazon-com-bestsellers.json \
  --diagnostics-dir diagnostics \
  --session-profile amazon-private
```

Expected:

- `sessions/amazon-private/usage.jsonl` gets a new entry;
- diagnostics `request.json` includes the selected session paths;
- agent prompt tells Playwright MCP/browser MCP to reuse the selected session.

## 12. Diagnostics Quality Check

For any successful or blocked scrape, inspect:

```bash
ls diagnostics/<timestamp-provider-prompt-amazon>/
cat diagnostics/<timestamp-provider-prompt-amazon>/metrics.json
cat diagnostics/<timestamp-provider-prompt-amazon>/summary.md
```

Expected:

- `metrics.json` contains host-level timing data;
- `summary.md` gives a short human-readable status;
- if blocked, final output explains the blocker.

## 13. Diagnose Command

```bash
uv run python main.py diagnose \
  --url "https://www.amazon.com/" \
  --diagnostics-dir diagnostics/amazon-home-diagnose
```

Expected:

- page artifacts are saved under the selected diagnostics directory;
- command does not invoke an LLM agent.

## 14. Compile Check

```bash
uv run python -m compileall main.py src
```

Expected:

- all active Python modules compile.
