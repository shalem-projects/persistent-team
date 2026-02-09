"""
Agent base class for the JSON-memory team architecture.

Core principle: each agent's JSON object IS its persistent brain.
When spawned, the agent loads its object, adapts behavior from experience,
works, records what it learned, and saves state back. The next incarnation
inherits everything.

    agent = MyAgent(team)       # spawned with its JSON scope
    agent.recall("dead_url")    # reads past lessons
    records = agent.run()       # adapts behavior from experience
    agent.save_state()          # writes back everything learned
"""

from datetime import datetime


class Agent:
    """
    Base class for a focused agent. Its JSON object is its persistent brain.

    Lifecycle:
        1. __init__  — load JSON object as scope
        2. recall()  — read past lessons to adapt
        3. run()     — do focused work (overridden by subclass)
        4. learn()   — record problems, solutions, edge cases
        5. save_state() — persist everything back to the JSON object

    Subclasses override run() and _apply_experience().
    """

    def __init__(self, name, team, engine=None):
        self.name = name
        self.team = team
        self.engine = engine  # e.g. "claude-opus-4-6", "claude-sonnet-4-5", "gpt-4o"
        self.state = team["agents"][name]
        self.role = self.state["role"]
        self.config = self.state["config"]
        self.experience = self.state["experience"]
        self._run_lessons = []   # lessons from THIS run only
        self._run_start = datetime.now()

    def recall(self, category=None):
        """
        Recall lessons from past runs. The agent's memory.

        Args:
            category: filter by category (e.g. "dead_url", "cms_quirk",
                     "parse_failure", "encoding_issue", "workaround")
        Returns:
            list of lesson dicts
        """
        lessons = self.experience.get("lessons_learned", [])
        if category:
            return [l for l in lessons if l.get("category") == category]
        return lessons

    def learn(self, category, problem, solution, context=None, engine=None):
        """
        Record a lesson learned during this run. This is how the agent
        builds knowledge for its next incarnation.

        Args:
            category: type of lesson (e.g. "dead_url", "parse_failure",
                     "encoding_issue", "workaround", "cms_quirk",
                     "regression", "new_pattern")
            problem: what went wrong or what was unexpected
            solution: what worked, or what should be tried next time
            context: optional extra data (URL, text sample, error message)
            engine: override engine for this specific lesson (defaults to
                    self.engine set at init). Records which AI model or
                    tool produced this knowledge — helps next incarnation
                    calibrate trust (e.g. Opus architecture vs Haiku lint).
        """
        lesson = {
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "problem": problem,
            "solution": solution,
        }
        if context is not None:
            lesson["context"] = context
        # Record which engine produced this lesson
        effective_engine = engine or self.engine
        if effective_engine:
            lesson["engine"] = effective_engine
        self._run_lessons.append(lesson)

    def log(self, msg, indent=1):
        """Print a message tagged with this agent's name."""
        prefix = "  " * indent
        print(f"{prefix}[{self.name}] {msg}", flush=True)

    def save_state(self):
        """
        Persist this run's lessons and updated stats back to the JSON object.
        Trims lessons to max_lessons to prevent unbounded growth.
        """
        if "lessons_learned" not in self.experience:
            self.experience["lessons_learned"] = []

        self.experience["lessons_learned"].extend(self._run_lessons)

        # Trim to keep only the most recent lessons
        max_lessons = self.config.get("max_lessons", 100)
        lessons = self.experience["lessons_learned"]
        if len(lessons) > max_lessons:
            self.experience["lessons_learned"] = lessons[-max_lessons:]

        # Track how many times this agent has run
        self.experience["run_count"] = self.experience.get("run_count", 0) + 1

        if self._run_lessons:
            self.log(f"Saved {len(self._run_lessons)} new lesson(s) "
                     f"({len(self.experience['lessons_learned'])} total)")

    def _apply_experience(self):
        """
        Hook for subclasses to adapt behavior based on accumulated experience
        BEFORE doing work. Called at the start of run().
        """
        pass

    def run(self, **kwargs):
        """Override in subclass. Called to do the agent's focused work."""
        raise NotImplementedError
