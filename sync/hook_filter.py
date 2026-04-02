#!/usr/bin/env python3
"""
Claude Code PostToolUse hook filter.
Reads tool event JSON from stdin.
Routes to kos_sync.py --db <target> based on which source file was edited.

Only two files feed Notion:
  kos-incident.md       → --db i   (Incidents DB only)
  kos-system-design.md  → (no --db, full sync: K + P + D + TA)

All other references/ files are Claude-only knowledge — no Notion sync needed.
"""
import json
import sys
import subprocess
import os

data = json.load(sys.stdin)
fp = data.get("tool_input", {}).get("file_path", "").replace("\\", "/")

# Map filename → optional --db argument (None = full sync)
FILE_DB_MAP = {
    "kos-incident.md":       ["--db", "i"],
    "kos-knowledge.md":     ["--db", "k"],
    "kos-patterns.md":      ["--db", "p"],
    "kos-decisions.md":     ["--db", "d"],
    "kos-tech-assets.md":   ["--db", "ta"],
    "kos-system-design.md": [],          # legacy: full sync K + P + D + TA
}

matched_args = None
for filename, db_args in FILE_DB_MAP.items():
    if fp.endswith(filename):
        matched_args = db_args
        break

if matched_args is None:
    # Not a Notion source file — exit silently
    sys.exit(0)

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cmd  = [sys.executable, os.path.join(root, "sync", "kos_sync.py")] + matched_args
result = subprocess.run(cmd, cwd=root)
sys.exit(result.returncode)
