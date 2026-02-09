"""
LogAnalyzerAgent — parse logs, categorize errors, track frequency trends.

Usage:
    from agent_framework import load_team, save_team
    from jobs.log_analyzer.agent import LogAnalyzerAgent

    team = load_team("team.json")
    agent = LogAnalyzerAgent("analyzer", team)
    results = agent.run()
    save_team(team)
"""

import re
from pathlib import Path

from agent_framework import Agent


class LogAnalyzerAgent(Agent):
    """
    Parses log files, categorizes errors by severity and pattern,
    tracks frequency trends across runs.
    """

    def _apply_experience(self):
        """Load previous error frequency for trend detection."""
        self._prev_frequency = dict(self.experience.get("error_frequency", {}))
        self._last_positions = dict(self.experience.get("last_analyzed_positions", {}))

    def _categorize_line(self, line):
        """
        Categorize a log line by severity.

        Returns (severity, matched_pattern) or (None, None).
        """
        patterns = self.config.get("error_patterns", {})
        severity_order = self.config.get("severity_order",
                                         ["critical", "error", "warning", "info"])
        # Check in severity order — return highest match
        for severity in severity_order:
            for pattern in patterns.get(severity, []):
                if re.search(pattern, line, re.IGNORECASE):
                    return severity, pattern
        return None, None

    def _read_log(self, log_path):
        """
        Read log lines, optionally starting from last analyzed position.

        Returns list of lines.
        """
        path = Path(log_path)
        if not path.exists():
            self.learn("missing_log", f"Log file not found: {log_path}",
                       "Check path or wait for log creation", context=log_path)
            return []

        tail_lines = self.config.get("tail_lines", 1000)
        last_pos = self._last_positions.get(str(log_path), 0)

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                # Seek to last position if available
                if last_pos > 0:
                    f.seek(last_pos)
                lines = f.readlines()
                new_pos = f.tell()

            self._last_positions[str(log_path)] = new_pos

            # If no previous position, only read tail
            if last_pos == 0 and len(lines) > tail_lines:
                lines = lines[-tail_lines:]

            return lines
        except OSError as e:
            self.learn("read_error", f"Cannot read {log_path}", str(e),
                       context=log_path)
            return []

    def run(self, log_paths=None, **kwargs):
        """
        Analyze log files and categorize errors.

        Args:
            log_paths: list of log file paths (overrides config)

        Returns:
            dict with categorized errors, frequency, trends
        """
        self._apply_experience()

        paths = log_paths or self.config.get("log_paths", [])
        track_freq = self.config.get("track_frequency", True)

        categorized = {}
        current_frequency = {}

        for log_path in paths:
            lines = self._read_log(log_path)
            self.log(f"Analyzing {log_path}: {len(lines)} lines")

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                severity, pattern = self._categorize_line(line)
                if severity:
                    categorized.setdefault(severity, []).append({
                        "file": str(log_path),
                        "line": line[:500],  # truncate very long lines
                        "pattern": pattern,
                    })
                    key = f"{severity}:{pattern}"
                    current_frequency[key] = current_frequency.get(key, 0) + 1

        # Detect trends
        trends = {}
        if track_freq and self._prev_frequency:
            for key, count in current_frequency.items():
                prev_count = self._prev_frequency.get(key, 0)
                if count > prev_count * 1.5 and count > 5:
                    trends[key] = {"previous": prev_count, "current": count,
                                   "trend": "increasing"}
                    self.learn("trend_alert",
                               f"Error pattern '{key}' increased: {prev_count} → {count}",
                               "Investigate root cause",
                               context=key)

        # Summary
        summary = {severity: len(entries)
                   for severity, entries in categorized.items()}

        # Update experience
        self.experience["error_frequency"] = current_frequency
        self.experience["last_analyzed_positions"] = self._last_positions

        self.save_state()

        return {
            "summary": summary,
            "categorized": categorized,
            "frequency": current_frequency,
            "trends": trends,
            "total_issues": sum(summary.values()),
        }
