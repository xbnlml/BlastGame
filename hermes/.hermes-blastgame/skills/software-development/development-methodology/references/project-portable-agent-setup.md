# Project-Portable Agent Setup (HERMES_HOME Pattern)

**Class:** Development environment methodology — project-scoped agent configuration that's self-contained and portable.

## Problem

You have a project folder that you want to stay self-contained — all tools, configs, and agent state live inside it so you can copy the whole directory to another machine and pick up where you left off. The default Hermes profile lives under `~/.hermes/` (system home), which ties the agent to one machine and mixes state across projects.

## Solution: Project-Level HERMES_HOME

Put a dedicated Hermes home directory **inside** the project folder and point to it via the `HERMES_HOME` environment variable.

### Directory Layout

```
my-project/
├── .hermes/                 ← Full Hermes home (config, skills, memory, sessions)
│   ├── config.yaml
│   ├── .env
│   ├── skills/
│   ├── sessions/
│   ├── memory/
│   └── state.db
├── src/
├── Makefile
└── ...
```

### Launch Methods

#### CLI: env var on each invocation

```bash
cd my-project
HERMES_HOME="$(pwd)/.hermes" hermes
```

#### CLI: wrapper script (portable, relative path)

Create `my-project/hermes.sh`:

```bash
#!/bin/bash
HERMES_HOME="$(dirname "$0")/.hermes" exec hermes "$@"
```

The script uses a **relative** path, so if you copy the whole folder to a different machine (different absolute path), it still works.

#### Hermes Desktop App

The desktop app reads `HERMES_HOME` from its environment. Launch it from the wrapper script:

```bash
# my-project/hermes-desktop.sh
#!/bin/bash
cd "$(dirname "$0")"
HERMES_HOME="$(pwd)/.hermes" hermes desktop
```

Or set the env var system-wide for that project by adding it to `.env` or a shell profile alias.

### Migration Steps

1. Create the project's `.hermes/` directory structure
2. Copy `config.yaml` and `.env` from `~/.hermes/` (adjust as needed)
3. Install project-specific skills: `hermes skills install <name>` (runs inside the new home)
4. Project memory/sessions accumulate naturally as you work

All Hermes state — sessions, memory, cron jobs — lives under `.hermes/` and goes with the folder.

### Isolation Benefits

- **No cross-project contamination** — project A's memory doesn't leak into project B
- **Clean slate per project** — skills only include what the project needs
- **Copy + run portability** — clone/folder-copy to another machine works
- **Accountability** — `.hermes/` can be `.gitignore`d or selectively tracked

### When NOT to Use This Pattern

- You want a single agent with unified memory across all projects → use the default `~/.hermes/` home
- You just need different configs/models per project → use `hermes profile` instead (lighter weight, but data stays in system home)

### Related

- Hermes docs: [Profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)
- Hermes env vars: `HERMES_HOME` changes the entire home directory
