"""
ScannerAgent — scan directories, classify files, detect changes between runs.

Usage:
    from agent_framework import load_team, save_team
    from jobs.file_scanner.agent import ScannerAgent

    team = load_team("team.json")
    agent = ScannerAgent("scanner", team)
    results = agent.run()
    save_team(team)
"""

import os
import fnmatch
from pathlib import Path

from agent_framework import Agent


class ScannerAgent(Agent):
    """
    Scans directories for files, classifies by type, and detects
    changes (new, modified, deleted) between runs.
    """

    def _apply_experience(self):
        """Load previous scan snapshot for change detection."""
        self._prev_snapshot = self.experience.get("last_scan_snapshot", {})

    def _matches_patterns(self, filename):
        """Check if filename matches include/exclude patterns."""
        excludes = self.config.get("exclude_patterns", [])
        for pattern in excludes:
            if fnmatch.fnmatch(filename, pattern):
                return False

        includes = self.config.get("include_patterns", ["*"])
        for pattern in includes:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False

    def _classify(self, filepath):
        """Classify a file by its extension."""
        ext = Path(filepath).suffix.lower()
        knowledge = self.team.get("universal_knowledge", {})
        categories = knowledge.get("common_extensions", {})
        for category, extensions in categories.items():
            if ext in extensions:
                return category
        return "other"

    def run(self, directories=None, **kwargs):
        """
        Scan directories and detect changes.

        Args:
            directories: list of paths to scan (overrides config)

        Returns:
            dict with files, changes (new, modified, deleted), classifications
        """
        self._apply_experience()

        scan_dirs = directories or self.config.get("scan_directories", [])
        include_ext = self.config.get("include_extensions", [])
        track_changes = self.config.get("track_changes", True)

        current_snapshot = {}
        classifications = {}

        for scan_dir in scan_dirs:
            scan_path = Path(scan_dir)
            if not scan_path.exists():
                self.learn("missing_directory", f"Directory not found: {scan_dir}",
                           "Check path or create directory", context=scan_dir)
                continue

            for root, dirs, files in os.walk(scan_path):
                # Filter excluded directories in-place
                excludes = self.config.get("exclude_patterns", [])
                dirs[:] = [d for d in dirs
                           if not any(fnmatch.fnmatch(d, p) for p in excludes)]

                for filename in files:
                    if not self._matches_patterns(filename):
                        continue

                    if include_ext:
                        ext = Path(filename).suffix.lower()
                        if ext not in include_ext:
                            continue

                    filepath = os.path.join(root, filename)
                    try:
                        stat = os.stat(filepath)
                        current_snapshot[filepath] = {
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                        }
                        category = self._classify(filepath)
                        classifications.setdefault(category, []).append(filepath)
                    except OSError as e:
                        self.learn("scan_error", f"Cannot stat {filepath}",
                                   str(e), context=filepath)

        # Detect changes
        changes = {"new": [], "modified": [], "deleted": []}
        if track_changes and self._prev_snapshot:
            prev_files = set(self._prev_snapshot.keys())
            curr_files = set(current_snapshot.keys())

            changes["new"] = list(curr_files - prev_files)
            changes["deleted"] = list(prev_files - curr_files)

            for filepath in curr_files & prev_files:
                prev = self._prev_snapshot[filepath]
                curr = current_snapshot[filepath]
                if curr["modified"] != prev["modified"] or curr["size"] != prev["size"]:
                    changes["modified"].append(filepath)

            if changes["new"]:
                self.learn("changes_detected",
                           f"{len(changes['new'])} new files found",
                           "Review new files for relevance")
            if changes["deleted"]:
                self.learn("changes_detected",
                           f"{len(changes['deleted'])} files deleted",
                           "Check if deletions were intentional")

        # Update experience
        self.experience["last_scan_snapshot"] = current_snapshot
        self.experience["total_files_seen"] = len(current_snapshot)

        self.save_state()

        return {
            "total_files": len(current_snapshot),
            "classifications": {k: len(v) for k, v in classifications.items()},
            "changes": changes,
            "files": list(current_snapshot.keys()),
        }
