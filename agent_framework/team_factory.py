"""
Team factory: create new teams by cloning existing ones or from templates.

The experience-reset logic preserves structure but clears accumulated data,
so a new deployment starts fresh while keeping universal knowledge and config.
"""

import copy
import json
from datetime import datetime
from pathlib import Path

from .team_io import save_team


def _reset_experience(team):
    """
    Reset all agent experience in a team — the brain starts fresh
    but universal_knowledge carries over.

    Handles arbitrary experience shapes:
    - lists → []
    - dicts of numbers → zeroed
    - other dicts → {}
    - numbers → 0
    - None → None
    - strings → ""
    - "format_priority" → preserved (universal knowledge embedded in agent)
    """
    for agent in team["agents"].values():
        exp = agent["experience"]
        for key, value in exp.items():
            if key == "lessons_learned":
                exp[key] = []
            elif key == "format_priority":
                pass  # preserve — this is universal knowledge embedded in agent
            elif isinstance(value, list):
                exp[key] = []
            elif isinstance(value, dict):
                exp[key] = {k: 0 for k in value} if all(
                    isinstance(v, (int, float)) for v in value.values()
                ) else {}
            elif isinstance(value, (int, float)):
                exp[key] = 0
            elif value is None:
                exp[key] = None
            else:
                exp[key] = ""


def create_team(source_team, project_id, project_meta=None,
                agent_overrides=None, output_path=None):
    """
    Create a new team.json by cloning a source team with reset experience.

    Preserves: universal_knowledge, agent roles, config structure
    Resets: all experience (lessons_learned, stats, site-specific data)
    Updates: project_id, created date, and any project_meta fields

    Args:
        source_team: dict — the source team.json to clone from
        project_id: str — identifier for the new project (e.g. "haifa")
        project_meta: dict — additional top-level fields to set
            (e.g. {"city_name": "חיפה", "city_name_en": "Haifa"})
        agent_overrides: dict — per-agent config overrides
            (e.g. {"scout": {"config": {"entry_urls": [...]}}})
        output_path: str/Path — if set, saves the new team.json here

    Returns:
        The new team dict
    """
    new_team = copy.deepcopy(source_team)

    # Set project identity
    new_team["project_id"] = project_id if "project_id" in new_team else None
    if "city" in new_team:
        new_team["city"] = project_id
    new_team["created"] = datetime.now().strftime("%Y-%m-%d")

    # Apply project metadata
    if project_meta:
        for key, value in project_meta.items():
            new_team[key] = value

    # Apply per-agent overrides (deep merge into config)
    if agent_overrides:
        for agent_name, overrides in agent_overrides.items():
            if agent_name in new_team["agents"]:
                agent = new_team["agents"][agent_name]
                for section, values in overrides.items():
                    if section in agent and isinstance(agent[section], dict):
                        agent[section].update(values)
                    else:
                        agent[section] = values

    # Reset all agent experience
    _reset_experience(new_team)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        save_team(new_team, out, backup=False)

    return new_team


def new_team_from_template(template_name, project_id, project_meta=None,
                           agent_overrides=None, output_path=None):
    """
    Create a new team from a bundled template.

    Args:
        template_name: str — name of the template (e.g. "blank")
            Looks in agent_framework/templates/{template_name}.json
        project_id: str — identifier for the new project
        project_meta: dict — additional top-level fields
        agent_overrides: dict — per-agent config overrides
        output_path: str/Path — if set, saves the new team.json here

    Returns:
        The new team dict
    """
    templates_dir = Path(__file__).parent / "templates"
    template_path = templates_dir / f"{template_name}.json"

    if not template_path.exists():
        available = [f.stem for f in templates_dir.glob("*.json")]
        raise FileNotFoundError(
            f"Template '{template_name}' not found. "
            f"Available: {available}"
        )

    with open(template_path, "r", encoding="utf-8") as f:
        template = json.load(f)

    return create_team(
        source_team=template,
        project_id=project_id,
        project_meta=project_meta,
        agent_overrides=agent_overrides,
        output_path=output_path,
    )
