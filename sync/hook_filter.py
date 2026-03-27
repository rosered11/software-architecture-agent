#!/usr/bin/env python3
"""
Claude Code PostToolUse hook filter.
Reads tool event JSON from stdin.
Runs kos_sync.py only when a KOS references file was edited.
"""
import json
import sys
import subprocess
import os

data = json.load(sys.stdin)
fp = data.get("tool_input", {}).get("file_path", "").replace("\\", "/")

KOS_PATH = "skills/software-architecture-specialist/references/"

if KOS_PATH in fp:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, os.path.join(root, "sync", "kos_sync.py")],
        cwd=root
    )
    sys.exit(result.returncode)
# Non-KOS file: exit 0 silently
sys.exit(0)
