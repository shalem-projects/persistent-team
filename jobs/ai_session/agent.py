"""
SessionAgent — the meta-job: an AI assistant as a persistent agent.

Your AI assistant (Claude, GPT, any LLM) is an ephemeral agent:
- Context window = one incarnation
- team.json = persistent memory across sessions
- recall() = read past decisions, codebase context, lessons
- learn() = deposit what was decided, built, failed
- die = context window ends

This agent ships with three default roles:
- architect: plans, designs, restructures
- debugger: investigates, traces, fixes
- builder: implements features, creates agents

Usage:
    from agent_framework import load_team, save_team
    from jobs.ai_session.agent import SessionAgent

    team = load_team("team.json")
    agent = SessionAgent("architect", team)

    # At session start — recall past context
    context = agent.recall_session_context()

    # During session — record decisions and outcomes
    agent.learn("decision", "Chose X over Y", "X has better perf", context="benchmark results")

    # Before session ends — deposit everything
    agent.deposit_session(summary="Implemented feature Z, refactored module Q")
    save_team(team)
"""

from datetime import datetime

from agent_framework import Agent


class SessionAgent(Agent):
    """
    An AI session treated as an agent incarnation.

    Extends the base Agent with session-specific helpers:
    - recall_session_context(): summarize what past sessions deposited
    - deposit_session(): save a session summary before context dies
    """

    def _apply_experience(self):
        """Load universal knowledge and past lessons for this role."""
        self._universal = self.team.get("universal_knowledge", {})

    def recall_session_context(self):
        """
        Build a context summary from deposited memory.

        Returns a dict with:
        - role: this agent's role
        - past_lessons: all deposited lessons
        - universal_knowledge: project-wide truths
        - run_count: how many sessions this role has had
        - other_agents: summary of what other roles have deposited
        """
        self._apply_experience()

        # Summarize other agents' recent lessons
        other_agents = {}
        for name, agent_data in self.team["agents"].items():
            if name != self.name:
                exp = agent_data.get("experience", {})
                lessons = exp.get("lessons_learned", [])
                other_agents[name] = {
                    "role": agent_data.get("role", ""),
                    "run_count": exp.get("run_count", 0),
                    "recent_lessons": lessons[-5:] if lessons else [],
                }

        return {
            "role": self.role,
            "past_lessons": self.recall(),
            "universal_knowledge": self._universal,
            "run_count": self.experience.get("run_count", 0),
            "other_agents": other_agents,
        }

    def deposit_session(self, summary, decisions=None, built=None, failed=None):
        """
        Deposit a session summary before context dies.

        This is the critical call — everything not deposited is lost
        when the context window ends.

        Args:
            summary: brief description of what this session accomplished
            decisions: list of key decisions made (optional)
            built: list of things created/implemented (optional)
            failed: list of things that didn't work (optional)
        """
        # Record the session summary as a lesson
        context_parts = []
        if decisions:
            context_parts.append(f"Decisions: {'; '.join(decisions)}")
        if built:
            context_parts.append(f"Built: {'; '.join(built)}")
        if failed:
            context_parts.append(f"Failed: {'; '.join(failed)}")

        self.learn(
            category="session_summary",
            problem="Session ending — depositing context",
            solution=summary,
            context=" | ".join(context_parts) if context_parts else None,
        )

        # Record individual decisions as separate lessons
        if decisions:
            for decision in decisions:
                self.learn(
                    category="decision",
                    problem="Architectural/design choice",
                    solution=decision,
                )

        # Record failures as lessons for next incarnation
        if failed:
            for failure in failed:
                self.learn(
                    category="failure",
                    problem=failure,
                    solution="Needs investigation in next session",
                )

        # Persist
        self.save_state()

    def run(self, **kwargs):
        """
        Not typically called directly — AI sessions are interactive.

        Override this if you want to create an automated session agent
        that runs without human interaction.
        """
        self._apply_experience()
        context = self.recall_session_context()
        self.log(f"Session started. Role: {self.role}. "
                 f"Past runs: {context['run_count']}. "
                 f"Lessons available: {len(context['past_lessons'])}.")
        return context
