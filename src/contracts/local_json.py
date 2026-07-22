from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from src.contracts.loader import AbstractLoader
from src.utils import utc_timestamp, write_json


class LocalJsonLoader(AbstractLoader):
    def __init__(self, export_prefix: str = "export"):
        self.export_prefix = export_prefix

    def load(
        self,
        payload: dict[str, Any],
        output_path: Path,
        export_dir: Path | None,
    ) -> Path | None:
        write_json(output_path, payload)

        if export_dir is None:
            return None

        export_dir.mkdir(parents=True, exist_ok=True)
        timestamped_path = export_dir / f"{self.export_prefix}-{utc_timestamp()}.json"
        shutil.copyfile(output_path, timestamped_path)
        shutil.copyfile(output_path, export_dir / "latest.json")
        return timestamped_path
