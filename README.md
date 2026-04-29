# Ergon

A CLI-first multi-agent helper tool. Ergon orchestrates AI coding CLIs 
(Claude Code, OpenAI Codex Gemini) around structured tasks, isolated git worktrees, validation runs,
reviews, and human approval.

Ergon is not a chatbot. It is a workflow orchestrator: you describe a task,
Ergon spins up a worktree, an agent works inside it, Ergon captures the diff
and validation logs, and you decide what to do next.

## Design priorities

1. Local-first.
2. CLI-first.
3. Git-worktree aware.
4. Human-in-the-loop. Ergon never merges or pushes automatically.
5. Safe by default; unsafe modes available with explicit flags.
6. Supports interactive conversational mode.
7. Stores all task artifacts as readable Markdown / YAML.

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/aarchan108/Ergon.git
cd Ergon
python3 -m venv .venv
.venv/bin/pip install -e .
```

The `ergon` entry point lands on your PATH (within the venv). To use it
without activating the venv, symlink it or alias it:

```bash
ln -s "$PWD/.venv/bin/ergon" ~/.local/bin/ergon
```

Ergon shells out to model CLIs. Install whichever you want to use:

- Claude Code → `claude`
- OpenAI Codex / ChatGPT CLI → `codex`
- Gemini CLI → `gemini`

Edit `~/.ergon/agents.yaml` after first run to point at the actual binary
names if they differ.

## Quick start

```bash
cd /path/to/your-repo                    # any git repo
ergon init --type roblox-rojo            # or embedded-zephyr | ros2 | python | generic
ergon start "Add guard vision cone system"
ergon plan 001 --agent openai
ergon implement 001 --agent claude       # opens claude inside an isolated worktree
ergon validate 001
ergon review 001 --agents openai gemini
ergon status 001
ergon diff 001
```

Each step writes Markdown / YAML artifacts under
`.ergon/tasks/001-add-guard-vision-cone-system/`:

```
task.yaml
brief.md
context.md
plan.md
implementation-log.md
diff.patch
changed_files.txt
validation.log
review-openai.md
review-gemini.md
review-summary.md
```

The agent's actual changes live in a separate worktree at
`~/ergon/worktrees/<repo>/<id-slug-agent>/` on a branch named
`ergon/<id-slug>/<agent>`. Your main checkout is never touched.

## Commands

| command                                     | what it does                                                |
| ------------------------------------------- | ----------------------------------------------------------- |
| `ergon init --type <kind>`                  | bootstrap `.ergon/` in the current repo                     |
| `ergon start <title>`                       | create a new numbered task folder                           |
| `ergon plan <id> --agent <name>`            | run the planner agent → `plan.md`                           |
| `ergon implement <id> --agent <name>`       | open the implementer agent inside an isolated worktree      |
| `ergon validate <id>`                       | run the task's validation commands inside its worktree      |
| `ergon review <id> --agents X Y`            | run reviewer agents → `review-X.md`, `review-Y.md`, summary |
| `ergon analyze <path> --type <kind>`        | run the analyzer on a log / pdf / csv / etc                 |
| `ergon debug <id> --agent <name>`           | run the debugger agent → `debug-<agent>.md`                 |
| `ergon status [<id>]`                       | project- or task-level status                               |
| `ergon tasks`                               | list all tasks                                              |
| `ergon logs <id> [-f <file>]`               | list / read task artifacts                                  |
| `ergon diff <id> [--refresh]`               | print the captured diff                                     |
| `ergon chat`                                | interactive shell                                           |

## Project config

`.ergon/project.yaml` is created by `ergon init` and tells Ergon how to
validate this project, which agent to use for each role, and which paths
agents should consider in scope. See `examples/project-zephyr.yaml` and
`examples/project-roblox.yaml` for reference shapes.

```yaml
name: NightRaid
type: roblox-rojo
repo_path: /path/to/repo
default_branch: main

validation:
  commands:
    - rojo build -o build.rbxlx

rules:
  auto_merge: false
  auto_push: false
  require_manual_approval: true
  safety_level: guarded

agents:
  planner: openai
  implementer: claude
  debugger: openai
  analyzer: gemini
  reviewers:
    - openai
    - gemini

context:
  include: [src/**, shared/**, server/**, client/**]
  exclude: [.git/**, build/**]
```

## Agent config

`~/.ergon/agents.yaml` is global. It maps logical names (`claude`, `openai`,
`gemini`) to the actual CLI binary and how Ergon should invoke it.

```yaml
agents:
  claude:
    backend: cli
    command: claude
    default_role: implementer
    mode: native           # hands the user a real PTY in the worktree
  openai:
    backend: cli
    command: codex
    default_role: planner_reviewer_debugger
    mode: controlled       # Ergon pipes a structured prompt on stdin
  gemini:
    backend: cli
    command: gemini
    default_role: analyzer_reviewer
    mode: controlled
```

Agent modes:

- `native` — Ergon runs the CLI in the worktree with a real PTY. Best for
  the implementer role (Claude Code is designed for this).
- `controlled` — Ergon pipes a structured prompt on stdin and captures
  stdout. Best for one-shot reviewer / planner / analyzer / debugger calls.
- `unsafe` / `unrestricted` — broader command access, captured but not
  policed. Use only for throwaway / experimental projects.

## Safety

Default safety level is `guarded`: agents work in worktrees, but no
automatic merge / push / sudo. `strict` is reserved for projects where you
want a tool broker between the agent and the filesystem (planned, not in
the MVP). `unsafe` and `unrestricted` are explicit opt-ins.

Ergon never merges, pushes, force-resets, or deletes your work without you
asking. The diff lives on a branch under `ergon/<id-slug>/<agent>`. You
review it in `ergon diff <id>` (or with your normal git tools), then merge
or discard manually.

## Project memory

`.ergon/memory/` holds long-lived project notes that Ergon includes when
prompting role agents:

- `architecture.md` — high-level structure
- `decisions.md` — engineering decisions and reasons
- `conventions.md` — coding style, branching, commit style
- `glossary.md` — project-specific terms

These files are committed alongside your code. Update them as the project
evolves; Ergon will fold the relevant pieces into planner / reviewer /
debugger prompts.

## What is *not* in the MVP

- Web UI
- Plugin marketplace
- Direct API integrations (CLI only for now)
- Tool-broker sandbox (`strict` mode is the same as `guarded` for MVP)
- Automatic merge / push (intentional — Ergon is human-in-the-loop)
- Background daemon, scheduling, SQLite job queue (planned)
- Media analysis pipeline beyond text excerpts

## Layout

```
ergon/
  cli/        Typer commands
  core/       project, task, orchestrator, artifact store, bootstrap
  agents/     CliAgent + registry
  roles/      prompt builders for planner / reviewer / analyzer / debugger / summariser
  tools/      git, worktree, shell command helpers
  ui/         console + interactive chat shell
  prompts/    canonical role system prompts and task templates
  utils/      slug, paths, yaml helpers
examples/     reference project / task YAMLs
```

## License

MIT.
