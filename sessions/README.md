# Browser Sessions

This directory is reserved for local browser session profiles created with `--session-profile`.

Runtime session folders are intentionally ignored by git because they may contain cookies, storage state, browser cache, screenshots, or other private authentication artifacts.

Typical layout:

```text
sessions/<profile>/
  session.md
  usage.jsonl
  storage_state.json
  user-data/
  mcp-output/
```

Use sessions only for login-required or stateful websites. Public pages should normally run without a session profile.

`usage.jsonl` is an append-only local trail. Every command that receives `--session-profile`
adds one JSON line, so you can verify that multiple direct discovery or diagnostic runs used the
same profile.
