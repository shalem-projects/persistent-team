"""
RefactorerAgent — phased monolith decomposition.

A team of agents that break apart large single-file or poorly-structured
codebases into modular architecture. Works in phases, each leaving the
app functional.

Pipeline:
    auditor → db_architect → backend_splitter → frontend_splitter → cleanup

Each phase depends on the previous. The auditor must run first — it produces
the file_map, function_index, and lessons that all subsequent agents need.

Usage:
    from agent_framework import load_team, save_team
    from jobs.refactorer.agent import AuditorAgent, DbArchitectAgent

    team = load_team("team.json")

    # Phase 0: Audit
    auditor = AuditorAgent("auditor", team)
    auditor.run(source_path="/path/to/monolith")
    save_team(team)

    # Phase 1: DB layer (reads auditor's deposits)
    db_arch = DbArchitectAgent("db_architect", team)
    db_arch.run(source_path="/path/to/monolith")
    save_team(team)
"""

from datetime import datetime

from agent_framework import Agent


class RefactorerBase(Agent):
    """Base class for refactoring agents with phase-awareness."""

    def _check_dependency(self):
        """Verify that the prerequisite agent has completed."""
        dep = self.config.get("depends_on")
        if dep and dep in self.team["agents"]:
            dep_status = self.team["agents"][dep]["experience"].get("status")
            if dep_status != "complete":
                self.log(f"BLOCKED: depends on '{dep}' which has status '{dep_status}'")
                return False
        return True

    def _recall_by_types(self):
        """Recall lessons from ALL agents filtered by this agent's recall_types."""
        recall_types = set(self.config.get("recall_types", []))
        if not recall_types:
            return []

        relevant = []
        for name, agent_data in self.team["agents"].items():
            lessons = agent_data.get("experience", {}).get("lessons_learned", [])
            for lesson in lessons:
                if lesson.get("category") in recall_types:
                    relevant.append(lesson)
        return relevant

    def _mark_complete(self):
        """Mark this agent's phase as complete."""
        self.experience["status"] = "complete"
        self.experience["completed_at"] = datetime.now().isoformat()


class AuditorAgent(RefactorerBase):
    """
    Phase 0: Maps the entire codebase.

    Deposits:
    - file_map: file names, line counts, section ranges
    - function_index: function name → line number + category
    - external_dependencies: files required but not in repo
    - lessons_learned: traps, anti-patterns, gotchas
    """

    def _apply_experience(self):
        """If re-running, recall what was found before."""
        past = self.recall("data_flow") + self.recall("shadow_risk")
        if past:
            self.log(f"Recalling {len(past)} lessons from previous audit")

    def run(self, source_path=None, **kwargs):
        self._apply_experience()

        if not source_path:
            source_path = self.config.get("source_path", ".")
        self.log(f"Auditing codebase at: {source_path}")

        # The actual audit work is done by the AI incarnation reading files.
        # This agent provides the structure for depositing findings.
        # When used with an LLM, the LLM does the reading and calls
        # learn() to deposit structured findings.

        self.log("Audit framework ready. LLM should now read files and deposit findings.")
        self.log("Required deposits: file_map, function_index, external_dependencies, lessons_learned")

        self.save_state()
        return {
            "status": "ready_for_deposits",
            "deposit_to": ["file_map", "function_index", "external_dependencies", "lessons_learned"],
        }


class DbArchitectAgent(RefactorerBase):
    """
    Phase 1: Creates unified DB abstraction and config system.

    Reads auditor's deposits to understand:
    - Which functions have dual MySQL/SQLite implementations
    - Where credentials are loaded from
    - What tables exist

    Deposits:
    - files_created: list of new files
    - lines_removed: count of lines eliminated
    - lessons_learned: what worked, what broke during extraction
    """

    def _apply_experience(self):
        """Recall traps from auditor before making changes."""
        relevant = self._recall_by_types()
        if relevant:
            self.log(f"Recalling {len(relevant)} relevant lessons before DB extraction")
            for lesson in relevant:
                self.log(f"  [{lesson['category']}] {lesson['problem'][:80]}")

    def run(self, source_path=None, **kwargs):
        if not self._check_dependency():
            return {"status": "blocked", "reason": f"depends on {self.config['depends_on']}"}

        self._apply_experience()

        # Read auditor's function_index to find DB functions
        auditor_exp = self.team["agents"].get("auditor", {}).get("experience", {})
        function_index = auditor_exp.get("function_index", {})
        db_functions = {k: v for k, v in function_index.items()
                        if v.get("category") in ("db", "tracking", "requests")}

        self.log(f"Found {len(db_functions)} DB-related functions to extract")
        for name, info in db_functions.items():
            self.log(f"  {name} (line {info.get('line', '?')})")

        self.save_state()
        return {
            "status": "ready",
            "db_functions": db_functions,
            "auditor_lessons": self._recall_by_types(),
        }


class BackendSplitterAgent(RefactorerBase):
    """Phase 2: Extracts backend functions into module files."""

    def _apply_experience(self):
        relevant = self._recall_by_types()
        if relevant:
            self.log(f"Recalling {len(relevant)} lessons before backend extraction")

    def run(self, source_path=None, **kwargs):
        if not self._check_dependency():
            return {"status": "blocked"}
        self._apply_experience()

        auditor_exp = self.team["agents"].get("auditor", {}).get("experience", {})
        function_index = auditor_exp.get("function_index", {})

        # Group functions by category for extraction plan
        by_category = {}
        for name, info in function_index.items():
            cat = info.get("category", "uncategorized")
            by_category.setdefault(cat, []).append(name)

        self.log(f"Extraction plan: {len(by_category)} modules")
        for cat, funcs in by_category.items():
            self.log(f"  {cat}: {len(funcs)} functions")

        self.save_state()
        return {"status": "ready", "extraction_plan": by_category}


class FrontendSplitterAgent(RefactorerBase):
    """Phase 3: Extracts CSS and JS into external files."""

    def _apply_experience(self):
        relevant = self._recall_by_types()
        if relevant:
            self.log(f"Recalling {len(relevant)} lessons before frontend extraction")
            # Specifically look for data_flow lessons — critical for JS extraction
            data_flow = [l for l in relevant if l.get("category") == "data_flow"]
            if data_flow:
                self.log(f"  WARNING: {len(data_flow)} data-flow lessons. "
                         f"Check PHP-in-JS patterns before extracting.")

    def run(self, source_path=None, **kwargs):
        if not self._check_dependency():
            return {"status": "blocked"}
        self._apply_experience()

        auditor_exp = self.team["agents"].get("auditor", {}).get("experience", {})
        file_map = auditor_exp.get("file_map", {})

        # Identify JS sections from file_map
        js_sections = {}
        for filename, info in file_map.items():
            sections = info.get("sections", {})
            for section_name, line_range in sections.items():
                if section_name.startswith("js_"):
                    js_sections[section_name] = line_range

        self.log(f"Found {len(js_sections)} JS sections to extract")
        for name, (start, end) in js_sections.items():
            self.log(f"  {name}: lines {start}-{end} ({end - start} lines)")

        self.save_state()
        return {"status": "ready", "js_sections": js_sections}


class CleanupAgent(RefactorerBase):
    """Phase 4: Final cleanup — dead code, logging, git init."""

    def run(self, source_path=None, **kwargs):
        if not self._check_dependency():
            return {"status": "blocked"}

        targets = self.config.get("targets", [])
        self.log(f"Cleanup targets: {len(targets)}")
        for target in targets:
            self.log(f"  - {target}")

        self.save_state()
        return {"status": "ready", "targets": targets}
