"""
CodeReviewerAgent — reviews code changes for patterns, regressions, and style.

A development meta-agent: it helps you BUILD better code, it's not the product.

Usage:
    from agent_framework import load_team, save_team
    from jobs.code_reviewer.agent import CodeReviewerAgent

    team = load_team("team.json")
    agent = CodeReviewerAgent("reviewer", team)
    findings = agent.run(changed_files=["src/auth.py", "src/api.py"])
    save_team(team)
"""

import re
from pathlib import Path

from agent_framework import Agent


class CodeReviewerAgent(Agent):
    """
    Reviews code changes against known patterns and accumulated lessons.

    Learns from past reviews: which patterns recur, which fixes stick,
    which anti-patterns keep appearing. Each review gets smarter.
    """

    def _apply_experience(self):
        """Load known anti-patterns and regression history."""
        self._known_antipatterns = self.recall("anti_pattern")
        self._known_regressions = self.recall("regression")
        self.log(f"Loaded {len(self._known_antipatterns)} known anti-patterns, "
                 f"{len(self._known_regressions)} past regressions")

    def _check_antipatterns(self, filepath, content):
        """Check file content against configured and learned anti-patterns."""
        findings = []
        patterns = self.config.get("anti_patterns", [])

        # Also check patterns learned from past reviews
        for lesson in self._known_antipatterns:
            pattern = lesson.get("context", "")
            if pattern:
                patterns.append(pattern)

        for pattern in patterns:
            try:
                matches = list(re.finditer(pattern, content))
                for match in matches:
                    line_num = content[:match.start()].count("\n") + 1
                    findings.append({
                        "file": filepath,
                        "line": line_num,
                        "severity": "warning",
                        "type": "anti_pattern",
                        "pattern": pattern,
                        "match": match.group()[:100],
                    })
            except re.error:
                pass  # skip invalid regex patterns

        return findings

    def _check_style(self, filepath, content):
        """Check file against style rules."""
        findings = []
        rules = self.config.get("style_rules", [])

        for rule in rules:
            pattern = rule.get("pattern", "")
            message = rule.get("message", "Style issue")
            severity = rule.get("severity", "suggestion")

            try:
                if re.search(pattern, content):
                    findings.append({
                        "file": filepath,
                        "severity": severity,
                        "type": "style",
                        "message": message,
                        "pattern": pattern,
                    })
            except re.error:
                pass

        return findings

    def run(self, changed_files=None, **kwargs):
        """
        Review changed files for issues.

        Args:
            changed_files: list of file paths to review

        Returns:
            dict with findings by severity, summary stats
        """
        self._apply_experience()

        files = changed_files or []
        all_findings = []

        for filepath in files:
            path = Path(filepath)
            if not path.exists():
                self.learn("missing_file", f"File not found: {filepath}",
                           "Check path or file was deleted", context=filepath)
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                self.learn("read_error", f"Cannot read {filepath}",
                           str(e), context=filepath)
                continue

            findings = self._check_antipatterns(filepath, content)
            findings.extend(self._check_style(filepath, content))
            all_findings.extend(findings)

            if findings:
                self.log(f"{filepath}: {len(findings)} issue(s)")
            else:
                self.log(f"{filepath}: clean")

        # Categorize findings
        by_severity = {}
        for finding in all_findings:
            sev = finding["severity"]
            by_severity.setdefault(sev, []).append(finding)

        # Track patterns for trend detection
        patterns_seen = self.experience.get("patterns_seen", {})
        for finding in all_findings:
            key = finding.get("pattern", finding.get("message", "unknown"))
            patterns_seen[key] = patterns_seen.get(key, 0) + 1
        self.experience["patterns_seen"] = patterns_seen

        # Record recurring patterns as lessons
        for pattern, count in patterns_seen.items():
            if count >= 3 and not any(
                l.get("context") == pattern for l in self.recall("recurring_pattern")
            ):
                self.learn("recurring_pattern",
                           f"Pattern appears {count}+ times across reviews",
                           "Consider adding to project linter or style guide",
                           context=pattern)

        if all_findings:
            self.experience["regressions_caught"] = (
                self.experience.get("regressions_caught", 0) +
                len(by_severity.get("critical", []))
            )

        self.save_state()

        return {
            "total_issues": len(all_findings),
            "by_severity": {k: len(v) for k, v in by_severity.items()},
            "findings": all_findings,
            "files_reviewed": len(files),
        }
