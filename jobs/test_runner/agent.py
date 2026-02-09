"""
TestRunnerAgent — runs tests, tracks flaky tests, deposits failure patterns.

A development meta-agent: it helps you BUILD reliable code, it's not the product.

Usage:
    from agent_framework import load_team, save_team
    from jobs.test_runner.agent import TestRunnerAgent

    team = load_team("team.json")
    agent = TestRunnerAgent("tester", team)
    results = agent.run()
    save_team(team)
"""

import subprocess
import re
from datetime import datetime

from agent_framework import Agent


class TestRunnerAgent(Agent):
    """
    Runs test suites and tracks results across incarnations.

    Learns which tests are flaky (pass/fail inconsistently), which
    failures are new vs recurring, and what error patterns appear.
    """

    def _apply_experience(self):
        """Load flaky test history and past failure patterns."""
        self._flaky_tests = dict(self.experience.get("flaky_tests", {}))
        self._failure_history = dict(self.experience.get("failure_history", {}))
        self.log(f"Tracking {len(self._flaky_tests)} known flaky tests")

    def _parse_results(self, output):
        """
        Parse test output into structured results.

        Override this for non-pytest frameworks. Default implementation
        parses pytest-style output.

        Returns:
            dict with passed, failed, errors, test_details
        """
        results = {"passed": 0, "failed": 0, "errors": 0, "test_details": []}

        # Parse pytest summary line: "X passed, Y failed, Z errors"
        summary = re.search(
            r"(\d+) passed(?:.*?(\d+) failed)?(?:.*?(\d+) error)?", output
        )
        if summary:
            results["passed"] = int(summary.group(1) or 0)
            results["failed"] = int(summary.group(2) or 0)
            results["errors"] = int(summary.group(3) or 0)

        # Parse individual FAILED lines
        for match in re.finditer(r"FAILED\s+(\S+)", output):
            test_name = match.group(1)
            results["test_details"].append({
                "name": test_name,
                "status": "failed",
            })

        # Parse individual ERROR lines
        for match in re.finditer(r"ERROR\s+(\S+)", output):
            test_name = match.group(1)
            results["test_details"].append({
                "name": test_name,
                "status": "error",
            })

        return results

    def _update_flaky_tracking(self, results):
        """Track tests that flip between pass and fail across runs."""
        threshold = self.config.get("flaky_threshold", 3)
        failed_names = {
            t["name"] for t in results["test_details"]
            if t["status"] in ("failed", "error")
        }

        for test_name in failed_names:
            history = self._failure_history.get(test_name, [])
            history.append({"run": self.experience.get("run_count", 0) + 1,
                            "status": "failed"})
            self._failure_history[test_name] = history[-20:]  # keep last 20

            # Check for flakiness: failed sometimes, passed other times
            if len(history) >= threshold:
                fail_count = sum(1 for h in history if h["status"] == "failed")
                if 0 < fail_count < len(history):
                    self._flaky_tests[test_name] = {
                        "fail_rate": fail_count / len(history),
                        "last_seen": datetime.now().isoformat(),
                    }
                    if not any(l.get("context") == test_name
                               for l in self.recall("flaky_test")):
                        self.learn("flaky_test",
                                   f"Test flips between pass/fail: {test_name}",
                                   f"Fail rate: {fail_count}/{len(history)} runs",
                                   context=test_name)

    def run(self, test_paths=None, **kwargs):
        """
        Run tests and analyze results.

        Args:
            test_paths: list of test paths (overrides config)

        Returns:
            dict with pass/fail counts, flaky tests, new failures
        """
        self._apply_experience()

        command = self.config.get("test_command", "pytest")
        paths = test_paths or self.config.get("test_paths", [])
        timeout = self.config.get("timeout_seconds", 300)

        cmd_parts = [command] + paths
        self.log(f"Running: {' '.join(cmd_parts)}")

        try:
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout + "\n" + result.stderr
        except subprocess.TimeoutExpired:
            self.learn("timeout", f"Tests timed out after {timeout}s",
                       "Increase timeout or split test suite")
            self.save_state()
            return {"error": "timeout", "timeout_seconds": timeout}
        except FileNotFoundError:
            self.learn("missing_tool", f"Test command not found: {command}",
                       "Install test framework or check PATH")
            self.save_state()
            return {"error": "command_not_found", "command": command}

        # Parse results
        results = self._parse_results(output)

        # Detect new failures (weren't failing last run)
        last_summary = self.experience.get("last_run_summary", {})
        last_failures = set(last_summary.get("failed_tests", []))
        current_failures = {
            t["name"] for t in results["test_details"]
            if t["status"] in ("failed", "error")
        }
        new_failures = current_failures - last_failures

        if new_failures:
            for test in new_failures:
                self.learn("new_failure", f"New test failure: {test}",
                           "Was passing before — investigate regression",
                           context=test)

        # Track flaky tests
        self._update_flaky_tracking(results)

        # Update experience
        self.experience["flaky_tests"] = self._flaky_tests
        self.experience["failure_history"] = self._failure_history
        self.experience["last_run_summary"] = {
            "timestamp": datetime.now().isoformat(),
            "passed": results["passed"],
            "failed": results["failed"],
            "errors": results["errors"],
            "failed_tests": list(current_failures),
        }

        self.log(f"Results: {results['passed']} passed, "
                 f"{results['failed']} failed, {results['errors']} errors")
        if new_failures:
            self.log(f"NEW failures: {new_failures}")
        if self._flaky_tests:
            self.log(f"Flaky tests: {list(self._flaky_tests.keys())}")

        self.save_state()

        return {
            "passed": results["passed"],
            "failed": results["failed"],
            "errors": results["errors"],
            "new_failures": list(new_failures),
            "flaky_tests": self._flaky_tests,
            "test_details": results["test_details"],
        }
