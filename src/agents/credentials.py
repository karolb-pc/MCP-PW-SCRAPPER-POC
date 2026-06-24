from __future__ import annotations

import os
from pathlib import Path


Credentials = tuple[str, str]


def load_dotenv_values(path: Path = Path(".env")) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_credentials_from_env() -> Credentials:
    dotenv = load_dotenv_values()
    login = os.getenv("LOGIN") or dotenv.get("LOGIN")
    password = os.getenv("PASSWORD") or dotenv.get("PASSWORD")
    missing = [name for name, value in (("LOGIN", login), ("PASSWORD", password)) if not value]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"--use-credentials requires {joined} in the environment or .env.")
    return login or "", password or ""


def credentials_prompt_block(credentials: Credentials | None, redacted: bool) -> str:
    if credentials is None:
        return "No credentials were provided. If the page asks for login, stop and report that credentials are required."

    login, password = credentials
    if redacted:
        login = "[REDACTED]"
        password = "[REDACTED]"

    return "\n".join(
        [
            "Credentials were provided for a source page that may require login.",
            f"Login: {login}",
            f"Password: {password}",
            "",
            "Before inspecting product DOM, use Playwright MCP/browser MCP to:",
            "1. Open the source URL.",
            "2. Detect the login form in the HTML/DOM.",
            "3. Fill the login and password fields with the provided credentials.",
            "4. Submit the form and wait until the authenticated page loads.",
            "5. Continue selector inspection only after login succeeds.",
            "",
            "Never print, save, echo, or commit credential values.",
        ]
    )


def redact_values(credentials: Credentials | None) -> tuple[str, ...]:
    if credentials is None:
        return ()
    return tuple(value for value in credentials if value)
