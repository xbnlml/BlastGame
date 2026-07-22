---
name: autonomous-coding-agents
description: "Orchestration guide for external coding CLIs: Claude Code, OpenAI Codex, OpenCode."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [coding-agent, claude-code, codex, opencode, pty, orchestration, delegation]
---

# Autonomous Coding Agents — Unified Orchestration

Delegate coding tasks to three external AI coding CLIs. All share common patterns: PTY mode for interactive use, background process monitoring, git repo requirement, and parallel worktree support.

## Quick Comparison

| Feature | Claude Code | Codex | OpenCode |
|---------|------------|-------|----------|
| One-shot mode | `claude -p "..."` | `codex exec "..."` | `opencode run "..."` |
| Interactive mode | `claude` (TUI, needs tmux) | `codex` (TUI) | `opencode` (TUI) |
| Needs PTY? | Interactive only | Yes (always) | `run`=no, TUI=yes |
| Git required? | No | **Yes** | No |
| Auth | OAuth or API key | OAuth or API key | Provider-agnostic |
| Cost tracking | Built-in `--max-budget-usd` | Not built-in | `opencode stats` |
| Subagents | Yes (agents + MCP) | No | No |
| PR Review | `--from-pr N` | Clone + review | `opencode pr N` |
| CI/Script mode | `--bare` | `--yolo` | `run` with flags |

**Choose:**
- **Claude Code** — most feature-rich, best for complex multi-step tasks, has MCP integration, subagents, hooks
- **Codex** — simplest API, sandboxed by default, best for quick one-shot tasks
- **OpenCode** — provider-agnostic (use any model), open-source, lightweight

---

## Section 1: Claude Code

Anthropic's autonomous coding agent CLI. Full TUI, print mode, agents, MCP, hooks.

### Prerequisites
```bash
npm install -g @anthropic-ai/claude-code
claude auth login          # or: claude auth login --console
claude auth status
```

### Mode 1: Print Mode (Preferred) — One-Shot
```bash
claude -p 'Add error handling to API calls' --allowedTools 'Read,Edit' --max-turns 10
```

**Key flags:** `-p` (one-shot), `--max-turns N`, `--max-budget-usd N`, `--effort level`, `--output-format json`, `--json-schema '...'`, `--bare` (CI mode), `--fallback-model haiku`

### Mode 2: Interactive — Multi-Turn via tmux
```bash
tmux new-session -d -s claude-work -x 140 -y 40
tmux send-keys -t claude-work 'cd /project && claude' Enter
sleep 5 && tmux send-keys -t claude-work Enter   # Trust dialog
tmux send-keys -t claude-work 'Refactor auth module' Enter
tmux capture-pane -t claude-work -p -S -50         # Monitor
tmux send-keys -t claude-work '/exit' Enter         # Exit
```

### Dialog Handling
- Workspace trust: Enter (default "Yes")
- Permissions bypass dialog: `Down` then Enter (default is "No, exit")

### Structured Output
```bash
claude -p 'Analyze auth.py for security issues' --output-format json --max-turns 5
```
Returns JSON with `session_id`, `num_turns`, `total_cost_usd`, `usage` breakdown.

### Key Features
- **Slash commands:** `/compact`, `/review`, `/plan`, `/model`, `/effort`, `/batch`
- **CLAUDE.md** project memory, auto-loaded from project root
- **Custom subagents:** `.claude/agents/<name>.md`
- **MCP integration:** `claude mcp add <name> -- <cmd>`
- **Hooks:** PreToolUse, PostToolUse, Stop — auto-format, security gates
- **Worktree isolation:** `claude -w feature-x --tmux`
- **Session continuation:** `claude -c` (resume last) or `-r <id>`

### CI/Bare Mode
```bash
claude --bare -p 'Run all tests and report failures' --allowedTools 'Read,Bash' --max-turns 10
```
Requires `ANTHROPIC_API_KEY`. Fastest startup, skips OAuth/plugins/MCP.

---

## Section 2: OpenAI Codex

OpenAI's autonomous coding agent CLI. Simpler than Claude Code, with built-in sandboxing.

### Prerequisites
```bash
npm install -g @openai/codex
# Auth: OPENAI_API_KEY or Codex OAuth login
```

**Must run inside a git repository** — Codex refuses to run outside one.

### One-Shot Tasks
```bash
codex exec 'Add dark mode toggle to settings'
```

For scratch (Codex needs git):
```bash
cd $(mktemp -d) && git init && codex exec 'Build a snake game in Python'
```

### Key Flags
- `exec "prompt"` — one-shot execution
- `--full-auto` — auto-approves workspace changes
- `--yolo` — no sandbox, no approvals (fastest)
- `--sandbox danger-full-access` — bypass bubblewrap issues

### Background Mode
```bash
terminal(command="codex exec --full-auto 'Refactor the auth module'", background=true, pty=true)
# Monitor with process(action="poll", ...)
# Send input with process(action="submit", ...)
```

### PR Reviews
```bash
REVIEW=$(mktemp -d) && git clone https://github.com/user/repo.git $REVIEW
cd $REVIEW && gh pr checkout 42 && codex review --base origin/main
```

### Parallel Worktrees
```bash
git worktree add -b fix/issue-78 /tmp/issue-78 main
codex --yolo exec 'Fix issue #78 and commit'  # in /tmp/issue-78
```

### Hermes Gateway Caveat
Codex sandboxing may fail in Hermes gateway contexts (bubblewrap/user-namespace errors). Use:
```bash
codex exec --sandbox danger-full-access "<task>"
```

**Always use `pty=true`** — Codex hangs without a PTY.

---

## Section 3: OpenCode

Provider-agnostic, open-source AI coding agent. Use any model provider.

### Prerequisites
```bash
npm i -g opencode-ai@latest      # or: brew install anomalyco/tap/opencode
opencode auth login              # then: opencode auth list
```

### One-Shot Tasks (No PTY Needed)
```bash
opencode run 'Add retry logic to API calls'
opencode run 'Review config for security issues' -f config.yaml -f .env.example
opencode run 'Refactor auth module' --model openrouter/anthropic/claude-sonnet-4
```

### Interactive TUI (Background)
```bash
terminal(command="opencode", background=true, pty=true)
process(action="submit", session_id="<id>", data="Implement OAuth refresh flow")
process(action="poll", session_id="<id>")
process(action="write", session_id="<id>", data="\x03")  # Ctrl+C to exit
```

**Important:** Do NOT use `/exit` — use Ctrl+C (`\x03`) to exit.

### Key Flags
| Flag | Use |
|------|-----|
| `run '...'` | One-shot execution |
| `-c` / `--continue` | Resume last session |
| `-s <id>` | Resume specific session |
| `--model p/m` | Force model |
| `--thinking` | Show thinking |
| `-f <path>` | Attach file |
| `--format json` | Machine output |
| `--variant high` | Reasoning effort |

### Binary Resolution
Shell may resolve wrong binary. Check with `which -a opencode`. Pin explicit path if needed:
```bash
$HOME/.opencode/bin/opencode run '...'
```

### PR Review
```bash
opencode pr 42     # Built-in PR review
```

### Cost Tracking
```bash
opencode stats
opencode stats --days 7 --models anthropic/claude-sonnet-4
```

### Session Management
```bash
opencode session list     # List past sessions
```

---

## Comparison: When to Use Which

| Task | Best Agent | Reason |
|------|-----------|--------|
| Quick one-shot fix | Codex | Simplest API, --yolo for speed |
| Complex multi-step feature | Claude Code | Subagents, MCP, hooks, CLAUDE.md |
| Provider-agnostic | OpenCode | Any model, open-source |
| CI/Automation | Claude Code (--bare) | Fastest CI startup, structured JSON |
| Low-cost | OpenCode | Use cheap models via OpenRouter |
| Sandboxed execution | Codex (--full-auto) | Built-in sandbox by default |
| Batch parallel tasks | Any | All support worktrees + background |
| PR Review | Claude Code | --from-pr N, native support |
