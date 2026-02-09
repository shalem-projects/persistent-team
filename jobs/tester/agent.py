"""
TesterAgent — verifies components work after changes.

A creation agent that reads other agents' deposits to understand what was
changed, then checks each component individually. Adapts test strategy to
available tooling.

Test levels (from cheapest to most expensive):
1. syntax     — files parse without errors
2. include    — all imports/requires resolve
3. endpoint   — API/AJAX endpoints return valid responses
4. smoke      — main page loads, key elements render
5. regression — previously broken things stay fixed

Usage:
    from agent_framework import load_team, save_team
    from jobs.tester.agent import TesterAgent

    team = load_team("team.json")
    tester = TesterAgent("tester", team, engine="claude-opus-4-6")

    # After a refactoring phase:
    results = tester.run(
        source_path="/path/to/project",
        phase="db_architect",
        changed_files=["includes/Database.php", "includes/db_functions.php"]
    )

    save_team(team)
"""

import subprocess
from datetime import datetime
from pathlib import Path

from agent_framework import Agent


class TesterAgent(Agent):
    """
    Verifies components work after changes.

    Reads from other agents:
    - auditor's file_map → knows what files exist
    - auditor's function_index → knows what functions should be reachable
    - auditor's lessons → knows about traps and load-bearing hacks
    - splitter's files_created → knows what was just extracted

    Deposits:
    - test_results: per-file, per-endpoint results
    - regressions_found: things that broke
    - lessons_learned: what to always check, what's flaky
    """

    def _apply_experience(self):
        """Recall past test failures to build regression checklist."""
        self._regressions = self.recall("regression")
        self._flaky = self.recall("flaky")
        past_failures = self.recall("test_failure")

        if self._regressions:
            self.log(f"Loaded {len(self._regressions)} known regressions to re-check")
        if past_failures:
            self.log(f"Loaded {len(past_failures)} past test failures")

    def _check_syntax_php(self, source_path, files):
        """Run php -l on each file. Returns list of (file, pass/fail, error)."""
        results = []
        for filepath in files:
            full_path = Path(source_path) / filepath
            if not full_path.exists() or not filepath.endswith(".php"):
                continue
            try:
                result = subprocess.run(
                    ["php", "-l", str(full_path)],
                    capture_output=True, text=True, timeout=10
                )
                passed = result.returncode == 0
                results.append({
                    "file": filepath,
                    "level": "syntax",
                    "passed": passed,
                    "error": result.stderr.strip() if not passed else None,
                })
                if not passed:
                    self.learn(
                        "test_failure",
                        f"Syntax error in {filepath}",
                        result.stderr.strip()[:200],
                        context=filepath,
                    )
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                results.append({
                    "file": filepath,
                    "level": "syntax",
                    "passed": None,
                    "error": f"Could not run php -l: {e}",
                })
        return results

    def _check_includes_php(self, source_path, files):
        """Verify all require/include statements point to existing files."""
        import re
        results = []
        for filepath in files:
            full_path = Path(source_path) / filepath
            if not full_path.exists() or not filepath.endswith(".php"):
                continue
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
                # Find require/include statements
                includes = re.findall(
                    r"(?:require|include)(?:_once)?\s*[\(]?\s*['\"]([^'\"]+)['\"]",
                    content
                )
                for inc in includes:
                    # Skip dynamic paths with variables
                    if "$" in inc or "__DIR__" in inc:
                        continue
                    inc_path = Path(source_path) / inc
                    exists = inc_path.exists()
                    results.append({
                        "file": filepath,
                        "level": "include_chain",
                        "include": inc,
                        "passed": exists,
                        "error": f"Missing: {inc}" if not exists else None,
                    })
                    if not exists:
                        self.learn(
                            "test_failure",
                            f"Broken include in {filepath}: {inc}",
                            "File not found after extraction",
                            context=f"{filepath} -> {inc}",
                        )
            except Exception as e:
                results.append({
                    "file": filepath,
                    "level": "include_chain",
                    "passed": None,
                    "error": str(e),
                })
        return results

    def _build_smoke_checklist(self, phase):
        """Build a manual smoke test checklist based on what phase just completed."""
        checklists = {
            "auditor": [
                "No changes to verify — auditor is read-only"
            ],
            "db_architect": [
                "Load main page — should render without errors",
                "Submit a search query — should return recommendations",
                "Check browser console for PHP errors in response",
                "Verify AJAX actions still return valid JSON: teacher_chat, track_usage, get_teacher_requests",
                "Check that SQLite fallback still works if MySQL is unavailable"
            ],
            "backend_splitter": [
                "Load main page — all sections render",
                "Submit a search — AI recommendations appear",
                "Click a recommendation card — opens correctly",
                "Submit a teacher request — saves and appears in list",
                "Support an existing request — count increments",
                "Check each AJAX action returns valid JSON (not HTML pollution)",
                "Verify ob_start() hack is removed (if AJAX is now separate file)"
            ],
            "frontend_splitter": [
                "Load main page — styles render correctly (RTL, Hebrew font)",
                "All cards display with images",
                "Category expand/collapse works",
                "YouTube modal opens and plays",
                "App iframe modal opens",
                "Autocomplete dropdown appears on search input",
                "Student link generation works",
                "Grade filtering works",
                "Check browser console — no 404s for .js or .css files"
            ],
            "cleanup": [
                "Full regression: run all checks from previous phases",
                "Verify no backup files are served publicly",
                "Verify .gitignore excludes .env, .db, .venv",
                "Check that error_log output is clean (no debug spam)"
            ]
        }
        return checklists.get(phase, ["Phase not recognized — manual review needed"])

    def _check_regressions(self, source_path):
        """Re-check all previously found regressions."""
        results = []
        for reg in self._regressions:
            # Each regression lesson has context with what to check
            results.append({
                "level": "regression",
                "original_problem": reg.get("problem", ""),
                "check": reg.get("solution", ""),
                "context": reg.get("context", ""),
                "status": "needs_manual_verification",
            })
        return results

    def run(self, source_path=None, phase=None, changed_files=None, **kwargs):
        """
        Run tests appropriate for the given phase.

        Args:
            source_path: path to the project being tested
            phase: which refactoring phase just completed (e.g. "db_architect")
            changed_files: list of files that were created/modified
        """
        self._apply_experience()

        if not source_path:
            source_path = self.config.get("source_path", ".")

        if not changed_files:
            changed_files = []

        self.log(f"Testing after phase: {phase or 'unknown'}")
        self.log(f"Changed files: {len(changed_files)}")

        all_results = []

        # Level 1: Syntax
        if changed_files:
            syntax_results = self._check_syntax_php(source_path, changed_files)
            all_results.extend(syntax_results)
            passed = sum(1 for r in syntax_results if r.get("passed"))
            failed = sum(1 for r in syntax_results if r.get("passed") is False)
            self.log(f"Syntax: {passed} passed, {failed} failed")

        # Level 2: Include chains
        if changed_files:
            include_results = self._check_includes_php(source_path, changed_files)
            all_results.extend(include_results)
            broken = [r for r in include_results if r.get("passed") is False]
            if broken:
                self.log(f"Include chains: {len(broken)} broken imports found")

        # Level 3: Smoke checklist
        checklist = self._build_smoke_checklist(phase)
        self.log(f"Smoke checklist ({len(checklist)} items):")
        for item in checklist:
            self.log(f"  [ ] {item}")

        # Level 4: Regressions
        regression_results = self._check_regressions(source_path)
        all_results.extend(regression_results)
        if regression_results:
            self.log(f"Regression checks: {len(regression_results)} items to re-verify")

        # Store results
        self.experience["test_results"] = all_results
        self.experience["last_phase_tested"] = phase
        self.experience["last_tested_at"] = datetime.now().isoformat()

        # Track any new regressions
        new_failures = [r for r in all_results
                        if r.get("passed") is False and r.get("level") != "regression"]
        if new_failures:
            for failure in new_failures:
                self.learn(
                    "regression",
                    f"Failed after {phase}: {failure.get('file', 'unknown')}",
                    failure.get("error", "See test results"),
                    context=failure.get("file") or failure.get("context"),
                )

        self.save_state()

        return {
            "status": "complete",
            "phase_tested": phase,
            "automated_results": all_results,
            "smoke_checklist": checklist,
            "regressions_to_check": len(regression_results),
            "new_failures": len(new_failures),
        }
