"""
EnvSetupAgent — tracks environment and tool installation.

Records every installation attempt: what was tried, what worked,
what failed, and why. Builds institutional memory about dev environment
setup across projects and machines.

Usage:
    from agent_framework import load_team, save_team
    from jobs.env_setup.agent import EnvSetupAgent

    team = load_team("team.json")
    setup = EnvSetupAgent("env_setup", team, engine="claude-opus-4-6")
    setup.record_attempt(
        tool="php",
        version="7.4.33",
        method="chocolatey",
        success=True,
        notes="choco install php --version=7.4.33"
    )
    setup.save_state()
    save_team(team)
"""

from datetime import datetime

from agent_framework import Agent


class EnvSetupAgent(Agent):
    """
    Tracks environment setup attempts and builds installation memory.

    Deposits:
    - installations: list of {tool, version, method, success, notes, timestamp}
    - findings: what worked, what failed, alternative approaches
    """

    def _apply_experience(self):
        """Recall past installation attempts."""
        self._past_installs = self.experience.get("installations", [])
        self._failures = self.recall("install_failure")
        self._alternatives = self.recall("alternative_method")

        if self._past_installs:
            self.log(f"Loaded {len(self._past_installs)} past installation records")
        if self._failures:
            self.log(f"Loaded {len(self._failures)} past failures to avoid")

    def record_attempt(self, tool, version, method, success, notes="", duration_s=None):
        """Record an installation attempt (success or failure)."""
        record = {
            "tool": tool,
            "version": version,
            "method": method,
            "success": success,
            "notes": notes,
            "timestamp": datetime.now().isoformat(),
        }
        if duration_s is not None:
            record["duration_s"] = duration_s

        if "installations" not in self.experience:
            self.experience["installations"] = []
        self.experience["installations"].append(record)

        if not success:
            self.learn(
                "install_failure",
                f"{tool} {version} via {method} failed",
                notes,
                context=f"{tool}:{version}:{method}",
            )
        else:
            self.learn(
                "install_success",
                f"{tool} {version} via {method} succeeded",
                notes,
                context=f"{tool}:{version}:{method}",
            )

    def record_alternative(self, tool, failed_method, working_method, notes=""):
        """Record when a fallback method works after a primary method fails."""
        self.learn(
            "alternative_method",
            f"{tool}: {failed_method} failed, {working_method} worked",
            notes,
            context=f"{tool}:{failed_method}->{working_method}",
        )

    def get_best_method(self, tool):
        """Suggest the best installation method based on past experience."""
        successes = [i for i in self._past_installs
                     if i["tool"] == tool and i["success"]]
        failures = [i for i in self._past_installs
                    if i["tool"] == tool and not i["success"]]

        if successes:
            # Return most recent successful method
            return successes[-1]["method"]
        if failures:
            # Return methods to avoid
            failed_methods = [f["method"] for f in failures]
            self.log(f"Avoid for {tool}: {failed_methods}")
        return None

    def run(self, **kwargs):
        self._apply_experience()
        self.log(f"Environment setup agent ready. {len(self._past_installs)} past records.")
        self.save_state()
        return {
            "status": "ready",
            "past_installs": len(self._past_installs),
            "known_failures": len(self._failures),
        }
