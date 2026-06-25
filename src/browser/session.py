from __future__ import annotations

import re
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from src.utils import utc_timestamp, write_text

SESSION_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")


@dataclass(frozen=True)
class BrowserSessionProfile:
    name: str
    root_dir: Path
    profile_dir: Path
    user_data_dir: Path
    storage_state_path: Path
    mcp_output_dir: Path
    notes_path: Path
    usage_log_path: Path

    def ensure(self, *, source_url: str | None = None) -> "BrowserSessionProfile":
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.mcp_output_dir.mkdir(parents=True, exist_ok=True)
        if not self.notes_path.exists():
            write_text(self.notes_path, self._build_notes(source_url=source_url))
        return self

    def _build_notes(self, *, source_url: str | None) -> str:
        source_line = f"- Source URL: {source_url}" if source_url else "- Source URL: not bound"
        return "\n".join(
            [
                f"# Browser Session: {self.name}",
                "",
                "This folder stores local browser session artifacts for MCP-PW-SCRAPPER.",
                "Do not commit session runtime files. They may contain cookies, auth state, or other private browser data.",
                "",
                "## Metadata",
                "",
                f"- Name: {self.name}",
                source_line,
                f"- Created at: {utc_timestamp()}",
                "",
                "## Paths",
                "",
                f"- Profile dir: `{self.profile_dir}`",
                f"- MCP user data dir: `{self.user_data_dir}`",
                f"- Runtime storage state: `{self.storage_state_path}`",
                f"- MCP output dir: `{self.mcp_output_dir}`",
                f"- Usage log: `{self.usage_log_path}`",
                "",
                "## MCP hint",
                "",
                "If you want the Playwright MCP server to reuse this profile, start/configure it with paths like:",
                "",
                "```bash",
                "npx -y @playwright/mcp@latest \\",
                f"  --user-data-dir {self.user_data_dir} \\",
                f"  --storage-state {self.storage_state_path} \\",
                f"  --output-dir {self.mcp_output_dir} \\",
                "  --save-session",
                "```",
                "",
                "Direct discovery agents should use the same profile or storage state when inspecting authenticated pages.",
                "",
            ]
        )

    def record_usage(
        self,
        *,
        command: str,
        source_url: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": utc_timestamp(),
            "session_profile": self.name,
            "command": command,
            "source_url": source_url,
            "profile_dir": str(self.profile_dir),
            "storage_state_path": str(self.storage_state_path),
            "user_data_dir": str(self.user_data_dir),
            "mcp_output_dir": str(self.mcp_output_dir),
            "details": details or {},
        }
        with self.usage_log_path.open("a") as log_file:
            log_file.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def resolve_browser_session_profile(
    name: str,
    *,
    sessions_dir: Path,
    source_url: str | None = None,
) -> BrowserSessionProfile:
    selected_name = name.strip()
    if not SESSION_NAME_PATTERN.fullmatch(selected_name):
        raise ValueError(
            "Session profile name must start with a letter or digit and contain only "
            "letters, digits, underscore, dash, or dot, up to 80 characters."
        )

    root_dir = sessions_dir.expanduser()
    profile_dir = root_dir / selected_name
    profile = BrowserSessionProfile(
        name=selected_name,
        root_dir=root_dir,
        profile_dir=profile_dir,
        user_data_dir=profile_dir / "user-data",
        storage_state_path=profile_dir / "storage_state.json",
        mcp_output_dir=profile_dir / "mcp-output",
        notes_path=profile_dir / "session.md",
        usage_log_path=profile_dir / "usage.jsonl",
    )
    return profile.ensure(source_url=source_url)


def session_prompt_block(profile: BrowserSessionProfile | None) -> str:
    if profile is None:
        return "No browser session profile was selected. Use a fresh browser/session for this task."

    storage_state_status = "exists" if profile.storage_state_path.exists() else "does not exist yet"
    return "\n".join(
        [
            "A browser session profile was selected for this task.",
            f"Session profile name: {profile.name}",
            f"Session notes: {profile.notes_path}",
            f"MCP user data dir: {profile.user_data_dir}",
            f"MCP output dir: {profile.mcp_output_dir}",
            f"Runtime storage state path: {profile.storage_state_path}",
            f"Runtime storage state status: {storage_state_status}",
            "",
            "Use this session when inspecting login-required pages. Do not create a second unrelated profile.",
            "If the page is already authenticated, reuse the existing session instead of logging in again.",
            "If login is required and credentials are provided, log in through the browser and preserve the resulting session.",
            "If a CAPTCHA or anti-bot challenge appears, do not bypass it. Stop, save diagnostics, and report the blocker.",
            "",
            "For direct discovery, configure Playwright MCP/browser MCP with these paths when the page needs this authenticated state.",
        ]
    )
