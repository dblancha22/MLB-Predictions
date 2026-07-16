# RTK - Rust Token Killer (Codex CLI)

**Usage**: Token-optimized CLI proxy for shell commands.

## Rule

Always prefix shell commands with `rtk`.

If `rtk` is not found on PATH, use `/Users/austinblanchard/.local/bin/rtk`.

## MLB-Predictions workflow

- Prefer `rtk git`, `rtk read`, `rtk grep`, `rtk find`, `rtk log`, and `rtk test` for repository inspection and validation.
- Do not print complete MLB Stats API JSON responses into the conversation. Save large responses to a file and inspect only the required fields with `jq`.
- Keep ingestion output concise: report counts, IDs, validation failures, and summaries rather than every processed record.
- Use targeted file reads and searches; do not dump entire notebooks, generated data files, logs, or database exports.
- Use a new focused Codex session for each ingestion script or milestone, especially after context compaction.

Examples:

```bash
rtk git status
rtk cargo test
rtk npm run build
rtk pytest -q
```

## Meta Commands

```bash
rtk gain            # Token savings analytics
rtk gain --history  # Recent command savings history
rtk proxy <cmd>     # Run raw command without filtering
```

## Verification

```bash
rtk --version
rtk gain
which rtk
```
