from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Any

from src.agents.credentials import Credentials
from src.utils import write_json


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load generated module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def run_generated_discovery_scraper(
    *,
    run_dir: Path,
    source_url: str,
    user_prompt: str,
    output_path: Path,
    credentials: Credentials | None = None,
) -> dict[str, Any]:
    generated_dir = run_dir / "generated"
    extractor_module = _load_module("discovery_runtime_extractor", generated_dir / "extractor.py")
    transformer_module = _load_module("discovery_runtime_transformer", generated_dir / "transformer.py")
    loader_module = _load_module("discovery_runtime_loader", generated_dir / "loader.py")

    extractor_class = getattr(extractor_module, "DiscoveryExtractor", None)
    transformer_class = getattr(transformer_module, "DiscoveryTransformer", None)
    loader_class = getattr(loader_module, "DiscoveryLoader", None)
    if extractor_class is None:
        raise RuntimeError("generated/extractor.py must define DiscoveryExtractor.")
    if transformer_class is None:
        raise RuntimeError("generated/transformer.py must define DiscoveryTransformer.")
    if loader_class is None:
        raise RuntimeError("generated/loader.py must define DiscoveryLoader.")

    extractor = extractor_class(source_url=source_url, credentials=credentials, artifacts_dir=generated_dir)
    raw_items = extractor.extract()
    if inspect.isawaitable(raw_items):
        raw_items = await raw_items
    if not isinstance(raw_items, list):
        raise RuntimeError("generated extractor returned a non-list value.")

    transformer = transformer_class(source_url=source_url, user_prompt=user_prompt, run_dir=run_dir)
    payload = transformer.transform(raw_items=raw_items)
    if not isinstance(payload, dict):
        raise RuntimeError("generated transformer returned a non-dict value.")
    if "items" not in payload or not isinstance(payload["items"], list):
        raise RuntimeError("generated transformer payload must contain an items list.")
    payload.setdefault("source_url", source_url)
    payload.setdefault("user_prompt", user_prompt)
    payload.setdefault("meta", {})
    if isinstance(payload["meta"], dict):
        payload["meta"].update(
            {
                "mode": "llm_generated_discovery",
                "artifacts_dir": str(run_dir),
                "extractor": str(generated_dir / "extractor.py"),
                "transformer": str(generated_dir / "transformer.py"),
            }
        )

    loader = loader_class(run_dir=run_dir, output_path=output_path)
    loader.load(raw_items=raw_items, payload=payload)
    write_json(run_dir / "raw_items.json", raw_items)
    write_json(run_dir / "output.json", payload)
    return payload
