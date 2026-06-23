from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from src.etl.loader.abstract import AbstractLoader
from src.utils import utc_timestamp, write_json


class LocalJsonLoader(AbstractLoader):
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
        timestamped_path = export_dir / f"books-{utc_timestamp()}.json"
        shutil.copyfile(output_path, timestamped_path)
        shutil.copyfile(output_path, export_dir / "latest.json")
        return timestamped_path
