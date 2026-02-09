"""
Team I/O: load and save team.json files.

The team.json file is the persistent memory for an agent team.
One file = one team's entire memory. Portable, diffable, version-controlled.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path


TEAM_FILE = "team.json"


def load_team(team_path=None):
    """Load team.json from the given path or current directory."""
    path = Path(team_path) if team_path else Path(TEAM_FILE)
    if not path.exists():
        raise FileNotFoundError(f"Team file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_team(team, team_path=None, backup=True):
    """Save team.json with optional backup of previous version."""
    path = Path(team_path) if team_path else Path(TEAM_FILE)
    if backup and path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.with_name(f"team_backup_{ts}.json")
        shutil.copy2(path, backup_path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(team, f, ensure_ascii=False, indent=2)
