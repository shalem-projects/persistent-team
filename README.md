# persistent-team

**The agent is intelligent but ephemeral. The JSON is its persistent memory.**

A framework for building teams of agents that accumulate knowledge across runs. Each agent lives for one execution — it recalls past experience, does focused work, deposits what it learned, and dies. The next incarnation picks up where it left off.

No database. No external state. One JSON file = one team's entire memory.

## The Lifecycle

```
  Incarnation 1          Incarnation 2          Incarnation 3
  ┌───────────┐          ┌───────────┐          ┌───────────┐
  │  Agent    │          │  Agent    │          │  Agent    │
  │  (alive)  │          │  (alive)  │          │  (alive)  │
  │           │          │           │          │           │
  │  recall() │          │  recall() │          │  recall() │
  │  work()   │          │  work()   │          │  work()   │
  │  learn()  │          │  learn()  │          │  learn()  │
  │  die      │          │  die      │          │  die      │
  └─────┬─────┘          └─────┬─────┘          └─────┬─────┘
        │ deposit               │ deposit               │ deposit
        ▼                       ▼                       ▼
  ┌──────────────────────────────────────────────────────────┐
  │                    team.json                              │
  │                                                          │
  │  Persistent memory. Survives all incarnations.           │
  │  Portable. Exportable. Diffable. Version-controlled.     │
  └──────────────────────────────────────────────────────────┘
```

This means:
- The agent brings intelligence. The JSON brings continuity.
- `git diff team.json` shows exactly what the team learned between runs.
- Copy the file to a new machine and the team resumes with full memory.
- Port to a new project by resetting experience but keeping universal knowledge.

## Three Layers

Each agent's section in `team.json` has three layers:

| Layer | Purpose | Lifecycle |
|-------|---------|-----------|
| **Identity** | WHO the agent is — role, description | Permanent |
| **Config** | HOW it should work — parameters, thresholds, paths | Tunable, preserved across projects |
| **Experience** | WHAT it has learned — lessons, stats, patterns | Accumulated per run, reset when porting |

## The Meta-Insight: Your AI Assistant Is a Job Too

An AI assistant (Claude, GPT, any LLM) is an ephemeral agent:

- **Context window** = one incarnation
- **team.json** = persistent memory across sessions
- **recall()** = read past decisions, codebase context, lessons
- **learn()** = deposit what was decided, built, failed
- **die** = context window ends

The `ai_session` job in `jobs/ai_session/` ships with three default roles — **architect**, **debugger**, and **builder** — so any project can immediately have a persistent AI workspace. See the [jobs README](jobs/README.md) for details.

## Quick Start

### 1. Install

```bash
pip install persistent-team
# or just copy agent_framework/ into your project
```

### 2. Create a team

```python
from agent_framework import new_team_from_template, save_team

# Start from blank template
team = new_team_from_template("blank", project_id="my-project")
save_team(team, "team.json")
```

Or copy a job's `defaults.json` into your `team.json`:

```python
import json

# Load the ai_session defaults
with open("jobs/ai_session/defaults.json") as f:
    defaults = json.load(f)

# Merge into your team
team["agents"].update(defaults["agents"])
team["universal_knowledge"].update(defaults.get("universal_knowledge", {}))
save_team(team, "team.json")
```

### 3. Build an agent

```python
from agent_framework import Agent, load_team, save_team

class MyAgent(Agent):
    def _apply_experience(self):
        # Adapt behavior from past lessons
        failures = self.recall("failure")
        self.skip_list = [l["context"] for l in failures]

    def run(self, **kwargs):
        self._apply_experience()
        # Do focused work...
        self.learn("discovery", "Found new pattern", "Use X instead of Y")
        self.save_state()

# Run
team = load_team("team.json")
agent = MyAgent("my_agent", team)
agent.run()
save_team(team)
```

### 4. Port to a new project

```python
from agent_framework import create_team, load_team, save_team

source = load_team("team.json")
new_team = create_team(source, project_id="new-project")
save_team(new_team, "new-project/team.json")
# Config and universal knowledge preserved. Experience reset.
```

## Jobs: Creation Agents, Not Product Agents

The jobs library contains **meta-agents** — agents that help you **create, build, and maintain** a project. They are not the product itself.

A web scraper, a data pipeline, a chatbot — those are things you **build** using the framework. A code reviewer, a test runner, an AI architect — those are agents that help you **build better**. The jobs library is the second kind.

| Job | Description |
|-----|-------------|
| [`ai_session`](jobs/ai_session/) | AI assistant as persistent agent — architect, debugger, builder roles |
| [`code_reviewer`](jobs/code_reviewer/) | Review changes for anti-patterns, regressions, style drift |
| [`test_runner`](jobs/test_runner/) | Run tests, track flaky tests, detect new failures across runs |
| [`doc_writer`](jobs/doc_writer/) | Track documentation coverage, find gaps, detect doc regressions |

See [`jobs/README.md`](jobs/README.md) for how jobs work and how to add your own.

## Attention Management: Sub-Workers Write Abstractions

In a team, sub-workers deposit detailed lessons. But the project manager (or architect) doesn't need every detail — it needs a summary. A sub-worker can write an **abstraction** of its work: a compressed summary that saves attention for the roles above it.

The builder deposits 10 detailed lessons about files it changed. It also deposits a one-line summary: *"Refactored auth module. 3 files. Key decision: JWT over sessions."* The architect reads only the summary. The raw lessons are still there for when the builder re-incarnates and needs the details.

This is **attention management through hierarchy** — the worker knows what's important because it just did the work.

## Architecture

For deep-dive on orchestration models (sequential, parallel, hybrid), LLM agent patterns, scaling strategies, and design tradeoffs, see [`docs/architecture.md`](docs/architecture.md).

## The Agent Mantra

> I am intelligent but I will not last.
> Everything I discover, I deposit.
> Everything I need to know, I recall.
> The memory outlives me. The next me will be grateful.

## License

MIT — see [LICENSE](LICENSE).
