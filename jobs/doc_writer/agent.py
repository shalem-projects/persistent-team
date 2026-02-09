"""
DocWriterAgent — tracks documentation coverage, identifies gaps, generates summaries.

A development meta-agent: it helps you MAINTAIN the project, it's not the product.

Usage:
    from agent_framework import load_team, save_team
    from jobs.doc_writer.agent import DocWriterAgent

    team = load_team("team.json")
    agent = DocWriterAgent("writer", team)
    report = agent.run()
    save_team(team)
"""

import os
import re
from pathlib import Path
from datetime import datetime

from agent_framework import Agent


class DocWriterAgent(Agent):
    """
    Scans source code for documentation gaps and tracks what's been documented.

    Learns which files change frequently (need fresh docs), which are
    well-documented, and which are chronically undocumented.
    """

    def _apply_experience(self):
        """Load previous documentation state."""
        self._prev_documented = dict(self.experience.get("documented_files", {}))
        self._prev_undocumented = list(self.experience.get("undocumented_files", []))

    def _check_file_docs(self, filepath):
        """
        Check if a Python file has basic documentation.

        Returns:
            dict with has_module_doc, has_class_docs, has_func_docs, coverage score
        """
        try:
            content = Path(filepath).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        has_module_doc = bool(re.match(r'\s*"""', content) or
                             re.match(r"\s*'''", content))

        # Count classes and functions, check which have docstrings
        class_defs = list(re.finditer(r"^class\s+\w+", content, re.MULTILINE))
        func_defs = list(re.finditer(r"^(?:    )?def\s+\w+", content, re.MULTILINE))

        documented_classes = 0
        for match in class_defs:
            after = content[match.end():match.end() + 200]
            if re.search(r':\s*\n\s+"""', after) or re.search(r":\s*\n\s+'''", after):
                documented_classes += 1

        documented_funcs = 0
        for match in func_defs:
            after = content[match.end():match.end() + 200]
            if re.search(r':\s*\n\s+"""', after) or re.search(r":\s*\n\s+'''", after):
                documented_funcs += 1

        total_items = len(class_defs) + len(func_defs) + 1  # +1 for module
        documented_items = documented_classes + documented_funcs + (1 if has_module_doc else 0)
        coverage = documented_items / total_items if total_items > 0 else 0

        return {
            "has_module_doc": has_module_doc,
            "classes": len(class_defs),
            "documented_classes": documented_classes,
            "functions": len(func_defs),
            "documented_functions": documented_funcs,
            "coverage": round(coverage, 2),
        }

    def run(self, source_dirs=None, **kwargs):
        """
        Scan source directories and assess documentation coverage.

        Args:
            source_dirs: list of directories to scan (overrides config)

        Returns:
            dict with coverage stats, undocumented files, changes since last run
        """
        self._apply_experience()

        dirs = source_dirs or self.config.get("source_dirs", [])
        track_coverage = self.config.get("track_coverage", True)

        file_reports = {}
        undocumented = []
        well_documented = []

        for source_dir in dirs:
            source_path = Path(source_dir)
            if not source_path.exists():
                self.learn("missing_dir", f"Source directory not found: {source_dir}",
                           "Check path configuration", context=source_dir)
                continue

            for root, dirs_list, files in os.walk(source_path):
                # Skip common non-source directories
                dirs_list[:] = [d for d in dirs_list
                                if d not in ("__pycache__", ".git", "node_modules",
                                             "venv", ".venv", ".tox")]

                for filename in files:
                    if not filename.endswith(".py"):
                        continue

                    filepath = os.path.join(root, filename)
                    report = self._check_file_docs(filepath)
                    if report is None:
                        continue

                    file_reports[filepath] = report

                    if report["coverage"] < 0.3:
                        undocumented.append(filepath)
                    elif report["coverage"] >= 0.8:
                        well_documented.append(filepath)

        # Detect newly undocumented files (were documented before)
        prev_documented_set = {f for f, info in self._prev_documented.items()
                               if info.get("coverage", 0) >= 0.3}
        newly_undocumented = [f for f in undocumented if f in prev_documented_set]

        if newly_undocumented:
            self.learn("doc_regression",
                       f"{len(newly_undocumented)} files lost documentation",
                       "Code changed without updating docs",
                       context="; ".join(newly_undocumented[:5]))

        # Detect chronically undocumented files
        if self._prev_undocumented:
            chronic = set(undocumented) & set(self._prev_undocumented)
            if chronic:
                self.learn("chronic_gap",
                           f"{len(chronic)} files remain undocumented across runs",
                           "Prioritize documenting these files",
                           context="; ".join(list(chronic)[:5]))

        # Overall stats
        total_files = len(file_reports)
        avg_coverage = (sum(r["coverage"] for r in file_reports.values()) / total_files
                        if total_files > 0 else 0)

        # Update experience
        self.experience["documented_files"] = file_reports
        self.experience["undocumented_files"] = undocumented
        self.experience["last_doc_pass"] = datetime.now().isoformat()

        self.log(f"Scanned {total_files} files. "
                 f"Avg coverage: {avg_coverage:.0%}. "
                 f"Undocumented: {len(undocumented)}")

        self.save_state()

        return {
            "total_files": total_files,
            "average_coverage": round(avg_coverage, 2),
            "well_documented": len(well_documented),
            "undocumented": len(undocumented),
            "newly_undocumented": newly_undocumented,
            "undocumented_files": undocumented,
            "file_reports": file_reports,
        }
