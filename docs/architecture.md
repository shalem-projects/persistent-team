# Architecture: Agent Team Pattern

## Core Principle

**The agent is intelligent but ephemeral. The JSON is its persistent memory.**

An AI agent lives for one run. It is born, it thinks, it acts, it dies. What survives is what it deposits into the JSON — its experience, context, findings, and observations. The next incarnation reads the JSON, reconstructs awareness from the deposited memory, does new work, and deposits again before dying.

The JSON is not the brain. The agent is the brain. The JSON is the **diary, the filing cabinet, the institutional memory** that outlives any single incarnation.


## What Gets Deposited: Three Layers

Each agent's section in the JSON has three layers:

```
┌─────────────────────────────────┐
│  IDENTITY (permanent)           │
│  - role: what this agent does   │
│  - description: in plain words  │
│  WHO the agent is               │
└─────────────────────────────────┘
┌─────────────────────────────────┐
│  CONFIG (tunable)               │
│  - parameters, thresholds       │
│  - input sources, paths         │
│  - carries across projects      │
│  HOW the agent should work      │
└─────────────────────────────────┘
┌─────────────────────────────────┐
│  EXPERIENCE (accumulated)       │
│  - findings[]                   │
│  - stats, patterns, hit rates   │
│  - contacts, discovered data    │
│  - grows with every run         │
│  WHAT the agent has learned     │
└─────────────────────────────────┘
```

### Identity
Fixed. Defines WHO the agent is. Doesn't change across runs or projects. The new incarnation reads this to understand its purpose.

### Config
Parameters that control HOW the agent works. Tunable but stable. Represents best practices — carries over when porting to a new project.

### Experience
Everything the agent has LEARNED from doing its work. Structured so the next incarnation can quickly reconstruct awareness:
- `findings[]` — structured entries with category, problem, solution, context
- Stats — counters, rates, histories
- Patterns — what works, what's dead, what's changed

Experience is **reset when porting** to a new project (it's situational) but **preserved across runs** on the same project (it accumulates).


## The Agent Lifecycle

Every agent follows the same lifecycle, regardless of complexity:

```
1. BORN        →  instantiated with its JSON section
2. RECALL      →  reads deposited memory, adapts behavior
3. WORK        →  does its focused task (the intelligent part)
4. LEARN       →  records problems, solutions, edge cases, discoveries
5. DEPOSIT     →  saves everything back to JSON
6. DIE         →  agent instance is gone. Memory persists.
```

```python
agent.recall("failure")          →  reads past findings by category
agent.learn("failure",           →  records a new lesson
    problem="API returned 500",
    solution="Retry with exponential backoff",
    context="/api/data endpoint")
agent.save_state()               →  deposits back to JSON
```

Findings are categorized so agents can recall specific types. Categories are domain-specific — each job defines its own. Findings are trimmed to `max_findings` to prevent unbounded growth. Old findings fall off. Recent experience is always prioritized.


## Universal Knowledge vs Project-Specific Experience

```json
{
  "agents": { "..." : "..." },
  "universal_knowledge": {
    "common_patterns": ["..."],
    "known_edge_cases": ["..."],
    "format_rankings": { "...": "..." }
  }
}
```

When porting `team.json` to a new project:
- `universal_knowledge` → **preserved** (patterns, rankings, shared truths)
- Agent `config` → **preserved** (best practices, thresholds)
- Agent `experience` → **reset** (findings, stats, project-specific data)

Universal knowledge is the team's **collective wisdom** — things that are true regardless of which project. Experience is **situational** — what this specific deployment has encountered.


---


## Orchestration Models

### Model A: Sequential Pipeline

Agents run in sequence. Each phase feeds the next. One process, one JSON.

```
Agent A  →  Agent B  →  Agent C  →  Agent D
                 output feeds input
```

**When this is right:**
- Agents depend on each other's output (pipeline)
- One JSON = one atomic save = no race conditions
- Easy to debug — read the console top to bottom
- Small team (3–10 agents)


### Model B: Parallel Independent Agents

Agents run as separate processes, possibly on separate machines. Each agent owns its own section of the shared memory. A coordinator manages lifecycle and memory merging.

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Agent A    │  │  Agent B    │  │  Agent C    │
│  (process)  │  │  (process)  │  │  (process)  │
│             │  │             │  │             │
│  own work   │  │  own work   │  │  own work   │
│  own timing │  │  own timing │  │  own timing │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │ deposit         │ deposit         │ deposit
       ▼                 ▼                 ▼
┌──────────────────────────────────────────────────┐
│              COORDINATOR                          │
│                                                   │
│  - loads team.json                                │
│  - hands each agent its section                   │
│  - collects deposits when agents finish           │
│  - merges experience back into one JSON           │
│  - saves atomically                               │
│  - detects conflicts (two agents wrote same key)  │
└──────────────────────────────────────────────────┘
                       │
                       ▼
                  team.json
```

**When this is right:**
- Agents do independent work (not a pipeline)
- Tasks are long-running or unpredictable in duration
- Agents might run on different machines or schedules
- Scale exceeds 10+ agents
- Some agents are AI-powered (LLM calls), others are deterministic

**Key design rules for parallel agents:**
1. **Each agent owns its section.** Agent A never writes to Agent B's experience. This eliminates write conflicts.
2. **The coordinator is the only writer to team.json.** Agents return their updated section; the coordinator merges and saves.
3. **Cross-agent communication goes through the JSON.** If Agent B needs to know what Agent A found, it reads Agent A's deposited experience on its next incarnation. No direct messaging.
4. **Agents are stateless between runs.** All state lives in the JSON. Any agent can be killed and restarted without data loss.


### Model C: Hybrid — Pipeline with Parallel Branches

Some agents are sequential (output → input), others are independent and can run in parallel.

```
                    ┌── Agent B1 (parallel) ──┐
Agent A  →  Agent B │                          │ → Agent D
                    └── Agent B2 (parallel) ──┘
```

Example: Agent B finds 1000 items. Two worker agents split the work and process in parallel. Agent D waits for both to finish.

```python
# Coordinator splits work
items_a = items[:500]
items_b = items[500:]

# Spawn parallel
thread_a = spawn(WorkerAgent, items=items_a)
thread_b = spawn(WorkerAgent, items=items_b)

# Wait and merge experience
wait_all([thread_a, thread_b])
merge_experience(team, [thread_a.agent, thread_b.agent])
save_team(team)
```


---


## When Agents Are AI-Powered (LLM Agents)

In complex projects, an "agent" might be backed by an actual LLM (Claude, GPT, etc.) rather than deterministic code. The pattern holds perfectly:

```
1. Load agent's memory from JSON
2. Feed memory as context to the LLM
3. LLM reasons, acts, produces results
4. Extract structured findings from LLM output
5. Deposit findings back to JSON
6. LLM context is gone (ephemeral). Memory persists.
```

The JSON serves as the **long-term memory** that bridges across LLM context windows. Each LLM invocation is one incarnation — it reads the deposited memory, does intelligent work, and deposits back.

This is especially powerful because:
- LLM context windows are limited. JSON memory is unlimited.
- LLM calls are expensive. Deposited experience avoids re-learning.
- Different agents can use different models (cheap model for routine work, expensive model for complex reasoning).

### The AI Session Pattern

The `ai_session` job is a concrete implementation of this idea. Your AI coding assistant (Claude, GPT, etc.) is treated as an ephemeral agent with three roles:

- **architect** — plans, designs, restructures
- **debugger** — investigates, traces, fixes
- **builder** — implements features, creates agents

Each role deposits its own experience. Between sessions, the `team.json` carries forward:
- What was decided and why
- What was built and how
- What failed and what the fix was
- Codebase structure, import patterns, project conventions

The next session's AI reads all of this on startup and continues with full context — even though its previous incarnation is gone.


---


## Scaling: From 5 Agents to N Agents

### Adding an Agent
= add a JSON entry + a Python class (or standalone script). No framework changes. `create_team()` automatically handles new agents. The `Agent` base class provides learn/recall/save for free.

### Composing Teams
= copy `team.json`, adjust config. Different projects get different teams but share universal knowledge and the agent codebase.

### Cross-Team Learning
= merge experience from multiple `team.json` files. Agents can accumulate patterns across projects — learned success rates, common failure modes, optimal configurations.

### Splitting a Team
When a team outgrows single-process orchestration:
1. Keep one `team.json` as the shared memory
2. Split agents into separate scripts/processes
3. Add a coordinator for merging deposits
4. Each agent still follows the same lifecycle: recall → work → deposit


## Standalone Agent Processes

For projects where agents are truly separate (different codebases, different schedules, different machines):

```python
# my_agent.py — runs independently, maybe on a cron job

from agent_framework import Agent, load_team, save_team

class ResearcherAgent(Agent):
    def _apply_experience(self):
        # Read what other agents have deposited
        other_exp = self.team["agents"]["other"]["experience"]
        known_items = other_exp.get("discovered_items", [])
        self.log(f"Other agent knows about {len(known_items)} items")

    def run(self, **kwargs):
        self._apply_experience()
        # Do independent work...
        self.learn("discovery", "Found new source", "Use it next time")
        self.save_state()

if __name__ == "__main__":
    team = load_team("team.json")
    agent = ResearcherAgent("researcher", team)
    agent.run()
    save_team(team)
```

### Locking for Concurrent Access

When agents run truly in parallel and share one JSON file:

```python
import filelock

lock = filelock.FileLock("team.json.lock")

with lock:
    team = load_team("team.json")
    agent = MyAgent("my_agent", team)
    agent.run()
    save_team(team)
```

Or use the coordinator model where agents deposit to separate files and the coordinator merges:

```
agent_a_deposit.json  ──┐
agent_b_deposit.json  ──┼──→  coordinator  ──→  team.json
agent_c_deposit.json  ──┘
```


## Creation Agents vs Product Agents

An important distinction in how jobs are categorized:

**Creation agents** help you build and maintain a project:
- AI session (architect, debugger, builder)
- Code reviewer, test runner, doc writer
- These live in the jobs library — reusable across any project

**Product agents** ARE the project you're building:
- A web scraper, a data pipeline, a chatbot
- These are deployed in your project's `team.json` directly
- They use the framework, but they're not part of the framework

The jobs library ships only creation agents. Product agents are what you build *using* the framework.

The test: **does this agent help CREATE a project, or is it a PRODUCT of a project?**


## Attention Management: Sub-Workers Write Abstractions

In a team with hierarchy, detailed findings are noise for the roles above. A sub-worker should deposit **two levels** of information:

1. **Detailed findings** — for its own next incarnation (full context, specific files, exact errors)
2. **A summary abstraction** — for the manager/architect role (compressed, decision-focused)

```
Builder deposits:
  findings: [
    { detailed lesson 1 },
    { detailed lesson 2 },
    ...10 more...
    { category: "session_summary",
      solution: "Refactored auth. 3 files. JWT over sessions. Redis for cache." }
  ]

Architect reads:
  → only the session_summary lesson from builder
  → saves attention for architectural decisions
  → can drill into detailed findings if needed
```

This is **attention management through hierarchy**. The worker knows what matters because it just did the work. It compresses its experience into what the roles above actually need. Raw details persist for when the same role re-incarnates.


## Resource Tracking Protocol

Every agent session MUST record:
1. **Engine** — which AI model did the work (e.g. "claude-opus-4-6", "claude-sonnet-4-5")
2. **Sub-agents spawned** — ID, task description, token count, model used
3. **Total token usage** — sum of all agent tokens (main session tokens estimated if not available)

This serves two purposes:
- **Trust calibration**: Opus architecture decisions carry more weight than Haiku lint checks
- **Cost awareness**: Know which phases are expensive and which are cheap. Helps plan future sessions.

Record in experience as:
```json
"token_usage": {
  "session_engine": "claude-opus-4-6",
  "agents_spawned": [
    {"id": "abc123", "task": "what it did", "tokens": 44287, "model": "opus"}
  ],
  "total_agent_tokens": 180355
}
```


## Design Decisions and Tradeoffs

| Decision | Why | Tradeoff |
|----------|-----|----------|
| JSON not database | Portable, diffable, no deps | Size limit ~50MB practical |
| Agent is ephemeral | Stateless, restartable, replaceable | Must deposit everything or it's lost |
| Findings trimmed to max | Prevents unbounded growth | Old findings are lost |
| Experience reset on port | Clean start per project | Loses project-specific tricks |
| Config preserved on port | Best practices transfer | May need manual tuning |
| One JSON = one team | Atomic, simple, portable | Needs locking if truly parallel |
| Track token usage | Cost awareness + trust calibration | Approximate (sub-agent only) |


## The Agent Mantra

> I am intelligent but I will not last.
> Everything I discover, I deposit.
> Everything I need to know, I recall.
> The memory outlives me. The next me will be grateful.
