from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.utils import utc_timestamp_with_microseconds, write_text


class MockEmailNotifier:
    def __init__(self, notifications_dir: Path, recipient: str):
        self.notifications_dir = notifications_dir
        self.recipient = recipient

    def send(
        self,
        subject: str,
        body: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> Path:
        timestamp = utc_timestamp_with_microseconds()
        safe_subject = re.sub(r"[^a-zA-Z0-9._-]+", "-", subject.lower()).strip("-")
        path = self.notifications_dir / f"{timestamp}-{safe_subject[:80]}.txt"
        metadata = metadata or {}

        content = "\n".join(
            [
                f"To: {self.recipient}",
                "From: mcp-pw-scrapper@example.local",
                f"Subject: {subject}",
                f"Date: {datetime.now(timezone.utc).isoformat()}",
                "",
                body,
                "",
                "Metadata:",
                json.dumps(dict(metadata), ensure_ascii=False, indent=2),
                "",
            ]
        )
        write_text(path, content)
        print(
            json.dumps(
                {
                    "status": "mock_email_sent",
                    "to": self.recipient,
                    "subject": subject,
                    "path": str(path),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return path
