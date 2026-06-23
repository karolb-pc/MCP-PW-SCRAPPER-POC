# MCP-PW-SCRAPPER

## PL: Co to jest?

POC scrapera przebudowany na architekture ETL zgodna stylem z `db-to-bigquery-etl` i `tiktok/tiktok-shop-etl`:

```text
main.py -> src/etl/books.py -> extractor -> transformer -> validator -> loader
```

Pipeline:

```text
scrape -> transform -> validate -> export/load
```

Tryb samonaprawiania:

```text
FAIL -> diagnostics -> mock email -> codex exec -> Playwright MCP -> patch -> retry
```

`scraper.py` zostal jako kompatybilny wrapper. Preferowany entrypoint to `main.py`.

## PL: Jak odpalic?

```bash
cd /Users/karol/Desktop/PC/projects/MCP-PW-SCRAPPER
uv run python main.py run --quiet --auto-repair
```

To zrobi:

1. scrape strony `https://books.toscrape.com/`,
2. transformacje danych do JSON,
3. walidacje kontraktu,
4. zapis do `output/books.json`,
5. eksport do `data/successful/latest.json` i pliku timestampowanego,
6. jesli failnie: zapis diagnostics, mock mail, Codex repair, retry maksymalnie 5 razy.

Stara komenda dalej dziala:

```bash
uv run python scraper.py run --quiet --auto-repair
```

## PL: Struktura

```text
main.py
  Click CLI, cienki entrypoint jak w innych ETL-ach.

scraper.py
  Wrapper kompatybilnosci, deleguje do main.py.

src/config/
  Ustawienia i domyslne sciezki.

src/etl/base.py
  BaseETL budujacy extractor/transformer/validator/loader z CONFIG.

src/etl/books.py
  BooksToScrapeETL oraz CONFIG.

src/etl/extractor/books.py
  Camoufox/Playwright scraping.

src/etl/transformer/books.py
  Raw scraped records -> kontrakt JSON.

src/etl/validator/books.py
  Walidacja kontraktu.

src/etl/loader/local_json.py
  Lokalny output/export JSON.

src/etl/runner.py
  Auto-repair, retry i powiadomienia po awarii.

src/diagnostics/
  HTML, screenshot, error.json, error.log, partial.json, repair_prompt.md.

src/notification/
  Mock email outbox.

src/repair/
  Codex repair agent uruchamiany przez codex exec.
```

## PL: Komendy

Pelny run:

```bash
uv run python main.py run
```

Run cichy:

```bash
uv run python main.py run --quiet
```

Run z samonaprawianiem:

```bash
uv run python main.py run --quiet --auto-repair
```

Wymuszenie Playwright:

```bash
uv run python main.py run --quiet --browser playwright
```

Walidacja outputu:

```bash
uv run python main.py validate output/books.json
```

Diagnostyka strony:

```bash
uv run python main.py diagnose --diagnostics-dir diagnostics/manual-check
```

## PL: Auto-repair

Domyslnie:

```text
repair-attempts = 5
repair-timeout = 900 sekund
notify-email = scraper-ops@example.local
notifications-dir = notifications/mock-email-outbox
```

Po awarii:

1. `diagnostics/latest/error.json` i inne artefakty sa zapisywane,
2. mock mail `Scraper run failed` trafia do outboxu,
3. `codex exec` dostaje prompt z `diagnostics/latest/repair_prompt.md`,
4. Codex moze uzyc Playwright MCP i poprawic kod w `src/etl/`,
5. pipeline robi retry,
6. po sukcesie idzie mock mail `Scraper recovered after repair`,
7. po 5 nieudanych probach idzie mock mail `manual intervention required`.

Dodanie Playwright MCP:

```bash
codex mcp add playwright -- npx -y @playwright/mcp@latest --headless
```

## PL: Mockowanie awarii

Szybki test `error.json` i maili bez odpalania Codexa:

```bash
uv run python main.py run --quiet --auto-repair \
  --repair-attempts 0 \
  --browser playwright \
  --simulate-failure transform \
  --diagnostics-dir diagnostics/mock-transform \
  --notifications-dir notifications/mock-transform-outbox
```

Dostepne mocki:

```text
--simulate-failure selector
--simulate-failure transform
--simulate-failure validation
--simulate-failure export
```

Artefakty:

```text
diagnostics/mock-*/error.json
diagnostics/mock-*/partial.json
diagnostics/mock-*/repair_prompt.md
notifications/mock-*-outbox/*.txt
```

Uwaga: `--simulate-failure` z realnym `--repair-attempts 5` wymusza awarie w kazdym retry. To testuje petle powiadomien, nie skuteczna naprawe.

---

# EN: What Is This?

A scraper POC refactored into an ETL architecture matching the style of `db-to-bigquery-etl` and `tiktok/tiktok-shop-etl`:

```text
main.py -> src/etl/books.py -> extractor -> transformer -> validator -> loader
```

Pipeline:

```text
scrape -> transform -> validate -> export/load
```

Self-repair mode:

```text
FAIL -> diagnostics -> mock email -> codex exec -> Playwright MCP -> patch -> retry
```

`scraper.py` remains as a compatibility wrapper. Prefer `main.py`.

## EN: Run It

```bash
cd /Users/karol/Desktop/PC/projects/MCP-PW-SCRAPPER
uv run python main.py run --quiet --auto-repair
```

This:

1. scrapes `https://books.toscrape.com/`,
2. transforms data to JSON,
3. validates the contract,
4. writes `output/books.json`,
5. exports to `data/successful/latest.json` and a timestamped file,
6. on failure: writes diagnostics, sends mock email, runs Codex repair, retries up to 5 times.

Old command still works:

```bash
uv run python scraper.py run --quiet --auto-repair
```

## EN: Commands

Full run:

```bash
uv run python main.py run
```

Quiet run:

```bash
uv run python main.py run --quiet
```

Self-repair run:

```bash
uv run python main.py run --quiet --auto-repair
```

Force Playwright:

```bash
uv run python main.py run --quiet --browser playwright
```

Validate output:

```bash
uv run python main.py validate output/books.json
```

Manual diagnostics:

```bash
uv run python main.py diagnose --diagnostics-dir diagnostics/manual-check
```

## EN: Auto-Repair

Defaults:

```text
repair-attempts = 5
repair-timeout = 900 seconds
notify-email = scraper-ops@example.local
notifications-dir = notifications/mock-email-outbox
```

On failure:

1. `diagnostics/latest/error.json` and other artifacts are written,
2. a mock `Scraper run failed` email goes to the outbox,
3. `codex exec` receives `diagnostics/latest/repair_prompt.md`,
4. Codex can use Playwright MCP and patch code under `src/etl/`,
5. the pipeline retries,
6. on recovery, a mock `Scraper recovered after repair` email is written,
7. after 5 failed repair attempts, a mock `manual intervention required` email is written.

Add Playwright MCP:

```bash
codex mcp add playwright -- npx -y @playwright/mcp@latest --headless
```

## EN: Mock Failures

Quick test for `error.json` and mock emails without starting Codex:

```bash
uv run python main.py run --quiet --auto-repair \
  --repair-attempts 0 \
  --browser playwright \
  --simulate-failure transform \
  --diagnostics-dir diagnostics/mock-transform \
  --notifications-dir notifications/mock-transform-outbox
```

Available mocks:

```text
--simulate-failure selector
--simulate-failure transform
--simulate-failure validation
--simulate-failure export
```

Artifacts:

```text
diagnostics/mock-*/error.json
diagnostics/mock-*/partial.json
diagnostics/mock-*/repair_prompt.md
notifications/mock-*-outbox/*.txt
```
