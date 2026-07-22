# Spec: `generate-self-healing` mode

Branch: `poc-self-healing` (forked from `poc-simplest`).
Status: **draft for confirmation** — agree first, then implement.

> This document is also the **canonical ETL infrastructure contract** that the code-generating
> agent MUST read and follow on **every** `generate-self-healing` run (see §5). The generated
> scraper is not free-form: it must match the layout, contracts, and rules described here so that
> every generated scraper looks and behaves like every other ETL in `/PC/projects`.

---

## 1. Goal of this iteration

We want a new scraper mode that fuses two worlds:

- **From `poc-simplest`** — the working style of the `discover-code` mode
  (`GeneratedCodeScrapeDiscovery`): the agent first inspects the live page through Playwright MCP
  and then **writes the scraper code itself**; plus this branch's rich CLI
  (`--prompt-file`, `--claude`/`--openai`, `--output-format`, `--session-profile`,
  `--scrape-command`, `--scrape-timeout`, `--use-credentials`).
- **From `main`** — **persistent, maintainable scraper code** written to disk (not deleted after
  the run) and the **self-healing system** (auto-repair, audit, semi-discover, break).

Key difference vs today's `discover-code`: the generated code is **persisted**. Today
`poc-simplest` deletes `generated-code-workspace` after the run (see
[auto_scraper.py](src/discovery/auto_scraper.py), `_cleanup_generated_code_dir`).

End state: the user runs one command (`generate-self-healing`) that **generates a self-healing
scraper of its own** — a complete, persistent ETL scraper project — using the advanced flags from
this branch (where to read the prompt from, Claude vs OpenAI, etc.).

### 1.1 Confirmed decisions (from review)

- **D1 — project structure: FULL ETL.** Not a flat throwaway script. The generated scraper must
  follow the canonical ETL infrastructure in §4/§5. This structure was **verified as global**
  across `/PC/projects`: the same shape recurs in `db-to-bigquery-etl`, `openai-etl`,
  `datarova-etl`, `google-sheet-etl`, `airflow-analytics-etl`, `airflow-gdrive-etl`,
  `google-mail-etl`, `power-bi-etl`, `quickbooks`, `tiktok`, and the `main` branch's
  `scrapers/books/`. §4 is the authoritative, agent-facing description of it.
- **D2 — the AI writes the code.** The generating agent (Claude/OpenAI) authors every file,
  including the `scraper_target.json` manifest — not the host, not a human. The host only scaffolds
  directories, injects this spec into the prompt, and verifies the result.
- **D3 — command name:** `generate-self-healing` (kept as the user named it).
- **D4 — no `uv` alias:** stay with `uv run python main.py generate-self-healing ...`.
  `pyproject.toml` keeps `package = false`; no `[project.scripts]`.
- **D5 — self-healing produces a DIFF.** After a repair, do **not** keep the old code around as a
  parallel copy; instead emit a generated **diff of exactly what changed** (unified diff artifact)
  into diagnostics, so every heal is auditable.
- **D6 — repair provider:** selectable per command via `--claude`/`--openai` (defaults to the same
  provider resolution as generation).

---

## 2. Current state of both branches

### 2.1 `poc-simplest` (base branch)

Intentionally small. The host does **not** persist scraper code and does **not** run stored
projects. Commands in [main.py](main.py): `discover` (direct), `discover-code`
(generated-code, disposable + cleanup), `validate`, `diagnose`. Classes in
[auto_scraper.py](src/discovery/auto_scraper.py): `AutomatedScrapeDiscovery`,
`GeneratedCodeScrapeDiscovery`. Advanced flags we keep: `--prompt-file`, `--prompt`,
`--output-format`, `--claude`/`--openai`, `--scrape-command`, `--scrape-timeout`,
`--session-profile`, `--sessions-dir`, `--use-credentials`.

### 2.2 `main` (self-healing prototype)

Full persistent-scraper + self-healing architecture:

- [main.py](main.py) — commands: `discover`, `run`, `repair`, `audit`, `semi-discover`, `break`,
  `validate`, `diagnose` (plus "source-first argv": `main.py <path> run`).
- `src/discovery/runtime.py` — `run_generated_discovery_scraper`: loads generated modules and runs
  E→T→L.
- `src/scraper_target.py` — `ScraperTarget` + `resolve_scraper_target`; two target kinds:
  `discovery_run` (folder with `request.json` + `generated/`) and `manifest`/`folder_etl`
  (folder with `scraper_target.json`).
- `src/repair/target_repair.py` — `TargetAutoRepairRunner`: "run → on error build
  `repair_prompt.md`, invoke repair agent, patch only `allowed_paths`, retry" up to
  `repair_attempts`.
- `src/agents/repair.py` — `ClaudeRepairAgent` / `CodexRepairAgent`.
- `src/audit/source_auditor.py`, `src/semi_discovery/extender.py`, `src/breaker/demo_breaker.py`.
- `src/contracts/` — ETL contracts (`base.py`, `extractor.py`, `transformer.py`, `loader.py`,
  `local_json.py`).
- `scrapers/books/` — reference persistent ETL scraper (the template to imitate).

---

## 3. Target mode: `generate-self-healing`

### 3.1 Idea

The new command generates a **persistent, self-healing ETL scraper project**. Flow:

1. The agent (Claude or OpenAI, flag-selected) inspects the live page via Playwright MCP
   (as in `discover-code`).
2. The agent writes a **persistent** full-ETL scraper to disk following §4/§5 — separate
   `extractor` / `transformer` / `validator` / `loader` layers driven by a `CONFIG` dict and a
   `BaseETL` subclass, **not** a one-off script.
3. The agent also writes the `scraper_target.json` manifest describing the target.
4. The result is immediately runnable (`run`) and repairable (`repair` / `run --auto-repair`).

In short: `discover-code` + "don't delete the code" + "emit a full ETL project + manifest" +
"restore the self-healing commands", wired through `poc-simplest`'s CLI flags.

### 3.2 CLI command and flags (proposal)

```bash
uv run python main.py generate-self-healing --claude \
  --url "https://www.amazon.com/gp/bestsellers/" \
  --prompt-file instructions/amazon/amazon-com-bestsellers.md \
  --output-format json \
  --output output/scrapers/amazon-bestsellers/output.json \
  --target-dir scrapers/amazon_bestsellers
```

| Flag | Meaning | Origin |
|---|---|---|
| `--url` | page to inspect / scrape | both |
| `--prompt` / `--prompt-file` | scrape goal (inline or from file) | `poc-simplest` |
| `--claude` / `--openai` | agent provider | both |
| `--output-format` | e.g. `json`, `csv` | `poc-simplest` |
| `--output` | final output file path | both |
| `--target-dir` | where to persist the generated scraper project | **new** |
| `--scrape-command` | custom LLM command | both |
| `--scrape-timeout` | generating-agent timeout | both |
| `--session-profile` / `--sessions-dir` | browser session profile | `poc-simplest` |
| `--use-credentials` | LOGIN/PASSWORD from env | both |

Invocation stays `uv run python main.py generate-self-healing ...` (D4).

### 3.3 Restored self-healing commands (from `main`, with `poc-simplest` flags)

- `run --path <scraper_dir>` — run the persistent scraper (E→T→[V]→L), write to `--output`.
- `run --path ... --auto-repair` **or** `repair --path ...` — self-healing loop
  (`TargetAutoRepairRunner`): on failure build `repair_prompt.md`, invoke the repair agent
  (Claude/OpenAI), patch only `allowed_paths`, retry up to `--repair-attempts`, and **emit a diff
  of what changed** (D5).
- `audit --path ...` [`--fix`] — source-drift audit.
- `semi-discover --path ...` — add new fields to an existing scraper.
- `break --path ...` — intentionally break a scraper to demo self-healing.

All accept `--claude`/`--openai`, `--use-credentials`, `--*-timeout`, `--*-command`.

---

## 4. Canonical ETL infrastructure (the global structure)

This is the structure **every** generated scraper must produce. It is the same shape verified
across `/PC/projects` ETLs. The invariant (the "global ETL structure") is:

- **layer separation** — `extractor/` + `transformer/` + `loader/`, each layer with its own
  concrete class implementing a shared abstract contract;
- **config-driven wiring** — a module-level `CONFIG` dict `{"extractor": {"_class": X,
  "params": {...}}, ...}` consumed by a `BaseETL(config)` whose `__build_instance` factory
  instantiates each component;
- **a concrete `<Name>ETL(BaseETL)`** overriding `extract` / `transform` / `load` (+ `validate`)
  and exposing `run(...)` = extract → transform → validate → load;
- **data contracts as Pydantic models** (the sibling ETLs keep these in `src/schema/`);
- **a `main.py` Click entrypoint** (`@click.group` + commands), pydantic-settings config, `loguru`.

Reference implementation to imitate: `main` branch `scrapers/books/` + `src/contracts/`.

**Scraper-sink adaptation (important):** the sibling ETLs sink to Postgres/BigQuery, so their
loaders are `SqlLoader`/`BigQueryLoader` over a SQLAlchemy `src/orm/` model. Our scrapers sink to a
**local JSON file**, so: the loader is `LocalJsonLoader` (no `src/orm/`, no DB), and the Pydantic
data contracts describe the scraped item/payload shape used by the transformer + validator. Every
other part of the global contract (layers, `CONFIG`, `BaseETL`, `<Name>ETL.run`, Click `main.py`)
is kept exactly.

### 4.1 Directory layout of a generated scraper

```text
scrapers/<slug>/
  scraper_target.json          # manifest (written by the AGENT)
  __init__.py
  main.py                      # Click `cli` with `run` and `validate` commands
  etl.py                       # CONFIG dict + <Name>ETL(BaseETL) with run()
  settings.py                  # SOURCE_URL, SOURCE_NAME, default paths
  extractor/
    __init__.py
    <slug>.py                  # <Name>Extractor(AbstractExtractor).extract(...)
  transformer/
    __init__.py
    <slug>.py                  # <Name>Transformer(AbstractTransformer).transform(...)
  validator/
    __init__.py
    <slug>.py                  # <Name>Validator.validate(payload)  (guards output)
  schema/
    __init__.py
    <slug>.py                  # Pydantic item/payload models (global convention: src/schema/)
  diagnostics/                 # logs, screenshots, repair_prompt.md, repair diffs, metrics
```

`schema/` holds the Pydantic data contracts (equivalent to the sibling ETLs' `src/schema/`); the
validator uses them to reject empty/degenerate payloads. There is no `orm/` layer because the sink
is a JSON file, not a database.

`<slug>` derived from prompt/URL (same rule as `_diagnostics_folder_name` in
[auto_scraper.py](src/discovery/auto_scraper.py)); Python-safe module name (underscores).

### 4.2 Shared contracts (live in `src/contracts/`, imported by generated code)

The host provides these base classes; generated code subclasses them and never redefines them:

```python
# src/contracts/base.py — config-driven builder (from main)
class BaseETL:
    def __init__(self, config: dict): ...   # builds extractor/transformer/validator/loader
    def extract(...):  raise NotImplementedError
    def transform(...): raise NotImplementedError
    def validate(...): raise NotImplementedError
    def load(...):     raise NotImplementedError

# src/contracts/extractor.py
class AbstractExtractor(ABC):
    @abstractmethod
    async def extract(self, *args, **kwargs): ...

# src/contracts/transformer.py
class AbstractTransformer(ABC):
    @abstractmethod
    def transform(self, *args, **kwargs): ...

# src/contracts/loader.py
class AbstractLoader(ABC):
    @abstractmethod
    def load(self, *args, **kwargs): ...

# src/contracts/local_json.py — LocalJsonLoader writing the {source_url,user_prompt,items,meta} payload
```

### 4.3 The `CONFIG` + `<Name>ETL` contract (from `scrapers/books/etl.py`)

```python
CONFIG = {
    "extractor":   {"_class": <Name>Extractor,   "params": {"source_url": SOURCE_URL}},
    "transformer": {"_class": <Name>Transformer, "params": {"source_name": SOURCE_NAME, "source_url": SOURCE_URL}},
    "validator":   {"_class": <Name>Validator},
    "loader":      {"_class": LocalJsonLoader,    "params": {"export_prefix": "<slug>"}},
}

class <Name>ETL(BaseETL):
    async def extract(...) -> list[dict]: ...
    def transform(raw_items) -> dict: ...      # returns {"items": [...], "summary": {...}, ...}
    def validate(payload) -> None: ...
    def load(payload, output_path, export_dir) -> Path | None: ...
    async def run(browser_mode, output_path, export_dir, diagnostics_dir, simulate_failure="none", quiet=False) -> dict:
        # extract -> transform -> validate -> load, writing failure artifacts on error
```

### 4.4 Output payload shape

```json
{
  "source_url": "...",
  "user_prompt": "...",
  "items": [ { "...": "..." } ],
  "summary": { "items": 0 },
  "meta": { "mode": "generate_self_healing", "scraper": "<slug>" }
}
```

### 4.5 Manifest `scraper_target.json` (written by the agent, validated by the host)

```json
{
  "name": "<slug>",
  "kind": "folder_etl",
  "source_url": "https://...",
  "files": ["main.py", "etl.py", "settings.py", "extractor/<slug>.py", "transformer/<slug>.py", "validator/<slug>.py", "models/<slug>.py"],
  "allowed_paths": ["etl.py", "extractor/<slug>.py", "transformer/<slug>.py", "validator/<slug>.py", "models/<slug>.py", "settings.py"],
  "run_command": ["uv", "run", "python", "-m", "scrapers.<slug>.main", "run", "--quiet", "--browser", "playwright"],
  "verification_command": ["uv", "run", "python", "-m", "scrapers.<slug>.main", "run", "--quiet", "--browser", "playwright"],
  "output_path": "output/scrapers/<slug>/output.json"
}
```

### 4.6 Layer rules (global ETL rules — must hold in generated code)

- **Separation:** the CLI holds no scraping logic beyond flow parametrization; extraction lives in
  the extractor; shaping/normalization in the transformer; schema/quantity checks in the validator;
  writing output in the loader.
- **Loader is source-agnostic:** it must not know how data was scraped; it only writes the payload.
- **Validator guards output:** empty/degenerate payloads must fail validation rather than silently
  writing an empty output (mirrors the `df.empty`-before-delete idempotency rule in
  `db-to-bigquery-etl`).
- **No secrets in code/output:** credentials only via env; never printed or persisted.
- **Deterministic per goal:** the scraper targets this one scrape goal; no free browsing, no
  CAPTCHA/anti-bot bypass; diagnostics go to the diagnostics dir.

---

## 5. Agent prompt (core of every generate run)

Based on `_build_scrape_prompt` in `GeneratedCodeScrapeDiscovery`
([auto_scraper.py](src/discovery/auto_scraper.py)), changed to:

- **Persist the code** into `--target-dir`; do NOT delete it.
- **Follow §4 exactly** — the host injects §4 (this spec's canonical infrastructure) into the
  prompt verbatim so the agent conforms every run: required directory layout, contract base classes
  to subclass, the `CONFIG`/`<Name>ETL` shape, output payload shape, and the manifest.
- **Write `scraper_target.json`** itself (D2), with correct `files`/`allowed_paths`/`run_command`.
- Keep `poc-simplest` guardrails: Playwright MCP for inspection, no CAPTCHA/anti-bot bypass,
  diagnostics under the diagnostics dir, never log credentials, run unattended.
- Finish only after the project imports/compiles (`uv run python -m compileall`) and a first
  `run` produces a valid payload — or a structured blocker report.

---

## 6. Work map (what to port / add)

- [ ] `src/contracts/` — port ETL contracts + `LocalJsonLoader` from `main`.
- [ ] `src/scraper_target.py` — `ScraperTarget` + `resolve_scraper_target` (support `folder_etl`).
- [ ] `src/discovery/runtime.py` — runtime loader for generated modules (if we also keep the flat
      `discovery_run` kind).
- [ ] `src/repair/` + `src/agents/repair.py` — repair loop + repair agents, **plus new diff
      emission** (D5): capture unified diff of `allowed_paths` before/after each heal into
      `diagnostics/repair-<n>.diff`.
- [ ] `src/audit/`, `src/semi_discovery/`, `src/breaker/` — remaining self-healing modes.
- [ ] `src/notification/mock_email.py` — repair notifications.
- [ ] `src/config/general.py` — **merge** self-healing paths/settings (repair notifications,
      audit/break/semi-discovery diagnostics, `repair_attempts`, `repair_timeout`) into the current
      config (which already has `generated_code_*` + `sessions_dir`). Do not overwrite.
- [ ] `main.py` — add `generate-self-healing`; restore `run`/`repair`/`audit`/`semi-discover`/
      `break`; keep existing `discover`/`discover-code`/`validate`/`diagnose` and all
      `poc-simplest` flags.
- [ ] New generating class (extends `GeneratedCodeScrapeDiscovery`): scaffold `--target-dir`, inject
      §4 into the prompt, persist the project, validate structure + manifest, run once to verify.
- [ ] `scrapers/` package root (`__init__.py`, `discovery/.gitkeep`) like `main`.

---

## 7. Rollout phases

1. **Phase 0 (this):** branch + spec + confirmed decisions §1.1.
2. **Phase 1:** port `src/contracts/`, `src/scraper_target.py`, merge `src/config/general.py`.
3. **Phase 2:** generating class + `generate-self-healing` command with all flags; enforce §4.
4. **Phase 3:** restore `run` + `repair`/`--auto-repair` (+ `repair.py`, notifications) + diff
   emission (D5).
5. **Phase 4:** `audit`, `semi-discover`, `break`.
6. **Phase 5:** end-to-end example (e.g. Amazon bestsellers) + README/ARCHITECTURE update.

---

## 8. Acceptance criteria (draft)

- `generate-self-healing --claude --url ... --prompt-file ...` produces a persistent, runnable
  full-ETL scraper project matching §4 (code is NOT deleted) + a valid `scraper_target.json`.
- The generated project imports/compiles and `run --path <scraper>` reproduces the output payload.
- After a deliberate `break`, `repair --path <scraper>` restores a working scraper within
  `--repair-attempts` and writes a unified diff of exactly what changed (D5).
- All modes honor `--claude`/`--openai`, `--prompt-file`, `--use-credentials`.
</content>
