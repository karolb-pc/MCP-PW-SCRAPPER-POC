# Amazon Direct Discovery Prompts

These prompt files are designed for the direct agent flow. Use them with `--prompt-file`.

Default commands use `--openai` for the Codex baseline. To run the same prompt through Claude, replace `--openai` with `--claude`.

Example:

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks.md \
  --output output/amazon-com-macbooks.json \
  --diagnostics-dir diagnostics
```

Deep-link prompts start directly on the target page, for example search results or bestsellers.
Homepage-navigation prompts start from `https://www.amazon.com/` and ask the agent to click/search its way to the same destination. Use both variants when comparing how much extra time the agent spends on navigation.

The `amazon-com-complex-product-research.md` prompt is a heavier navigation test: homepage search, scrolling result listings, opening product detail pages, reading specifications, and producing a comparison JSON.

The `amazon-com-complex-budget-filtered-research.md` prompt adds decision criteria: search from homepage, inspect visible results, filter by USD price range, rating, review count, delivery/Prime signal, sponsorship, and relevance, then open selected products.

## Command Cookbook

### `amazon-com-search-macbooks.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks.md \
  --output output/amazon-com-macbooks.json \
  --diagnostics-dir diagnostics
```

### `amazon-com-search-macbooks-csv.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-search-macbooks-csv.md \
  --output output/amazon-com-macbooks.csv \
  --output-format csv \
  --diagnostics-dir diagnostics
```

### `amazon-com-bestsellers.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/gp/bestsellers/" \
  --prompt-file instructions/amazon/amazon-com-bestsellers.md \
  --output output/amazon-com-bestsellers.json \
  --diagnostics-dir diagnostics
```

### `amazon-com-bestsellers-csv.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/gp/bestsellers/" \
  --prompt-file instructions/amazon/amazon-com-bestsellers-csv.md \
  --output output/amazon-com-bestsellers.csv \
  --output-format csv \
  --diagnostics-dir diagnostics
```

### `amazon-com-product-detail.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/Apple-2025-MacBook-13-inch-Laptop/dp/B0DZDC3WW5" \
  --prompt-file instructions/amazon/amazon-com-product-detail.md \
  --output output/amazon-com-product-detail.json \
  --diagnostics-dir diagnostics
```

### `amazon-com-offers.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/Apple-2025-MacBook-13-inch-Laptop/dp/B0DZDC3WW5" \
  --prompt-file instructions/amazon/amazon-com-offers.md \
  --output output/amazon-com-offers.json \
  --diagnostics-dir diagnostics
```

### `amazon-com-reviews.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/product-reviews/B0DZDC3WW5/" \
  --prompt-file instructions/amazon/amazon-com-reviews.md \
  --output output/amazon-com-reviews.json \
  --diagnostics-dir diagnostics
```

### `amazon-com-prime-availability.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/s?k=macbook" \
  --prompt-file instructions/amazon/amazon-com-prime-availability.md \
  --output output/amazon-com-prime-availability.json \
  --diagnostics-dir diagnostics
```

### `amazon-com-home-to-macbooks.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-home-to-macbooks.md \
  --output output/amazon-com-macbooks-home-navigation.json \
  --diagnostics-dir diagnostics
```

### `amazon-com-home-to-bestsellers.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-home-to-bestsellers.md \
  --output output/amazon-com-bestsellers-home-navigation.json \
  --diagnostics-dir diagnostics
```

### `amazon-com-complex-product-research.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-complex-product-research.md \
  --output output/amazon-com-complex-product-research.json \
  --diagnostics-dir diagnostics
```

### `amazon-com-complex-budget-filtered-research.md`

```bash
uv run python main.py discover --openai \
  --url "https://www.amazon.com/" \
  --prompt-file instructions/amazon/amazon-com-complex-budget-filtered-research.md \
  --output output/amazon-com-complex-budget-filtered-research.json \
  --diagnostics-dir diagnostics
```

Important:

- Use only pages you are allowed to access.
- Do not bypass CAPTCHA, bot challenges, or access controls.
- If blocked, write a structured blocker report with `items: []`.
- Optional notes or screenshots may be saved in the diagnostics directory requested by the host prompt.
