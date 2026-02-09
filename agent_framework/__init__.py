"""
agent_framework — reusable JSON-memory agent pattern.

The agent is intelligent but ephemeral. The JSON is its persistent memory.
An agent lives for one run: recall → work → learn → deposit → die.
What survives is what it deposits into the JSON.

Usage:
    from agent_framework import Agent, load_team, save_team, create_team

    team = load_team("team.json")
    agent = MyAgent("my_agent", team)
    agent.run()
    save_team(team)
"""

from .agent import Agent
from .team_io import load_team, save_team, TEAM_FILE
from .team_factory import create_team, new_team_from_template

__all__ = [
    "Agent",
    "load_team",
    "save_team",
    "TEAM_FILE",
    "create_team",
    "new_team_from_template",
]
