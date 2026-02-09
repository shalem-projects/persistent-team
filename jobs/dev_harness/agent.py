"""
DevHarnessAgent — creates the local dev environment for a project.

Distinct from EnvSetupAgent (which installs TOOLS like PHP, Node, etc.),
this agent adapts the PROJECT itself to run locally: stubs for config files,
mock DB connections, fake API responses, auth bypasses.

Records what works offline vs what needs the real server, so future agents
and testers know which features are testable locally.

Usage:
    from agent_framework import load_team, save_team
    from jobs.dev_harness.agent import DevHarnessAgent

    team = load_team("team.json")
    harness = DevHarnessAgent("dev_harness", team, engine="claude-opus-4-6")

    harness.record_stub("connect.php", "stub", "Creates null $connection. SQLite fallback handles the rest.")
    harness.record_gap("OpenAI API calls", "Needs real API key. Can't mock without recorded responses.")
    harness.save_state()
    save_team(team)
"""

from datetime import datetime

from agent_framework import Agent


class DevHarnessAgent(Agent):
    """
    Creates and documents the local dev harness for a project.

    Deposits:
    - stubs_created: list of stub files with purpose and notes
    - gaps: features that can't be tested locally
    - server_recipe: exact command to start local server
    - lessons_learned: what broke, what worked, what to watch for
    """

    def _apply_experience(self):
        """Recall past harness setup attempts."""
        self._past_stubs = self.experience.get("stubs_created", [])
        self._known_gaps = self.experience.get("gaps", [])
        past_issues = self.recall("harness_issue")

        if self._past_stubs:
            self.log(f"Loaded {len(self._past_stubs)} previously created stubs")
        if self._known_gaps:
            self.log(f"Loaded {len(self._known_gaps)} known offline gaps")
        if past_issues:
            self.log(f"Loaded {len(past_issues)} past harness issues")

    def record_stub(self, filename, stub_type, notes=""):
        """Record a stub file created for local dev."""
        record = {
            "file": filename,
            "type": stub_type,
            "notes": notes,
            "timestamp": datetime.now().isoformat(),
        }
        if "stubs_created" not in self.experience:
            self.experience["stubs_created"] = []
        self.experience["stubs_created"].append(record)

    def record_gap(self, feature, reason):
        """Record a feature that can't be tested locally."""
        gap = {
            "feature": feature,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        }
        if "gaps" not in self.experience:
            self.experience["gaps"] = []
        self.experience["gaps"].append(gap)

    def record_server_recipe(self, command, notes=""):
        """Record the exact command to start local dev server."""
        self.experience["server_recipe"] = {
            "command": command,
            "notes": notes,
            "timestamp": datetime.now().isoformat(),
        }

    def run(self, source_path=None, **kwargs):
        self._apply_experience()

        if not source_path:
            source_path = self.config.get("source_path", ".")

        self.log(f"Dev harness agent ready for: {source_path}")
        self.log(f"Existing stubs: {len(self._past_stubs)}")
        self.log(f"Known gaps: {len(self._known_gaps)}")

        self.save_state()
        return {
            "status": "ready",
            "stubs": len(self._past_stubs),
            "gaps": len(self._known_gaps),
        }
