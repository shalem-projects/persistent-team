# Jobs

A **job** is a reusable agent definition: a Python class + a `defaults.json` that you can deploy into any project's `team.json`.

## Structure

Each job is a directory:

```
jobs/
├── my_job/
│   ├── agent.py         ← the agent class (extends Agent)
│   └── defaults.json    ← identity + config + empty experience
```

- `agent.py` contains the agent class with `run()`, `_apply_experience()`, and any helper methods.
- `defaults.json` contains a valid `team.json` fragment with the agent pre-configured and experience zeroed out.

## How to Deploy a Job

1. Copy the job's `defaults.json` agents into your project's `team.json`:

```python
import json
from agent_framework import load_team, save_team

# Load your project team
team = load_team("team.json")

# Load the job defaults
with open("jobs/web_scraper/defaults.json") as f:
    defaults = json.load(f)

# Merge agents and universal knowledge
team["agents"].update(defaults["agents"])
for key, value in defaults.get("universal_knowledge", {}).items():
    team["universal_knowledge"][key] = value

save_team(team)
```

2. Customize the config for your project (URLs, paths, patterns, etc.)

3. Import and use the agent class:

```python
from jobs.web_scraper.agent import ScraperAgent

agent = ScraperAgent("scraper", team)
results = agent.run()
```

## Available Jobs

### `ai_session` — AI Assistant as Persistent Agent

The meta-job. Your AI coding assistant (Claude, GPT, any LLM) treated as an ephemeral agent. Ships with three roles:

- **architect** — plans, designs, restructures
- **debugger** — investigates, traces, fixes
- **builder** — implements features, creates agents

Each role deposits its own experience. The `universal_knowledge` section captures project-wide truths (repo structure, import patterns, conventions).

**Using it with Claude/GPT/any LLM:**
1. Deploy `defaults.json` into your project's `team.json`
2. At session start, feed the relevant role's `experience.lessons_learned` + `universal_knowledge` as context to the LLM
3. During the session, have the LLM record decisions and outcomes
4. Before the session ends, deposit a session summary

```python
from jobs.ai_session.agent import SessionAgent

agent = SessionAgent("architect", team)
context = agent.recall_session_context()  # feed this to the LLM

# ... session work happens ...

agent.deposit_session(
    summary="Refactored auth module, added rate limiting",
    decisions=["Chose JWT over sessions", "Added Redis for token cache"],
    built=["auth/jwt.py", "middleware/rate_limit.py"],
    failed=["Tried SQLite for cache — too slow under load"]
)
```

### `web_scraper` — Fetch Pages, Extract Links

Fetches web pages, extracts links, learns which URLs are dead, tracks success rates across runs.

### `file_scanner` — Scan Directories, Classify Files

Scans directories for files matching patterns, classifies them by type (code, data, docs, config), detects new/changed/deleted files between runs.

### `log_analyzer` — Parse Logs, Track Error Trends

Parses log files, categorizes errors by severity and pattern, tracks frequency trends across runs to detect emerging issues.

## How to Add a New Job

1. Create a directory under `jobs/`:

```
jobs/my_new_job/
├── agent.py
└── defaults.json
```

2. Write `defaults.json` — a valid team.json fragment:

```json
{
  "project_id": "",
  "created": "",
  "description": "What this job does",
  "agents": {
    "my_agent": {
      "role": "My Agent Role",
      "description": "What it does in plain English",
      "config": {
        "max_lessons": 100
      },
      "experience": {
        "run_count": 0,
        "lessons_learned": []
      }
    }
  },
  "universal_knowledge": {}
}
```

3. Write `agent.py` — extend `Agent`:

```python
from agent_framework import Agent

class MyAgent(Agent):
    def _apply_experience(self):
        # Load past lessons, adapt behavior
        pass

    def run(self, **kwargs):
        self._apply_experience()
        # Do focused work
        # self.learn(...) to record observations
        self.save_state()
        return results
```

4. Test it:

```python
from agent_framework import load_team, save_team
from jobs.my_new_job.agent import MyAgent

team = load_team("team.json")
agent = MyAgent("my_agent", team)
result = agent.run()
save_team(team)
```
