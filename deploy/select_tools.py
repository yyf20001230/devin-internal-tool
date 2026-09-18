"""Image build helper: delete every tools/*.yaml whose id is not in $TOOLS (comma-separated).

Run inside the Dockerfile after `COPY tools/ tools/` so a per-tool image ships only its own
definition; `_users.yaml` and the knowledge/ policies are shared and left untouched.
"""
import os
import sys
from pathlib import Path

import yaml

wanted = {t.strip() for t in os.environ.get("TOOLS", "").split(",") if t.strip()}
tools_dir = Path(os.environ.get("TOOLS_DIR", "tools"))
if not wanted:
    sys.exit(0)

by_id = {yaml.safe_load(p.read_text())["id"]: p for p in tools_dir.glob("*.yaml") if not p.name.startswith("_")}
if missing := wanted - by_id.keys():
    sys.exit(f"TOOLS names unknown tool id(s): {', '.join(sorted(missing))}; known: {', '.join(sorted(by_id))}")
for tool_id, path in by_id.items():
    if tool_id not in wanted:
        path.unlink()
print("tools in image:", ", ".join(sorted(wanted)))
